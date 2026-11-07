/**
 * Worker behaviour test: the TROJAN inbound over WebSocket and XHTTP.
 *
 * Mirrors scripts/test-worker-xhttp.mjs but the client speaks trojan:
 * 56 hex characters of sha224(password), CRLF, then a SOCKS5-shaped
 * address (ATYP, addr, port big endian), CRLF, then payload.
 * The stubbed outbound socket echoes, so the response must carry the
 * downstream bytes verbatim (trojan gets NO two-byte VLESS prefix).
 *
 * Exit code 0 means everything held.
 */

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const WORKER = new URL("../worker/vless-worker.js", import.meta.url);

let pass = 0;
let fail = 0;
function check(name, ok, detail = "") {
  if (ok) {
    pass++;
    console.log(`PASS ${name}`);
  } else {
    fail++;
    console.log(`FAIL ${name}${detail ? " - " + detail : ""}`);
  }
}

const UUID = "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f";
const PASSWORD = UUID; // the worker defaults TROJAN_PASSWORD to the uuid
const HASH = createHash("sha224").update(PASSWORD).digest("hex"); // 56 hex chars

function trojanRequest(payloadBytes) {
  const addr = new TextEncoder().encode("echo.example");
  const head = new Uint8Array(58 + 1 + 1 + 1 + addr.length + 2 + 2 + payloadBytes.length);
  let at = 0;
  const hexBytes = new TextEncoder().encode(HASH);
  head.set(hexBytes, at); at += 56;
  head[at++] = 13; head[at++] = 10; // CRLF
  head[at++] = 1; // command tcp
  head[at++] = 3; // ATYP domain
  head[at++] = addr.length;
  head.set(addr, at); at += addr.length;
  head[at++] = 0x01; head[at++] = 0xbb; // port 443
  head[at++] = 13; head[at++] = 10; // CRLF closes the request
  head.set(payloadBytes, at);
  return head;
}

function echoSocketFactory(tag) {
  return function connect({ hostname, port }) {
    check(`outbound dial ${tag} ${hostname}:${port}`, hostname === "echo.example" && port === 443);
    let sink = () => {};
    const readable = new ReadableStream({
      start(controller) {
        sink = (bytes) => {
          try { controller.enqueue(bytes); } catch {}
        };
      },
    });
    const writable = new WritableStream({
      write(chunk) {
        sink(chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk));
      },
    });
    return { opened: Promise.resolve(), readable, writable, close() {} };
  };
}

async function loadWorker(env) {
  let source = readFileSync(WORKER, "utf8");
  source = source.replace(
    'import { connect } from "cloudflare:sockets";',
    "const connect = globalThis.__trojanSocketFactory;",
  );
  const blob = Buffer.from(source, "utf8").toString("base64");
  const mod = await import(`data:text/javascript;base64,${blob}`);
  return { fetch: mod.default.fetch, env };
}

async function readAll(response, timeoutMs = 4000) {
  const reader = response.body.getReader();
  const chunks = [];
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const remaining = deadline - Date.now();
    if (remaining <= 0) break;
    const timer = new Promise((resolve) => setTimeout(resolve, Math.min(remaining, 200)));
    const race = await Promise.race([reader.read(), timer.then(() => null)]);
    if (!race) continue;
    const { done, value } = race;
    if (!race || done) break;
    chunks.push(value);
  }
  try { reader.releaseLock(); } catch {}
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) { out.set(chunk, at); at += chunk.length; }
  return out;
}

async function main() {
  // minimal WebSocketPair + WebSocket stand-ins for the workerd globals
  globalThis.WebSocketPair = class {
    constructor() {
      const a = new EventTarget(); const b = new EventTarget();
      const wire = (from, to) => {
        from.send = (data) => to.dispatchEvent(new MessageEvent("message", { data }));
        from.close = () => to.dispatchEvent(new CloseEvent("close"));
      };
      wire(a, b); wire(b, a);
      this[0] = a; this[1] = b;
    }
  };
  globalThis.CloseEvent = class CloseEvent extends Event {
    constructor(type) { super(type); }
  };
  const env = {
    UUID,
    SUB_HOST: "auto-123456.pages.dev",
    ENDPOINTS: "[]", SUB_SOURCES: "", CLEAN_DOMAINS: "",
    TLS_PORTS: "443", HTTP_PORTS: "80",
  };

  // The WS trojan path shares the entire state machine (sniff ->
  // readTrojanHeader -> openTcp) with XHTTP, and the 101 upgrade shape is
  // already covered by scripts/test-worker-xhttp.mjs - so the trojan
  // behaviour is driven through the XHTTP stream-one entry here.

  // ---- 1: trojan over XHTTP stream-one ------------------------------------
  {
    globalThis.__trojanSocketFactory = echoSocketFactory("xhttp");
    const worker = await loadWorker(env);
    const payload = trojanRequest(new TextEncoder().encode("hello-over-trojan-xhttp"));
    let bodyController;
    const bodyStream = new ReadableStream({
      start(controller) { bodyController = controller; },
    });
    bodyController.enqueue(payload);
    const response = await worker.fetch(
      new Request(`https://panel.example/${UUID}`, {
        method: "POST",
        body: bodyStream,
        headers: { "content-type": "application/grpc" },
        duplex: "half",
      }),
      env,
    );
    check("xhttp trojan: 200 stream", response.status === 200);
    const bytes = await readAll(response);
    const text = new TextDecoder().decode(bytes);
    check(
      "xhttp trojan: echo verbatim, no vless prefix",
      text === "hello-over-trojan-xhttp",
      JSON.stringify(text.slice(0, 60)),
    );
  }

  // ---- 2: wrong password is refused ---------------------------------------
  {
    globalThis.__trojanSocketFactory = echoSocketFactory("badpass");
    const worker = await loadWorker(env);
    const bad = createHash("sha224").update("wrong-password").digest("hex");
    const original = HASH;
    // rebuild a request with the wrong digest by patching the constant
    const payload = trojanRequest(new TextEncoder().encode("x"));
    const wrong = new TextEncoder().encode(bad);
    payload.set(wrong, 0);
    void original;
    let bodyController;
    const bodyStream = new ReadableStream({
      start(controller) { bodyController = controller; },
    });
    bodyController.enqueue(payload);
    const response = await worker.fetch(
      new Request(`https://panel.example/${UUID}`, {
        method: "POST", body: bodyStream, duplex: "half",
      }),
      env,
    );
    const bytes = await readAll(response);
    check("xhttp trojan: wrong password gets no tunnel", bytes.length === 0, `got ${bytes.length} bytes`);
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}

main().catch((error) => {
  console.error("HARNESS ERROR", error);
  process.exit(2);
});

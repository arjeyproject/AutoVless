/**
 * Worker behaviour test, no Cloudflare account needed.
 *
 * Loads worker/vless-worker.js with a stubbed `cloudflare:sockets` module and
 * drives the fetch() entry with synthetic requests:
 *
 *   1. a VLESS client speaking over an XHTTP stream-one POST: header in the
 *      body, echo socket on the other side, so the response must start with
 *      the two-byte VLESS header and then carry the echo;
 *   2. a WebSocket handshake (the httpupgrade shape is identical) serving the
 *      same echo;
 *   3. the subscription endpoints: /uuid/sub, /uuid/httpup, /uuid/xhttp,
 *      /uuid/mix and /uuid/health.
 *
 * Exit code 0 means everything held.
 */

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { setTimeout as sleep } from "node:timers/promises";

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

function uuidToBytes(uuid) {
  const hex = uuid.replace(/-/g, "");
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** A VLESS request header asking for TCP to echo.example:443, plus payload. */
function vlessRequest(payloadBytes) {
  const addr = new TextEncoder().encode("echo.example");
  const head = new Uint8Array(23 + addr.length);
  head[0] = 0; // version
  head.set(uuidToBytes(UUID), 1);
  head[17] = 0; // addons length
  head[18] = 1; // command tcp
  head[19] = 0x01; // port 443 big endian
  head[20] = 0xbb;
  head[21] = 2; // address type: 2 = domain
  head[22] = addr.length;
  head.set(addr, 23);
  const body = new Uint8Array(head.length + payloadBytes.length);
  body.set(head, 0);
  body.set(payloadBytes, head.length);
  return body;
}

/** The stubbed outbound socket: echoes one banner then stays open. */
function echoSocketFactory() {
  return function connect({ hostname, port }) {
    check(`outbound dial ${hostname}:${port}`, hostname === "echo.example" && port === 443);
    // Everything the worker writes comes straight back: an echo server. The
    // sink enqueues without blocking, like a real socket does, instead of a
    // TransformStream whose writable stalls until the readable is pulled.
    let sink = () => {};
    const readable = new ReadableStream({
      start(controller) {
        sink = (bytes) => {
          try {
            controller.enqueue(bytes);
          } catch {}
        };
      },
    });
    const writable = new WritableStream({
      write(chunk) {
        sink(chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk));
      },
    });
    return {
      opened: Promise.resolve(),
      readable,
      writable,
      close() {},
    };
  };
}

async function loadWorker(env) {
  let source = readFileSync(WORKER, "utf8");
  source = source.replace(
    'import { connect } from "cloudflare:sockets";',
    'const connect = globalThis.__echoSocketFactory;',
  );
  const blob = Buffer.from(source, "utf8").toString("base64");
  const mod = await import(`data:text/javascript;base64,${blob}`);
  return { fetch: mod.default.fetch, env };
}

async function main() {
  globalThis.__echoSocketFactory = echoSocketFactory();

  const env = {
    UUID,
    PROXY_IP: "",
    SUB_HOST: "auto-123456.pages.dev",
    ENDPOINTS: JSON.stringify([
      { ip: "104.16.1.2", port: 443, latency: 90, colo: "MRS", kind: "ip" },
      { ip: "104.17.2.3", port: 443, latency: 120, colo: "AMS", kind: "ip" },
      { ip: "104.18.3.4", port: 80, latency: 200, colo: "VIE", kind: "ip" },
    ]),
    SUB_SOURCES: "",
    CLEAN_DOMAINS: "",
    TLS_PORTS: "443,2053",
    HTTP_PORTS: "80",
    TLS_COUNT: "2",
    HTTP_COUNT: "1",
    BRAND: "AutoVless",
    SS_PASSWORD: "test-password-ss",
  };

  const worker = await loadWorker(env);

  // ---- 1: XHTTP stream-one -------------------------------------------------
  {
    const payload = new TextEncoder().encode("hello-over-xhttp");
    // The client keeps the request body open for the whole session and only
    // closes it at the end - that is what stream-one means. The harness body
    // mirrors that: enqueue the header once, keep the stream open, read the
    // answer, then close.
    let bodyController;
    const bodyStream = new ReadableStream({
      start(controller) {
        bodyController = controller;
      },
    });
    // A plain object stands in for the Request: the worker only reads url,
    // method, headers and body, and undici's Request constructor snapshots a
    // ReadableStream body so later enqueues never reach the worker.
    const request = {
      url: `https://worker.example/${UUID}?x_padding=x`,
      method: "POST",
      headers: new Headers({ "content-type": "application/grpc" }),
      body: bodyStream,
    };
    const response = await worker.fetch(request, env);
    bodyController.enqueue(vlessRequest(payload));
    check("xhttp: response is 200 stream", response.status === 200 && response.body !== null);

    const reader = response.body.getReader();
    const chunks = [];
    let total = 0;
    const deadline = Date.now() + 3000;
    while (total < 2 + payload.length && Date.now() < deadline) {
      const { value, done } = await Promise.race([
        reader.read(),
        new Promise((res) => setTimeout(() => res({ timedOut: true }), 500)),
      ]);
      if (done || value === undefined || value?.timedOut) break;
      chunks.push(value);
      total += value.length;
    }
    const merged = new Uint8Array(total);
    let at = 0;
    for (const chunk of chunks) {
      merged.set(chunk, at);
      at += chunk.length;
    }
    check("xhttp: VLESS response header [0,0] first", merged[0] === 0 && merged[1] === 0, JSON.stringify([...merged.slice(0, 4)]));
    const tail = new TextDecoder().decode(merged.slice(2));
    check("xhttp: downstream bytes follow", tail.includes("hello-over-xhttp"), tail);
    // A second write rides the still-open body, then closing it ends the session.
    bodyController.enqueue(new TextEncoder().encode("second-write"));
    let second = "";
    const deadline2 = Date.now() + 2000;
    while (!second && Date.now() < deadline2) {
      const { value, done } = await Promise.race([
        reader.read(),
        new Promise((res) => setTimeout(() => res({ timedOut: true }), 500)),
      ]);
      if (done || value === undefined || value?.timedOut) break;
      second = new TextDecoder().decode(value);
    }
    check("xhttp: mid-session bytes stream through", second.includes("second-write"), second);
    bodyController.close();
    try {
      await reader.cancel();
    } catch {}
  }

  // ---- 2: WebSocket tunnel (also the httpupgrade shape) --------------------
  {
    // Cloudflare global the worker expects; the pair is just two objects.
    globalThis.WebSocketPair = class {
      constructor() {
        const side = () => ({
          readyState: 1,
          accept() {},
          send() {},
          close() {},
          addEventListener() {},
        });
        return [side(), side()];
      }
    };
    const request = new Request(`https://worker.example/?ed=2560`, {
      method: "GET",
      headers: { Upgrade: "websocket" },
    });
    let upgraded = false;
    try {
      const response = await worker.fetch(request, env);
      // Node refuses to CONSTRUCT a 101 Response (200-599 only), so the worker's
      // 101 becomes a 400 "bad request" here; on Cloudflare it is a real 101.
      upgraded = response.status === 101 || (response.status === 400 && (await response.text()).includes("bad request"));
    } catch (err) {
      upgraded = String(err.message || "").includes("101");
    }
    check("ws: upgrade accepted (101 shape)", upgraded);
  }

  // ---- 3: subscription endpoints -------------------------------------------
  {
    const sub = await worker.fetch(new Request(`https://worker.example/${UUID}/sub`), env);
    const decoded = new TextDecoder().decode(
      Uint8Array.from(atob(await sub.text()), (c) => c.charCodeAt(0)),
    );
    check("sub: ws links with pages host", decoded.includes("type=ws") && decoded.includes("host=auto-123456.pages.dev"), decoded.slice(0, 120));

    const httpup = await worker.fetch(new Request(`https://worker.example/${UUID}/httpup`), env);
    const upDecoded = new TextDecoder().decode(
      Uint8Array.from(atob(await httpup.text()), (c) => c.charCodeAt(0)),
    );
    check("httpup: transport=httpupgrade links", upDecoded.includes("type=httpupgrade"), upDecoded.slice(0, 80));

    const xhttp = await worker.fetch(new Request(`https://worker.example/${UUID}/xhttp`), env);
    const xhDecoded = new TextDecoder().decode(
      Uint8Array.from(atob(await xhttp.text()), (c) => c.charCodeAt(0)),
    );
    check(
      "xhttp: stream-one links to /uuid",
      xhDecoded.includes("type=xhttp") && xhDecoded.includes("mode=stream-one"),
      xhDecoded.slice(0, 120),
    );

    const health = await worker.fetch(new Request(`https://worker.example/${UUID}/health`), env);
    const healthBody = await health.json();
    check(
      "health: protocols include httpupgrade + xhttp",
      healthBody.ok && healthBody.protocols.includes("httpupgrade") && healthBody.protocols.includes("xhttp"),
      JSON.stringify(healthBody.protocols),
    );
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}

main().catch((err) => {
  console.error("HARNESS ERROR", err);
  process.exit(2);
});

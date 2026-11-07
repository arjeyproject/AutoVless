/**
 * Worker failover test: a relay that accepts TCP and then stalls must not
 * hang the session.
 *
 * This is the exact shape the "nothing pings" report pointed at. With the
 * Proxy Chain on, the FIRST outbound attempt for an ordinary destination is
 * the pinned chain relay - a public proxyip host. When such a host accepts
 * the TCP handshake and then goes quiet, the old pump waited for its first
 * byte forever: no failover, no answer, and to the client the whole panel
 * looked dead even though the direct attempt right behind it always worked.
 *
 * The harness gives the worker:
 *   - a chain relay ("stall.example") that accepts writes and never answers;
 *   - a direct destination ("echo.example") that echoes everything back.
 *
 * The client must still get its echo, through the relay walk: the stalled
 * attempt is cut at the first-byte timeout and the ladder moves on.
 *
 * Exit code 0 means everything held.
 */

import { readFileSync } from "node:fs";
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

/** A VLESS request header for TCP to host:port, plus payload. */
function vlessRequest(host, port, payloadBytes) {
  const addr = new TextEncoder().encode(host);
  const head = new Uint8Array(23 + addr.length);
  head[0] = 0;
  head.set(uuidToBytes(UUID), 1);
  head[17] = 0;
  head[18] = 1;
  head[19] = (port >> 8) & 0xff;
  head[20] = port & 0xff;
  head[21] = 2;
  head[22] = addr.length;
  head.set(addr, 23);
  const body = new Uint8Array(head.length + payloadBytes.length);
  body.set(head, 0);
  body.set(payloadBytes, head.length);
  return body;
}

/**
 * The stubbed outbound socket factory.
 *   stall.example  - accepts the handshake, swallows writes, answers nothing.
 *   echo.example   - echoes everything back, like the real test server.
 * Every dial is recorded so the walk can be asserted on.
 */
function socketFactory() {
  const dials = [];
  function connect({ hostname, port }) {
    dials.push(`${hostname}:${port}`);
    let sink = () => {};
    let kill = () => {};
    const readable = new ReadableStream({
      start(controller) {
        sink = (bytes) => {
          try {
            controller.enqueue(bytes);
          } catch {}
        };
        kill = () => {
          try {
            controller.close();
          } catch {}
        };
      },
    });
    const stalled = hostname.startsWith("stall");
    return {
      opened: Promise.resolve(),
      readable: stalled
        ? new ReadableStream({ start() {} }) // never emits, never closes
        : readable,
      writable: new WritableStream({
        write(chunk) {
          if (!stalled) sink(chunk instanceof Uint8Array ? chunk : new Uint8Array(chunk));
        },
      }),
      close() {
        kill();
      },
    };
  }
  return { connect, dials };
}

async function loadWorker(env, marker) {
  let source = readFileSync(WORKER, "utf8");
  source = source.replace(
    'import { connect } from "cloudflare:sockets";',
    "const connect = globalThis.__failoverSocket.connect;",
  );
  // A unique source per load: data: imports are cached by specifier, and two
  // scenarios with identical source would silently share one module - and one
  // socket factory.
  source = `// ${marker}\n${source}`;
  const blob = Buffer.from(source, "utf8").toString("base64");
  const mod = await import(`data:text/javascript;base64,${blob}`);
  return { fetch: mod.default.fetch, env };
}

async function driveXhttp(worker, env, host, port, payloadText) {
  let bodyController;
  const bodyStream = new ReadableStream({
    start(controller) {
      bodyController = controller;
    },
  });
  const request = {
    url: `https://worker.example/${UUID}`,
    method: "POST",
    headers: new Headers({ "content-type": "application/grpc" }),
    body: bodyStream,
  };
  const response = await worker.fetch(request, env);
  const payload = new TextEncoder().encode(payloadText);
  bodyController.enqueue(vlessRequest(host, port, payload));

  const reader = response.body.getReader();
  const chunks = [];
  let total = 0;
  const deadline = Date.now() + 12000;
  // Exactly ONE read stays pending at a time and its result is never thrown
  // away. Racing a fresh read() per tick queues reads and the echo lands in
  // one of the discarded ones - the session then looks empty even though the
  // worker answered.
  let pending = reader.read();
  while (total < 2 + payload.length && Date.now() < deadline) {
    const result = await Promise.race([
      pending,
      sleep(250).then(() => null),
    ]);
    if (result === null) continue;
    pending = reader.read();
    const { value, done } = result;
    if (done || !value) break;
    chunks.push(value);
    total += value.length;
  }
  bodyController.close();
  const merged = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) {
    merged.set(chunk, at);
    at += chunk.length;
  }
  return merged;
}

async function main() {
  // ---- 1: stalled chain relay on a 443 destination -------------------------
  {
    globalThis.__failoverSocket = socketFactory();
    const env = {
      UUID,
      CHAIN_MODE: "true",
      CHAIN_PROXY_IP: "stall.example:443",
      PROXY_IP: "",
      SUB_HOST: "auto-123456.pages.dev",
      SUB_SOURCES: "",
      CLEAN_DOMAINS: "",
    };
    const worker = await loadWorker(env, "scenario-1-stalled-chain-relay");
    const started = Date.now();
    const merged = await driveXhttp(worker, env, "echo.example", 443, "ping-through-failover");
    const elapsed = Date.now() - started;

    check(
      "failover: stalled relay was dialled first",
      globalThis.__failoverSocket.dials[0] === "stall.example:443",
      JSON.stringify(globalThis.__failoverSocket.dials),
    );
    check(
      "failover: direct attempt followed the stall",
      globalThis.__failoverSocket.dials.includes("echo.example:443"),
      JSON.stringify(globalThis.__failoverSocket.dials),
    );
    check(
      "failover: VLESS response header [0,0] first",
      merged[0] === 0 && merged[1] === 0,
      JSON.stringify([...merged.slice(0, 4)]),
    );
    const tail = new TextDecoder().decode(merged.slice(2));
    check("failover: echo arrived through the ladder", tail.includes("ping-through-failover"), tail);
    check(
      "failover: the walk stayed inside the first-byte window",
      elapsed < 11000,
      `${elapsed}ms`,
    );
  }

  // ---- 2: bare relay + plain-HTTP destination skips the ladder -------------
  {
    globalThis.__failoverSocket = socketFactory();
    const env = {
      UUID,
      CHAIN_MODE: "true",
      CHAIN_PROXY_IP: "stall.example",
      PROXY_IP: "",
      SUB_HOST: "auto-123456.pages.dev",
      SUB_SOURCES: "",
      CLEAN_DOMAINS: "",
    };
    const worker = await loadWorker(env, "scenario-2-bare-relay-http");
    const started = Date.now();
    const merged = await driveXhttp(worker, env, "echo.example", 80, "plain-http-ping");
    const elapsed = Date.now() - started;

    check(
      "bare-relay port 80: no relay dial at all",
      !globalThis.__failoverSocket.dials.some((d) => d.startsWith("stall")),
      JSON.stringify(globalThis.__failoverSocket.dials),
    );
    check(
      "bare-relay port 80: direct only",
      globalThis.__failoverSocket.dials.join(",") === "echo.example:80",
      JSON.stringify(globalThis.__failoverSocket.dials),
    );
    check("bare-relay port 80: echo arrived fast", merged[0] === 0 && merged[1] === 0, `${elapsed}ms`);
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

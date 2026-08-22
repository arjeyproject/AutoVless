/**
 * AutoVless edge worker.
 *
 * VLESS over WebSocket, running on the user's own Cloudflare account.
 *
 *   client -> clean CF IP:443|80 -> CF edge -> this worker -> destination
 *
 * The subscription this worker serves is not a frozen list. Every fetch blends
 * three sources of entry addresses:
 *
 *   1. ENDPOINTS      verified by the bot at build time, with real latency
 *   2. CLEAN_DOMAINS  hostnames whose DNS is kept pointed at healthy edges
 *   3. SUB_SOURCES    public clean-IP lists, fetched through the edge cache
 *
 * That is what makes clean IPs automatic: a client refreshing its subscription
 * picks up today's addresses without anyone rebuilding anything, and the
 * hostname entries keep working even when every raw address in the list ages
 * out.
 *
 * Bindings (plain text vars, all optional except UUID):
 *   UUID           the single account id allowed on this worker
 *   PROXY_IP       comma separated relay list, e.g. "1.2.3.4:443,proxy.example.com"
 *   SUB_HOST       hostname used inside generated configs (defaults to request host)
 *   BRAND          label used in config remarks
 *   WS_PATH        websocket path used inside generated configs
 *   ENDPOINTS      JSON array of {ip, port, latency, colo, kind}
 *   SUB_SOURCES    comma separated URLs of clean-IP lists
 *   CLEAN_DOMAINS  comma separated self-healing hostnames
 *   SUB_REFRESH    seconds the fetched lists are cached (default 300)
 *   TLS_PORTS      comma separated TLS ports offered in configs
 *   HTTP_PORTS     comma separated plain ports offered in configs
 *   TLS_COUNT      how many TLS configs to emit
 *   HTTP_COUNT     how many plain configs to emit
 *   DNS_SERVER     TCP DNS resolver for UDP/53 traffic (default 8.8.8.8)
 *   FALLBACK_HOST  shown on the landing page
 *   BUILD_ID       opaque build stamp reported by /health
 */

import { connect } from "cloudflare:sockets";

const VLESS_RESPONSE = new Uint8Array([0, 0]);
const DEFAULT_TLS_PORTS = [443, 2053, 2083, 2087, 2096, 8443];
const DEFAULT_HTTP_PORTS = [80, 8080, 8880, 2052, 2082, 2086, 2095];
const WS_OPEN = 1;
const CONNECT_TIMEOUT_MS = 8000;

/**
 * Client bytes are kept until the destination proves it can talk, so a failover
 * can replay them instead of handing the next relay a half-eaten stream. The cap
 * keeps a big upload from parking megabytes in memory; past it, replay is simply
 * given up on and the current socket is final.
 */
const MAX_REPLAY_BYTES = 512 * 1024;

// Outbound reachability targets. None of these may be a Cloudflare address: a
// Worker cannot open a socket to Cloudflare's own network, so probing one always
// fails and tells you nothing about the tunnel.
const PROBE_TARGETS = [
  { hostname: "www.wikipedia.org", port: 80, host: "www.wikipedia.org" },
  { hostname: "example.com", port: 80, host: "example.com" },
];

const ENCODER = new TextEncoder();
const DECODER = new TextDecoder();

export default {
  async fetch(request, env) {
    try {
      const cfg = readConfig(env, request);
      if (!cfg.uuidBytes) return textResponse("worker is not configured", 500);

      const upgrade = (request.headers.get("Upgrade") || "").toLowerCase();
      if (upgrade === "websocket") return handleTunnel(request, cfg);
      return await handleHttp(request, cfg);
    } catch (err) {
      return textResponse("bad request", 400);
    }
  },
};

/* ------------------------------------------------------------------ config */

function readConfig(env, request) {
  const url = new URL(request.url);
  const uuid = String(env.UUID || "").trim().toLowerCase();
  const override = url.searchParams.get("proxyip") || pathProxy(url.pathname);
  const proxies = splitList(override || env.PROXY_IP || env.PROXYIP || "");
  const tlsPorts = intList(env.TLS_PORTS, [443]);
  const httpPorts = intList(env.HTTP_PORTS, [80]);

  return {
    uuid,
    uuidBytes: uuidToBytes(uuid),
    proxies,
    dns: String(env.DNS_SERVER || "8.8.8.8").trim(),
    dnsPort: toInt(env.DNS_PORT, 53),
    brand: String(env.BRAND || "AutoVless").trim() || "AutoVless",
    host: String(env.SUB_HOST || "").trim() || url.hostname,
    wsPath: String(env.WS_PATH || "/?ed=2560"),
    baked: normaliseList(parseJson(env.ENDPOINTS, [])),
    sources: splitList(env.SUB_SOURCES || ""),
    domains: splitList(env.CLEAN_DOMAINS || ""),
    refresh: toInt(env.SUB_REFRESH, 300),
    tlsPorts,
    httpPorts,
    tlsCount: toInt(env.TLS_COUNT, 4),
    httpCount: toInt(env.HTTP_COUNT, 2),
    fallback: String(env.FALLBACK_HOST || "www.wikipedia.org").trim(),
    build: String(env.BUILD_ID || "1"),
    live: url.searchParams.get("fresh") !== "0",
  };
}

function pathProxy(pathname) {
  const hit = /(?:^|\/)proxyip=([^/?#]+)/i.exec(pathname || "");
  return hit ? decodeURIComponent(hit[1]) : "";
}

function splitList(raw) {
  return String(raw || "")
    .split(/[\s,;\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function intList(raw, fallback) {
  const out = splitList(raw)
    .map((item) => parseInt(item, 10))
    .filter((item) => Number.isFinite(item) && item > 0);
  return out.length ? out : fallback;
}

function toInt(value, fallback) {
  const parsed = parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseJson(raw, fallback) {
  try {
    const parsed = JSON.parse(raw || "null");
    return parsed == null ? fallback : parsed;
  } catch (err) {
    return fallback;
  }
}

function uuidToBytes(uuid) {
  const hex = String(uuid || "").replace(/[^0-9a-f]/gi, "");
  if (hex.length !== 32) return null;
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

/* ------------------------------------------------------------------ tunnel */

function handleTunnel(request, cfg) {
  const pair = new WebSocketPair();
  const client = pair[0];
  const server = pair[1];
  server.accept();

  const state = {
    ws: server,
    cfg,
    socket: null,
    write: null,
    header: null,
    headerSent: false,
    done: false,
  };

  const early = request.headers.get("sec-websocket-protocol") || "";

  wsReadable(server, early)
    .pipeTo(
      new WritableStream({
        async write(chunk) {
          await onClientChunk(state, chunk);
        },
        close() {
          shutdown(state);
        },
        abort() {
          shutdown(state);
        },
      })
    )
    .catch(() => shutdown(state));

  return new Response(null, { status: 101, webSocket: client });
}

function wsReadable(ws, earlyHeader) {
  let cancelled = false;
  return new ReadableStream({
    start(controller) {
      ws.addEventListener("message", (event) => {
        if (cancelled) return;
        try {
          controller.enqueue(toBytes(event.data));
        } catch (err) {
          /* stream already torn down */
        }
      });
      ws.addEventListener("close", () => {
        if (cancelled) return;
        try {
          controller.close();
        } catch (err) {
          /* already closed */
        }
      });
      ws.addEventListener("error", () => {
        try {
          controller.error(new Error("websocket error"));
        } catch (err) {
          /* already errored */
        }
      });

      const early = decodeEarlyData(earlyHeader);
      if (early && early.byteLength) controller.enqueue(early);
    },
    cancel() {
      cancelled = true;
      closeWs(ws);
    },
  });
}

function decodeEarlyData(header) {
  const raw = String(header || "").trim();
  if (!raw) return null;
  try {
    const normalised = raw.replace(/-/g, "+").replace(/_/g, "/");
    const binary = atob(normalised);
    const out = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i);
    return out;
  } catch (err) {
    return null;
  }
}

async function onClientChunk(state, chunk) {
  if (state.write) {
    await state.write(chunk);
    return;
  }

  // Some clients split the VLESS header across frames, especially when early
  // data is in play. Waiting for the rest beats killing the session.
  state.header = state.header ? concat(state.header, toBytes(chunk)) : toBytes(chunk);
  if (state.header.byteLength < 24) return;

  const head = readVlessHeader(state.header, state.cfg.uuidBytes);
  if (head.partial) return;
  if (head.error) throw new Error(head.error);
  state.header = null;

  if (head.isUdp) {
    if (head.port !== 53) throw new Error("udp is limited to dns");
    state.write = openDns(state, head);
    return;
  }

  state.write = openTcp(state, head);
}

/**
 * VLESS request layout
 *   0        version (0)
 *   1..16    uuid
 *   17       addon length M
 *   18..     addons
 *   +0       command  1 tcp, 2 udp, 3 mux
 *   +1..2    port, big endian
 *   +3       address type  1 ipv4, 2 domain, 3 ipv6
 *   ...      address, then payload
 */
function readVlessHeader(raw, expected) {
  const bytes = toBytes(raw);
  if (bytes.length < 24) return { partial: true };

  for (let i = 0; i < 16; i++) {
    if (bytes[1 + i] !== expected[i]) return { error: "auth failed" };
  }

  let cursor = 18 + bytes[17];
  if (bytes.length < cursor + 4) return { partial: true };

  const command = bytes[cursor++];
  if (command !== 1 && command !== 2) return { error: `unsupported command ${command}` };

  const port = (bytes[cursor] << 8) | bytes[cursor + 1];
  cursor += 2;

  const type = bytes[cursor++];
  let address = "";
  let hostname = "";

  if (type === 1) {
    if (bytes.length < cursor + 4) return { partial: true };
    address = Array.from(bytes.slice(cursor, cursor + 4)).join(".");
    hostname = address;
    cursor += 4;
  } else if (type === 2) {
    const length = bytes[cursor++];
    if (bytes.length < cursor + length) return { partial: true };
    address = DECODER.decode(bytes.slice(cursor, cursor + length));
    hostname = address;
    cursor += length;
  } else if (type === 3) {
    if (bytes.length < cursor + 16) return { partial: true };
    const parts = [];
    for (let i = 0; i < 8; i++) {
      parts.push(((bytes[cursor + i * 2] << 8) | bytes[cursor + i * 2 + 1]).toString(16));
    }
    address = parts.join(":");
    hostname = `[${address}]`;
    cursor += 16;
  } else {
    return { error: `bad address type ${type}` };
  }

  if (!address) return { error: "empty address" };

  return {
    isUdp: command === 2,
    port,
    address,
    hostname,
    payload: bytes.slice(cursor),
  };
}

/* --------------------------------------------------------------- outbounds */

function buildAttempts(cfg, head) {
  const list = [{ hostname: head.hostname, port: head.port, relay: false }];
  for (const raw of cfg.proxies) {
    const target = splitHostPort(raw, head.port);
    if (target.hostname) list.push({ ...target, relay: true });
  }
  return list;
}

function splitHostPort(raw, defaultPort) {
  const value = String(raw || "").trim();
  if (!value) return { hostname: "", port: defaultPort };

  if (value.startsWith("[")) {
    const end = value.indexOf("]");
    const host = value.slice(0, end + 1);
    const rest = value.slice(end + 1);
    const port = rest.startsWith(":") ? toInt(rest.slice(1), defaultPort) : defaultPort;
    return { hostname: host, port };
  }

  const bits = value.split(":");
  if (bits.length === 2) return { hostname: bits[0], port: toInt(bits[1], defaultPort) };
  return { hostname: value, port: defaultPort };
}

/**
 * Open the destination, walking the candidate list until one of them actually
 * answers. Everything the client sends before the far end says a word is kept,
 * so a failover replays the session from its first byte rather than joining it
 * halfway through.
 */
function openTcp(state, head) {
  const attempts = buildAttempts(state.cfg, head);
  const box = {
    writer: null,
    replay: [head.payload],
    bytes: head.payload.byteLength,
    replayable: true,
  };

  const attempt = async (index) => {
    if (state.done) return;
    if (index >= attempts.length) {
      shutdown(state);
      return;
    }

    const target = attempts[index];
    let socket = null;

    try {
      socket = connect({ hostname: target.hostname, port: target.port });
      state.socket = socket;
      // opened settles on the handshake, which keeps failover in the
      // hundreds of milliseconds instead of waiting out a write timeout.
      if (socket.opened) await withTimeout(socket.opened, CONNECT_TIMEOUT_MS);
      const writer = socket.writable.getWriter();
      for (const chunk of box.replay) {
        if (chunk && chunk.byteLength) await writer.write(chunk);
      }
      box.writer = writer;
    } catch (err) {
      box.writer = null;
      closeSocket(socket);
      if (!box.replayable) {
        shutdown(state);
        return;
      }
      return attempt(index + 1);
    }

    const received = await pumpRemote(state, socket);
    box.writer = null;

    const retryable =
      received === 0 && !state.headerSent && box.replayable && index + 1 < attempts.length;
    closeSocket(socket);
    if (retryable) return attempt(index + 1);
    shutdown(state);
  };

  attempt(0).catch(() => shutdown(state));

  return async (chunk) => {
    const bytes = toBytes(chunk);

    // Once the far end has spoken there is nothing left to fail over to, so the
    // replay buffer is released instead of growing for the whole session.
    if (state.headerSent) {
      box.replay = [];
      box.bytes = 0;
    } else if (box.replayable) {
      box.bytes += bytes.byteLength;
      if (box.bytes > MAX_REPLAY_BYTES) {
        box.replay = [];
        box.replayable = false;
      } else {
        box.replay.push(bytes);
      }
    }

    if (box.writer) {
      try {
        await box.writer.write(bytes);
      } catch (err) {
        shutdown(state);
      }
      return;
    }

    // No socket yet. A replayable chunk is already queued above; if replay was
    // given up on there is nowhere to put it, and dropping it silently would
    // corrupt the stream, so the session ends honestly instead.
    if (!box.replayable) shutdown(state);
  };
}

/**
 * VLESS UDP frames are already length prefixed the same way TCP DNS is, so the
 * resolver conversation can be piped straight through in both directions.
 */
function openDns(state, head) {
  const socket = connect({ hostname: state.cfg.dns, port: state.cfg.dnsPort });
  state.socket = socket;
  const writer = socket.writable.getWriter();

  writer
    .write(head.payload)
    .then(() => pumpRemote(state, socket))
    .then(() => shutdown(state))
    .catch(() => shutdown(state));

  return async (chunk) => {
    try {
      await writer.write(toBytes(chunk));
    } catch (err) {
      shutdown(state);
    }
  };
}

async function pumpRemote(state, socket) {
  let received = 0;
  try {
    await socket.readable.pipeTo(
      new WritableStream({
        write(chunk) {
          if (state.ws.readyState !== WS_OPEN) throw new Error("websocket closed");
          const bytes = toBytes(chunk);
          received += bytes.byteLength;
          if (state.headerSent) {
            state.ws.send(bytes);
          } else {
            state.headerSent = true;
            state.ws.send(concat(VLESS_RESPONSE, bytes));
          }
        },
      })
    );
  } catch (err) {
    /* connection reset, refused or torn down: caller decides what is next */
  }
  return received;
}

function shutdown(state) {
  if (state.done) return;
  state.done = true;
  closeSocket(state.socket);
  closeWs(state.ws);
}

function closeSocket(socket) {
  if (!socket) return;
  try {
    socket.close();
  } catch (err) {
    /* already gone */
  }
}

function closeWs(ws) {
  try {
    if (ws.readyState === WS_OPEN) ws.close(1000, "done");
  } catch (err) {
    /* already gone */
  }
}

/* ------------------------------------------------------------------- bytes */

function toBytes(data) {
  if (data instanceof Uint8Array) return data;
  if (data instanceof ArrayBuffer) return new Uint8Array(data);
  if (ArrayBuffer.isView(data)) return new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  if (typeof data === "string") return ENCODER.encode(data);
  return new Uint8Array(0);
}

function concat(a, b) {
  const out = new Uint8Array(a.byteLength + b.byteLength);
  out.set(a, 0);
  out.set(b, a.byteLength);
  return out;
}

/* ------------------------------------------------- live endpoint selection */

function isTls(port, cfg) {
  const list = cfg && cfg.tlsPorts && cfg.tlsPorts.length ? cfg.tlsPorts : DEFAULT_TLS_PORTS;
  return list.includes(Number(port));
}

function groupOf(port, cfg) {
  return isTls(port, cfg) ? "tls" : "http";
}

function normaliseList(raw) {
  if (!Array.isArray(raw)) return [];
  const out = [];
  for (const item of raw) {
    if (!item || !item.ip || !item.port) continue;
    out.push({
      ip: String(item.ip),
      port: Number(item.port),
      latency: Number(item.latency || 0),
      colo: item.colo || "CF",
      kind: item.kind || "ip",
    });
  }
  return out;
}

/**
 * Pull the public clean-IP lists through the edge cache. The cache key is the
 * URL, the TTL is SUB_REFRESH, so a thousand clients refreshing at once cost one
 * upstream request per window.
 */
async function fetchSources(cfg) {
  const found = [];
  for (const url of cfg.sources.slice(0, 4)) {
    try {
      const response = await fetch(url, {
        cf: { cacheTtl: cfg.refresh, cacheEverything: true },
        headers: { "user-agent": `${cfg.brand}/1.1` },
      });
      if (!response.ok) continue;
      const body = await response.text();
      for (const line of body.split(/[\r\n]+/)) {
        const hit = /^\s*((?:\d{1,3}\.){3}\d{1,3})(?::(\d{2,5}))?/.exec(line);
        if (!hit) continue;
        const label = /#\s*([A-Za-z0-9 _.-]{1,16})/.exec(line);
        found.push({
          ip: hit[1],
          port: hit[2] ? Number(hit[2]) : 0,
          colo: label ? label[1].trim().slice(0, 8).toUpperCase() : "LIVE",
          latency: 0,
          kind: "live",
        });
        if (found.length >= 120) break;
      }
    } catch (err) {
      /* a dead list is not worth failing a subscription over */
    }
  }
  return found;
}

/**
 * Rotate deterministically inside each refresh window. Everyone who fetches in
 * the same window gets the same answer, which keeps the cache useful, and the
 * next window moves the list along so a blocked address is not served forever.
 */
function rotate(items, cfg) {
  if (items.length < 2) return items;
  const window = Math.floor(Date.now() / (Math.max(60, cfg.refresh) * 1000));
  const offset = window % items.length;
  return items.slice(offset).concat(items.slice(0, offset));
}

async function liveEndpoints(cfg) {
  const baked = cfg.baked;
  let fresh = [];
  if (cfg.live && cfg.sources.length) {
    fresh = rotate(await fetchSources(cfg), cfg);
  }

  const groups = [
    { key: "tls", ports: cfg.tlsPorts, count: cfg.tlsCount },
    { key: "http", ports: cfg.httpPorts, count: cfg.httpCount },
  ];

  const out = [];
  const seen = new Set();
  const take = (bag, item) => {
    if (!item || !item.ip) return;
    const key = `${item.ip}:${item.port}`;
    if (seen.has(key)) return;
    seen.add(key);
    bag.push(item);
  };

  for (const group of groups) {
    if (group.count <= 0 || !group.ports.length) continue;
    const port = group.ports[0];
    const bag = [];

    const bakedGroup = baked.filter((item) => groupOf(item.port, cfg) === group.key);
    const domainGroup = cfg.domains.map((domain) => ({
      ip: domain,
      port,
      latency: 0,
      colo: "AUTO",
      kind: "domain",
    }));
    const freshGroup = fresh.map((item) => ({
      ...item,
      port: item.port && groupOf(item.port, cfg) === group.key ? item.port : port,
    }));

    // Reserve one slot for a self-healing hostname and one for a live address
    // whenever the group is big enough to spare them. The rest stay on the
    // measured, bot-verified addresses.
    const domainSlots = group.count >= 2 && domainGroup.length ? 1 : 0;
    const freshSlots = group.count >= 3 && freshGroup.length ? 1 : 0;
    const bakedSlots = Math.max(0, group.count - domainSlots - freshSlots);

    for (const item of bakedGroup.slice(0, bakedSlots)) take(bag, item);
    for (const item of domainGroup.slice(0, domainSlots)) take(bag, item);
    for (const item of freshGroup.slice(0, freshSlots)) take(bag, item);

    // Top up from anything left so the user always receives a full set.
    for (const item of [...bakedGroup, ...freshGroup, ...domainGroup]) {
      if (bag.length >= group.count) break;
      take(bag, item);
    }

    out.push(...bag.slice(0, group.count));
  }

  return out.length ? out : baked;
}

/* -------------------------------------------------------------------- http */

async function handleHttp(request, cfg) {
  const url = new URL(request.url);
  const segments = url.pathname.split("/").filter(Boolean);

  if ((segments[0] || "").toLowerCase() !== cfg.uuid) return landing(cfg);

  const kind = (segments[1] || "sub").toLowerCase();

  if (kind === "health") {
    return jsonResponse({
      ok: true,
      brand: cfg.brand,
      host: cfg.host,
      build: cfg.build,
      endpoints: cfg.baked.length,
      domains: cfg.domains.length,
      sources: cfg.sources.length,
      refresh: cfg.refresh,
      proxies: cfg.proxies.length,
      colo: request.cf && request.cf.colo ? request.cf.colo : null,
    });
  }

  if (kind === "probe") {
    return jsonResponse(await probe(cfg));
  }

  const endpoints = await liveEndpoints(cfg);

  if (kind === "endpoints") {
    return jsonResponse({ count: endpoints.length, endpoints });
  }

  if (kind === "clash") {
    return new Response(buildClash(cfg, endpoints), {
      headers: { "content-type": "text/yaml; charset=utf-8" },
    });
  }

  if (kind === "singbox" || kind === "sing-box") {
    return jsonResponse(buildSingbox(cfg, endpoints));
  }

  const links = buildLinks(cfg, endpoints).join("\n");

  if (kind === "raw") {
    return new Response(links, { headers: { "content-type": "text/plain; charset=utf-8" } });
  }

  return new Response(btoa(unescape(encodeURIComponent(links))), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "profile-update-interval": "6",
      "profile-title": cfg.brand,
      "cache-control": "no-store",
    },
  });
}

function landing(cfg) {
  const body = `<!doctype html><html lang="en"><head><meta charset="utf-8">` +
    `<meta name="viewport" content="width=device-width,initial-scale=1">` +
    `<title>${cfg.brand}</title></head><body style="font-family:system-ui;padding:3rem;">` +
    `<h1>${cfg.brand}</h1><p>Nothing to see here.</p></body></html>`;
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

/**
 * Outbound reachability, measured from inside the worker. This is the check that
 * tells the bot whether the tunnel can actually carry traffic, and which relays
 * are usable right now.
 */
async function probe(cfg) {
  let direct = { ok: false, error: "not attempted" };
  for (const target of PROBE_TARGETS) {
    direct = await tcpProbe(target.hostname, target.port, target.host);
    if (direct.ok) break;
  }

  const relays = [];
  for (const raw of cfg.proxies.slice(0, 4)) {
    const target = splitHostPort(raw, 443);
    const result = await tcpProbe(target.hostname, target.port, "");
    relays.push({ target: raw, ...result });
  }

  return {
    ok: Boolean(direct.ok),
    direct,
    relays,
    usable_relays: relays.filter((item) => item.ok).length,
  };
}

async function tcpProbe(hostname, port, readBackHost) {
  const started = Date.now();
  let socket = null;
  try {
    socket = connect({ hostname, port });
    if (socket.opened) await withTimeout(socket.opened, 5000);

    if (readBackHost) {
      const writer = socket.writable.getWriter();
      await writer.write(
        ENCODER.encode(
          `GET / HTTP/1.1\r\nHost: ${readBackHost}\r\nUser-Agent: AutoVless\r\n` +
            "Accept: */*\r\nConnection: close\r\n\r\n"
        )
      );
      writer.releaseLock();
      const reader = socket.readable.getReader();
      const first = await withTimeout(reader.read(), 5000);
      reader.releaseLock();
      if (first.done || !first.value || !first.value.byteLength) {
        closeSocket(socket);
        return { ok: false, ms: Date.now() - started, error: "no data" };
      }
    }

    closeSocket(socket);
    return { ok: true, ms: Date.now() - started };
  } catch (err) {
    closeSocket(socket);
    return { ok: false, ms: Date.now() - started, error: String((err && err.message) || err) };
  }
}

function withTimeout(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

/* ------------------------------------------------------------ config export */

function remark(cfg, endpoint, index) {
  const secure = isTls(endpoint.port, cfg);
  let badge = secure ? "\u26a1" : "\ud83d\udfe1";
  if (endpoint.kind === "domain") badge = "\ud83c\udf00";
  if (endpoint.kind === "live") badge = "\ud83d\udd04";
  const ping = endpoint.latency ? `${Math.round(Number(endpoint.latency))}ms` : "auto";
  const tail = secure ? "" : ` | \ud83d\udd0c${endpoint.port}`;
  return `@${cfg.brand} | ${badge} VLESS | \ud83c\udf0d GLOBAL | ${ping} | ${endpoint.colo || "CF"}${tail} | #${index}`;
}

function buildLinks(cfg, endpoints) {
  const links = [];
  endpoints.forEach((endpoint, position) => {
    const secure = isTls(endpoint.port, cfg);
    const params = new URLSearchParams({
      encryption: "none",
      security: secure ? "tls" : "none",
      type: "ws",
      host: cfg.host,
      path: cfg.wsPath,
    });
    if (secure) {
      params.set("sni", cfg.host);
      params.set("fp", "chrome");
      params.set("alpn", "http/1.1");
    }
    const label = encodeURIComponent(remark(cfg, endpoint, position + 1));
    links.push(`vless://${cfg.uuid}@${endpoint.ip}:${endpoint.port}?${params.toString()}#${label}`);
  });
  return links;
}

function buildClash(cfg, endpoints) {
  const proxies = [];
  const names = [];

  endpoints.forEach((endpoint, position) => {
    const secure = isTls(endpoint.port, cfg);
    const name = remark(cfg, endpoint, position + 1).replace(/"/g, "'");
    names.push(`      - "${name}"`);
    const lines = [
      `  - name: "${name}"`,
      "    type: vless",
      `    server: ${endpoint.ip}`,
      `    port: ${endpoint.port}`,
      `    uuid: ${cfg.uuid}`,
      "    udp: true",
      `    tls: ${secure ? "true" : "false"}`,
    ];
    if (secure) {
      lines.push(`    servername: ${cfg.host}`, "    client-fingerprint: chrome");
    }
    lines.push(
      "    network: ws",
      "    ws-opts:",
      `      path: "${cfg.wsPath}"`,
      "      headers:",
      `        Host: ${cfg.host}`
    );
    proxies.push(lines.join("\n"));
  });

  return [
    `# ${cfg.brand} - built on your own Cloudflare account`,
    "mixed-port: 7890",
    "allow-lan: false",
    "mode: rule",
    "log-level: warning",
    "proxies:",
    proxies.join("\n"),
    "proxy-groups:",
    `  - name: "${cfg.brand}"`,
    "    type: url-test",
    "    url: http://cp.cloudflare.com/generate_204",
    "    interval: 300",
    "    tolerance: 50",
    "    proxies:",
    names.join("\n"),
    "rules:",
    `  - MATCH,${cfg.brand}`,
    "",
  ].join("\n");
}

function buildSingbox(cfg, endpoints) {
  const outbounds = endpoints.map((endpoint, position) => {
    const secure = isTls(endpoint.port, cfg);
    const item = {
      type: "vless",
      tag: remark(cfg, endpoint, position + 1),
      server: endpoint.ip,
      server_port: Number(endpoint.port),
      uuid: cfg.uuid,
      packet_encoding: "xudp",
      transport: {
        type: "ws",
        path: cfg.wsPath,
        headers: { Host: cfg.host },
        early_data_header_name: "Sec-WebSocket-Protocol",
      },
    };
    if (secure) {
      item.tls = {
        enabled: true,
        server_name: cfg.host,
        utls: { enabled: true, fingerprint: "chrome" },
      };
    }
    return item;
  });
  return { outbounds };
}

/* --------------------------------------------------------------- responses */

function textResponse(body, status) {
  return new Response(body, {
    status: status || 200,
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(payload, null, 2), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

import { connect } from "cloudflare:sockets";

const ENC = new TextEncoder();
const DEC = new TextDecoder();
const OPEN = 1;
const VLESS_OK = new Uint8Array([0, 0]);
const CONNECT_TIMEOUT = 6500;
const FIRST_BYTE_TIMEOUT = 4500;
const MAX_REPLAY = 768 * 1024;

export default {
  async fetch(request, env) {
    try {
      if (request.method === "OPTIONS") return response("", 204);
      const cfg = config(env, request);
      if (!cfg.uuidBytes) return response("worker is not configured", 500);
      if ((request.headers.get("upgrade") || "").toLowerCase() === "websocket") return tunnel(request, cfg);
      return http(request, cfg);
    } catch (_) {
      return response("bad request", 400);
    }
  },
};

function config(env, request) {
  const url = new URL(request.url);
  const uuid = String(env.UUID || "").trim().toLowerCase();
  return {
    uuid, uuidBytes: uuidBytes(uuid),
    proxies: list(url.searchParams.get("proxyip") || env.PROXY_IP || env.PROXYIP),
    host: String(env.SUB_HOST || url.hostname).trim(),
    brand: String(env.BRAND || "AutoVless").trim(),
    path: String(env.WS_PATH || "/?ed=2560"),
    dns: String(env.DNS_SERVER || "8.8.8.8").trim(),
    baked: normalise(json(env.ENDPOINTS, [])),
    domains: list(env.CLEAN_DOMAINS), sources: list(env.SUB_SOURCES),
    refresh: integer(env.SUB_REFRESH, 180),
    tlsPorts: ints(env.TLS_PORTS, [443]), httpPorts: ints(env.HTTP_PORTS, [80]),
    tlsCount: integer(env.TLS_COUNT, 6), httpCount: integer(env.HTTP_COUNT, 3),
    build: String(env.BUILD_ID || "1"), live: url.searchParams.get("fresh") !== "0",
  };
}

function list(value) { return String(value || "").split(/[\s,;\n]+/).map(x => x.trim()).filter(Boolean); }
function ints(value, fallback) { const out = list(value).map(Number).filter(x => Number.isInteger(x) && x > 0); return out.length ? out : fallback; }
function integer(value, fallback) { const n = Number.parseInt(value, 10); return Number.isFinite(n) && n > 0 ? n : fallback; }
function json(value, fallback) { try { const x = JSON.parse(value || "null"); return x == null ? fallback : x; } catch (_) { return fallback; } }
function uuidBytes(value) {
  const hex = String(value).replace(/[^0-9a-f]/gi, "");
  if (hex.length !== 32) return null;
  return Uint8Array.from({ length: 16 }, (_, i) => Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16));
}
function bytes(value) {
  if (value instanceof Uint8Array) return value;
  if (value instanceof ArrayBuffer) return new Uint8Array(value);
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer, value.byteOffset, value.byteLength);
  return typeof value === "string" ? ENC.encode(value) : new Uint8Array();
}
function join(a, b) { const out = new Uint8Array(a.byteLength + b.byteLength); out.set(a); out.set(b, a.byteLength); return out; }
function timeout(promise, ms) { return Promise.race([promise, new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))]); }
function closeSocket(socket) { try { if (socket) socket.close(); } catch (_) {} }
function closeWs(ws) { try { if (ws && ws.readyState === OPEN) ws.close(1000, "done"); } catch (_) {} }

function tunnel(request, cfg) {
  const pair = new WebSocketPair();
  const client = pair[0], ws = pair[1];
  ws.accept();
  const state = { ws, cfg, header: new Uint8Array(), send: null, closed: false, socket: null };
  readable(ws, request.headers.get("sec-websocket-protocol") || "").pipeTo(new WritableStream({
    write: chunk => clientChunk(state, chunk),
    close: () => shutdown(state), abort: () => shutdown(state),
  })).catch(() => shutdown(state));
  return new Response(null, { status: 101, webSocket: client });
}

function readable(ws, early) {
  let cancelled = false;
  return new ReadableStream({
    start(controller) {
      ws.addEventListener("message", e => { if (!cancelled) { try { controller.enqueue(bytes(e.data)); } catch (_) {} } });
      ws.addEventListener("close", () => { if (!cancelled) { try { controller.close(); } catch (_) {} } });
      ws.addEventListener("error", () => { try { controller.error(new Error("websocket")); } catch (_) {} });
      const first = earlyData(early); if (first.byteLength) controller.enqueue(first);
    },
    cancel() { cancelled = true; closeWs(ws); },
  });
}
function earlyData(raw) {
  try {
    const value = String(raw || "").replace(/-/g, "+").replace(/_/g, "/");
    if (!value) return new Uint8Array();
    const decoded = atob(value); return Uint8Array.from(decoded, x => x.charCodeAt(0));
  } catch (_) { return new Uint8Array(); }
}

async function clientChunk(state, chunk) {
  if (state.send) return state.send(bytes(chunk));
  state.header = join(state.header, bytes(chunk));
  const head = parseHeader(state.header, state.cfg.uuidBytes);
  if (head.partial) return;
  if (head.error) throw new Error(head.error);
  state.header = new Uint8Array();
  if (head.udp) {
    if (head.port !== 53) throw new Error("udp is dns-only");
    state.send = dnsSession(state, head.payload);
  } else {
    state.send = tcpSession(state, head);
  }
}

function parseHeader(raw, expected) {
  if (raw.length < 24) return { partial: true };
  for (let i = 0; i < 16; i++) if (raw[i + 1] !== expected[i]) return { error: "auth" };
  let p = 18 + raw[17];
  if (raw.length < p + 4) return { partial: true };
  const command = raw[p++]; if (command !== 1 && command !== 2) return { error: "command" };
  const port = (raw[p] << 8) | raw[p + 1]; p += 2;
  const type = raw[p++]; let host = "";
  if (type === 1) { if (raw.length < p + 4) return { partial: true }; host = Array.from(raw.slice(p, p + 4)).join("."); p += 4; }
  else if (type === 2) { if (raw.length < p + 1) return { partial: true }; const n = raw[p++]; if (raw.length < p + n) return { partial: true }; host = DEC.decode(raw.slice(p, p + n)); p += n; }
  else if (type === 3) { if (raw.length < p + 16) return { partial: true }; const parts = []; for (let i = 0; i < 8; i++) parts.push(((raw[p + i * 2] << 8) | raw[p + i * 2 + 1]).toString(16)); host = parts.join(":"); p += 16; }
  else return { error: "address" };
  return { udp: command === 2, host, port, payload: raw.slice(p) };
}

function relayTarget(raw, port) {
  const value = String(raw || "").trim();
  if (!value) return null;
  if (value.startsWith("[")) { const end = value.indexOf("]"); return { hostname: value.slice(1, end), port: value[end + 1] === ":" ? integer(value.slice(end + 2), port) : port }; }
  const match = /^([^:]+):(\d+)$/.exec(value);
  return match ? { hostname: match[1], port: integer(match[2], port) } : { hostname: value, port };
}

function tcpSession(state, head) {
  const attempts = [{ hostname: head.host, port: head.port }, ...state.cfg.proxies.map(x => relayTarget(x, head.port)).filter(Boolean)];
  const session = { replay: head.payload.byteLength ? [head.payload] : [], size: head.payload.byteLength, trial: null, active: null, ready: false };
  const run = async () => {
    for (const target of attempts) {
      if (state.closed) return;
      let socket, writer, reader;
      try {
        socket = connect(target); state.socket = socket;
        if (socket.opened) await timeout(socket.opened, CONNECT_TIMEOUT);
        writer = socket.writable.getWriter(); session.trial = writer;
        for (const chunk of session.replay) if (chunk.byteLength) await writer.write(chunk);
        reader = socket.readable.getReader();
        const first = await timeout(reader.read(), FIRST_BYTE_TIMEOUT);
        if (first.done || !first.value || !first.value.byteLength) throw new Error("no first byte");
        session.trial = null; session.active = writer; session.ready = true; session.replay = []; session.size = 0;
        if (state.ws.readyState !== OPEN) throw new Error("closed");
        state.ws.send(join(VLESS_OK, bytes(first.value)));
        while (true) {
          const next = await reader.read();
          if (next.done) break;
          if (state.ws.readyState !== OPEN) break;
          state.ws.send(bytes(next.value));
        }
        shutdown(state); return;
      } catch (_) {
        session.trial = null;
        try { if (reader) reader.releaseLock(); } catch (_) {}
        try { if (writer) writer.releaseLock(); } catch (_) {}
        closeSocket(socket);
      }
    }
    shutdown(state);
  };
  run().catch(() => shutdown(state));
  return async chunk => {
    if (session.ready && session.active) { try { await session.active.write(chunk); } catch (_) { shutdown(state); } return; }
    session.size += chunk.byteLength;
    if (session.size > MAX_REPLAY) return shutdown(state);
    session.replay.push(chunk);
    if (session.trial) { try { await session.trial.write(chunk); } catch (_) {} }
  };
}

function dnsSession(state, payload) {
  const socket = connect({ hostname: state.cfg.dns, port: 53 }); state.socket = socket;
  const writer = socket.writable.getWriter();
  (async () => {
    try {
      if (payload.byteLength) await writer.write(payload);
      let first = true;
      const reader = socket.readable.getReader();
      while (true) { const item = await reader.read(); if (item.done) break; const chunk = bytes(item.value); state.ws.send(first ? join(VLESS_OK, chunk) : chunk); first = false; }
    } catch (_) {} finally { shutdown(state); }
  })();
  return async chunk => { try { await writer.write(chunk); } catch (_) { shutdown(state); } };
}
function shutdown(state) { if (state.closed) return; state.closed = true; closeSocket(state.socket); closeWs(state.ws); }

function normalise(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.filter(x => x && x.ip && x.port).map(x => ({
    ip: String(x.ip), port: Number(x.port), latency: Number(x.latency || 0), jitter: Number(x.jitter || 0),
    score: Number(x.score || x.latency || 99999), colo: String(x.colo || "CF"), kind: String(x.kind || "ip"),
  })).sort((a, b) => a.score - b.score);
}
function tls(port, cfg) { return cfg.tlsPorts.includes(Number(port)); }
function validIPv4(value) { const p = String(value).split("."); return p.length === 4 && p.every(x => /^\d{1,3}$/.test(x) && Number(x) >= 0 && Number(x) <= 255); }
async function sourceEndpoints(cfg) {
  const out = [];
  for (const url of cfg.sources.slice(0, 3)) {
    try {
      const res = await fetch(url, { cf: { cacheEverything: true, cacheTtl: cfg.refresh }, headers: { "user-agent": `${cfg.brand}/2.0` } });
      if (!res.ok || (res.headers.get("content-type") || "").toLowerCase().includes("html")) continue;
      for (const line of (await res.text()).split(/[\r\n]+/).slice(0, 2000)) {
        const match = /^\s*((?:\d{1,3}\.){3}\d{1,3})(?::(\d{2,5}))?/.exec(line);
        if (match && validIPv4(match[1])) out.push({ ip: match[1], port: Number(match[2] || 0), latency: 0, score: 99998, colo: "LIVE", kind: "live" });
        if (out.length >= 100) break;
      }
    } catch (_) {}
  }
  const window = Math.floor(Date.now() / (Math.max(60, cfg.refresh) * 1000));
  return out.length ? out.slice(window % out.length).concat(out.slice(0, window % out.length)) : out;
}
async function endpoints(cfg) {
  const live = cfg.live ? await sourceEndpoints(cfg) : [];
  const output = [], seen = new Set();
  const take = (bag, item) => { if (!item || !item.ip) return; const key = `${item.ip}:${item.port}`; if (!seen.has(key)) { seen.add(key); bag.push(item); } };
  for (const group of [{ ports: cfg.tlsPorts, count: cfg.tlsCount, secure: true }, { ports: cfg.httpPorts, count: cfg.httpCount, secure: false }]) {
    if (!group.count || !group.ports.length) continue;
    const port = group.ports[0], bag = [];
    const baked = cfg.baked.filter(x => tls(x.port, cfg) === group.secure);
    const domains = cfg.domains.map(ip => ({ ip, port, latency: 0, score: 99997, colo: "AUTO", kind: "domain" }));
    const fresh = live.map(x => ({ ...x, port: x.port && tls(x.port, cfg) === group.secure ? x.port : port }));
    const domainSlots = group.count >= 2 && domains.length ? 1 : 0;
    const liveSlots = group.count >= 4 && fresh.length ? 1 : 0;
    baked.slice(0, group.count - domainSlots - liveSlots).forEach(x => take(bag, x));
    domains.slice(0, domainSlots).forEach(x => take(bag, x));
    fresh.slice(0, liveSlots).forEach(x => take(bag, x));
    [...baked, ...domains, ...fresh].forEach(x => { if (bag.length < group.count) take(bag, x); });
    output.push(...bag.slice(0, group.count));
  }
  return output.length ? output : cfg.baked;
}

async function http(request, cfg) {
  const url = new URL(request.url), parts = url.pathname.split("/").filter(Boolean);
  if ((parts[0] || "").toLowerCase() !== cfg.uuid) return response(`<h1>${escapeHtml(cfg.brand)}</h1>`, 200, "text/html; charset=utf-8");
  const kind = (parts[1] || "sub").toLowerCase();
  if (kind === "health") return jsonResponse({ ok: true, version: 2, build: cfg.build, endpoints: cfg.baked.length, proxies: cfg.proxies.length, sources: cfg.sources.length, colo: request.cf?.colo || null });
  if (kind === "probe") return jsonResponse(await probe(cfg));
  const eps = await endpoints(cfg);
  if (kind === "endpoints") return jsonResponse({ count: eps.length, endpoints: eps });
  const links = buildLinks(cfg, eps);
  if (kind === "raw") return response(links.join("\n"));
  if (kind === "clash") return response(buildClash(cfg, eps), 200, "text/yaml; charset=utf-8");
  if (kind === "singbox" || kind === "sing-box") return jsonResponse(buildSingbox(cfg, eps));
  return response(btoa(unescape(encodeURIComponent(links.join("\n")))), 200, "text/plain; charset=utf-8", { "profile-update-interval": "3", "profile-title": cfg.brand, "cache-control": "no-store" });
}
async function probe(cfg) {
  const direct = await socketProbe("www.wikipedia.org", 80, "www.wikipedia.org");
  const relays = [];
  for (const raw of cfg.proxies.slice(0, 6)) { const target = relayTarget(raw, 443); relays.push({ target: raw, ...(await socketProbe(target.hostname, target.port, "")) }); }
  return { ok: direct.ok, direct, relays, usable_relays: relays.filter(x => x.ok).length };
}
async function socketProbe(hostname, port, host) {
  const started = Date.now(); let socket;
  try {
    socket = connect({ hostname, port }); if (socket.opened) await timeout(socket.opened, 5000);
    if (host) { const writer = socket.writable.getWriter(); await writer.write(ENC.encode(`GET / HTTP/1.1\r\nHost: ${host}\r\nConnection: close\r\n\r\n`)); const reader = socket.readable.getReader(); const item = await timeout(reader.read(), 5000); if (item.done || !item.value?.byteLength) throw new Error("no data"); }
    closeSocket(socket); return { ok: true, ms: Date.now() - started };
  } catch (error) { closeSocket(socket); return { ok: false, ms: Date.now() - started, error: String(error?.message || error) }; }
}

function label(cfg, ep, i) { const secure = tls(ep.port, cfg); const badge = ep.kind === "domain" ? "🌀" : ep.kind === "live" ? "🔄" : secure ? "⚡" : "🟡"; const ping = ep.latency ? `${Math.round(ep.latency)}ms` : "auto"; return `@${cfg.brand} | ${badge} VLESS | 🌍 GLOBAL | ${ping} | ${ep.colo || "CF"} | #${i}`; }
function buildLinks(cfg, eps) { return eps.map((ep, i) => { const secure = tls(ep.port, cfg); const q = new URLSearchParams({ encryption: "none", security: secure ? "tls" : "none", type: "ws", host: cfg.host, path: cfg.path }); if (secure) { q.set("sni", cfg.host); q.set("fp", "chrome"); q.set("alpn", "http/1.1"); } return `vless://${cfg.uuid}@${ep.ip}:${ep.port}?${q}#${encodeURIComponent(label(cfg, ep, i + 1))}`; }); }
function buildClash(cfg, eps) {
  const blocks = [], names = [];
  eps.forEach((ep, i) => { const name = label(cfg, ep, i + 1).replace(/"/g, "'"); names.push(`      - "${name}"`); const secure = tls(ep.port, cfg); const x = [`  - name: "${name}"`, "    type: vless", `    server: ${ep.ip}`, `    port: ${ep.port}`, `    uuid: ${cfg.uuid}`, "    udp: true", `    tls: ${secure}`]; if (secure) x.push(`    servername: ${cfg.host}`, "    client-fingerprint: chrome"); x.push("    network: ws", "    ws-opts:", `      path: "${cfg.path}"`, "      headers:", `        Host: ${cfg.host}`); blocks.push(x.join("\n")); });
  return [`# ${cfg.brand}`, "mixed-port: 7890", "mode: rule", "proxies:", blocks.join("\n"), "proxy-groups:", `  - name: "${cfg.brand}"`, "    type: url-test", "    url: http://cp.cloudflare.com/generate_204", "    interval: 180", "    tolerance: 80", "    proxies:", names.join("\n"), "rules:", `  - MATCH,${cfg.brand}`, ""].join("\n");
}
function buildSingbox(cfg, eps) { return { outbounds: eps.map((ep, i) => { const item = { type: "vless", tag: label(cfg, ep, i + 1), server: ep.ip, server_port: ep.port, uuid: cfg.uuid, packet_encoding: "xudp", transport: { type: "ws", path: cfg.path, headers: { Host: cfg.host }, early_data_header_name: "Sec-WebSocket-Protocol" } }; if (tls(ep.port, cfg)) item.tls = { enabled: true, server_name: cfg.host, utls: { enabled: true, fingerprint: "chrome" } }; return item; }) }; }
function escapeHtml(value) { return String(value).replace(/[&<>"']/g, x => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[x])); }
function headers(extra = {}) { return { "access-control-allow-origin": "*", "access-control-allow-methods": "GET,HEAD,OPTIONS", ...extra }; }
function response(body, status = 200, type = "text/plain; charset=utf-8", extra = {}) { return new Response(body, { status, headers: headers({ "content-type": type, ...extra }) }); }
function jsonResponse(value) { return response(JSON.stringify(value, null, 2), 200, "application/json; charset=utf-8"); }

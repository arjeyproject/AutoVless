/**
 * AutoVless edge worker.
 *
 * VLESS, Trojan *and* Shadowsocks over WebSocket, running on the user's own
 * Cloudflare account. None of the traffic touches the operator's VPS:
 *
 *   client -> clean CF IP:443|80 -> CF edge -> this worker -> destination
 *
 * Two protocols share one path and are told apart by the first frame: a Trojan
 * client opens with 56 hex characters and a CRLF, and nothing else can, because
 * a VLESS header starts with a zero byte. So the worker sniffs instead of
 * asking, and the same address, port and path serve both. That matters because a
 * VLESS handshake and a Trojan handshake look nothing alike to a DPI box: a
 * network that has learned to kill one frequently still passes the other.
 *
 * Shadowsocks is the third shape and it cannot be sniffed: its first 32 bytes
 * are random salt, which is indistinguishable from anything. It therefore gets
 * its own WebSocket path, SS_PATH ("/ss" by default), and fetch() dispatches on
 * that before any sniffing happens. The master key arrives pre-derived as SS_KEY
 * hex, because EVP_BytesToKey needs MD5 and WebCrypto has none; from there it is
 * HKDF-SHA1 and AES-256-GCM, both native. The same code lives in
 * worker/shadowsocks.js, where scripts/test-shadowsocks.mjs checks it against an
 * independent client.
 *
 * Trojan and Shadowsocks are only ever offered on TLS ports. Their cover story is
 * "this is ordinary HTTPS", and on a plain port there is no TLS record to hide
 * inside. TROJAN_PASSWORD defaults to UUID, so an existing panel starts speaking
 * Trojan the moment it picks up this bundle.
 *
 * The subscription this worker serves is not a frozen list. Every fetch blends
 * three sources of entry addresses:
 *
 *   1. ENDPOINTS      verified by the bot at build time, with real latency
 *   2. CLEAN_DOMAINS  hostnames whose DNS is kept pointed at healthy edges
 *   3. SUB_SOURCES    public clean-IP lists, fetched through the edge cache
 *
 * Ports are spread on purpose, so the day 443 is filtered on someone's network
 * they still have a second and third way in.
 *
 * AI destinations get their own outbound path. A Worker cannot open a socket to
 * a Cloudflare owned address, and chatgpt.com, openai.com, claude.ai and
 * perplexity.ai are all Cloudflare-fronted, so those hosts go relay-first. The
 * relay is pinned rather than picked: stickyOrder() rotates the relay list by a
 * hash of the destination hostname, so one host always exits through one relay
 * and the site sees a steady address. AI_PROXY_IP pins a dedicated relay.
 *
 * Paths, all under /<uuid>/ :
 *   sub | raw        VLESS subscription, base64 or plain
 *   trojan           Trojan subscription (TLS endpoints only)
 *   ss               Shadowsocks subscription (TLS endpoints only)
 *   mix              every protocol in one subscription
 *   clash | singbox  ready made client configs
 *   endpoints        the live entry list as JSON
 *   health | probe | ai   diagnostics the bot reads
 *
 * Bindings (plain text vars, all optional except UUID):
 *   UUID             the single account id allowed on this worker
 *   TROJAN_PASSWORD  trojan password. Defaults to UUID.
 *   TROJAN           "false" turns the trojan inbound and its paths off
 *   SS               "false" turns the shadowsocks inbound off
 *   SS_KEY           shadowsocks master key, 64 hex characters
 *   SS_PATH          websocket path shadowsocks listens on (default /ss)
 *   SS_METHOD        cipher name used in generated links (aes-256-gcm)
 *   SS_PASSWORD      password used in generated links (the key's source)
 *   PROXY_IP         comma separated relay list, e.g. "1.2.3.4:443,proxy.example.com"
 *   AI_PROXY_IP      relays reserved for AI destinations. Falls back to PROXY_IP.
 *   AI_DOMAINS       extra AI hostnames to route this way, comma separated
 *   AI_ROUTE         "false" turns the whole behaviour off
 *   SUB_HOST         hostname used inside generated configs (defaults to request host)
 *   BRAND            label used in config remarks
 *   WS_PATH          websocket path used inside generated configs
 *   ENDPOINTS        JSON array of {ip, port, latency, colo, kind}
 *   SUB_SOURCES      comma separated URLs of clean-IP lists
 *   CLEAN_DOMAINS    comma separated self-healing hostnames
 *   SUB_REFRESH      seconds the fetched lists are cached (default 300)
 *   TLS_PORTS        comma separated TLS ports offered in configs
 *   HTTP_PORTS       comma separated plain ports offered in configs
 *   TLS_COUNT        how many TLS configs to emit
 *   HTTP_COUNT       how many plain configs to emit
 *   DNS_SERVER       TCP DNS resolver for UDP/53 traffic (default 8.8.8.8)
 *   FALLBACK_HOST    shown on the landing page
 *   BUILD_ID         opaque build stamp reported by /health
 */

import { connect } from "cloudflare:sockets";

const VLESS_RESPONSE = new Uint8Array([0, 0]);
const DEFAULT_TLS_PORTS = [443, 2053, 2083, 2087, 2096, 8443];
const DEFAULT_HTTP_PORTS = [80, 8080, 8880, 2052, 2082, 2086, 2095];
// More than one port per group by default, for the reason in the header.
const SERVE_TLS_PORTS = [443, 2053, 8443];
const SERVE_HTTP_PORTS = [80, 8080];
const WS_OPEN = 1;
const CONNECT_TIMEOUT_MS = 8000;
// 56 hex characters of sha224, then CRLF. The whole trojan preamble.
const TROJAN_HEAD = 58;

/**
 * Destinations that need the relay path.
 *
 * Some of these are Cloudflare-fronted, so a Worker literally cannot reach them
 * directly. The rest are reachable but score a Cloudflare datacentre egress as
 * suspicious, which shows up as constant re-logins. Both are fixed by exiting
 * through one steady relay. Matching is by suffix.
 */
const DEFAULT_AI_DOMAINS = [
  "openai.com",
  "chatgpt.com",
  "oaistatic.com",
  "oaiusercontent.com",
  "sora.com",
  "gemini.google.com",
  "bard.google.com",
  "aistudio.google.com",
  "makersuite.google.com",
  "generativelanguage.googleapis.com",
  "ai.google.dev",
  "labs.google",
  "notebooklm.google.com",
  "anthropic.com",
  "claude.ai",
  "claudeusercontent.com",
  "perplexity.ai",
  "pplx.ai",
  "x.ai",
  "grok.com",
  "copilot.microsoft.com",
  "githubcopilot.com",
  "midjourney.com",
  "huggingface.co",
  "runwayml.com",
  "suno.com",
  "elevenlabs.io",
  "cursor.com",
  "poe.com",
  "character.ai",
  "mistral.ai",
  "cohere.com",
  "together.ai",
  "groq.com",
  "deepseek.com",
  "qwen.ai",
  "kimi.com"
];

/**
 * Client bytes are kept until the destination proves it can talk, so a failover
 * can replay them instead of handing the next relay a half-eaten stream. The cap
 * keeps a big upload from parking megabytes in memory.
 */
const MAX_REPLAY_BYTES = 512 * 1024;

// Outbound reachability targets. None of these may be a Cloudflare address.
const PROBE_TARGETS = [
  { hostname: "www.wikipedia.org", port: 80, host: "www.wikipedia.org" },
  { hostname: "example.com", port: 80, host: "example.com" }
];

const ENCODER = new TextEncoder();
const DECODER = new TextDecoder();

export default {
  async fetch(request, env) {
    try {
      // Preflight is answered before anything else so a browser probe never
      // needs a configured worker to get an answer.
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: corsHeaders() });
      }

      const cfg = readConfig(env, request);
      if (!cfg.uuidBytes) return textResponse("worker is not configured", 500);

      const upgrade = (request.headers.get("Upgrade") || "").toLowerCase();
      if (upgrade === "websocket") {
        // Shadowsocks is dispatched by path, before any sniffing: its first bytes
        // are random salt and cannot be told apart from anything else.
        if (cfg.ssActive && ssPathMatch(new URL(request.url).pathname, cfg.ssPath)) {
          return handleSsTunnel(request, cfg);
        }
        return handleTunnel(request, cfg);
      }
      return await handleHttp(request, cfg);
    } catch (err) {
      return textResponse("bad request", 400);
    }
  }
};

/* ------------------------------------------------------------------ config */

function readConfig(env, request) {
  const url = new URL(request.url);
  const uuid = String(env.UUID || "").trim().toLowerCase();
  const override = url.searchParams.get("proxyip") || pathProxy(url.pathname);
  const proxies = splitList(override || env.PROXY_IP || env.PROXYIP || "");
  const aiOverride = url.searchParams.get("aiproxy") || "";
  const aiProxies = splitList(aiOverride || env.AI_PROXY_IP || "");
  const tlsPorts = intList(env.TLS_PORTS, SERVE_TLS_PORTS);
  const httpPorts = intList(env.HTTP_PORTS, SERVE_HTTP_PORTS);
  const ssKey = ssKeyBytes(env.SS_KEY);
  const ssOn = String(env.SS || "true").toLowerCase() !== "false";

  return {
    uuid,
    uuidBytes: uuidToBytes(uuid),
    // Defaulting to the account uuid is deliberate: a panel built before this
    // bundle existed has no TROJAN_PASSWORD bound, and it still has to start
    // speaking trojan the moment it is re-uploaded, with no migration step.
    trojanPassword: String(env.TROJAN_PASSWORD || env.TROJAN_PASS || uuid).trim(),
    trojan: String(env.TROJAN || "true").toLowerCase() !== "false",
    // Shadowsocks needs its key; without one the inbound stays shut.
    ssKey,
    ssActive: ssOn && !!ssKey,
    ssPath: String(env.SS_PATH || "/ss"),
    ssMethod: String(env.SS_METHOD || "aes-256-gcm").trim() || "aes-256-gcm",
    ssPassword: String(env.SS_PASSWORD || "").trim(),
    proxies,
    aiProxies,
    aiDomains: aiDomainList(env.AI_DOMAINS),
    aiRoute: String(env.AI_ROUTE || "true").toLowerCase() !== "false",
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
    live: url.searchParams.get("fresh") !== "0"
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

/** The built-in AI list plus anything the operator added. Deduplicated. */
function aiDomainList(raw) {
  const extra = splitList(raw).map((item) => item.toLowerCase().replace(/^\.+/, ""));
  return Array.from(new Set([...DEFAULT_AI_DOMAINS, ...extra]));
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

/* ------------------------------------------------------- trojan: sha224 */

/**
 * SHA-224, by hand, because the trojan handshake is defined as exactly that and
 * WebCrypto on Workers does not implement it. SHA-224 is SHA-256 with a
 * different initial state and a truncated output. Memoised per password.
 */
const K256 = new Uint32Array(
  (
    "428a2f98 71374491 b5c0fbcf e9b5dba5 3956c25b 59f111f1 923f82a4 ab1c5ed5 " +
    "d807aa98 12835b01 243185be 550c7dc3 72be5d74 80deb1fe 9bdc06a7 c19bf174 " +
    "e49b69c1 efbe4786 0fc19dc6 240ca1cc 2de92c6f 4a7484aa 5cb0a9dc 76f988da " +
    "983e5152 a831c66d b00327c8 bf597fc7 c6e00bf3 d5a79147 06ca6351 14292967 " +
    "27b70a85 2e1b2138 4d2c6dfc 53380d13 650a7354 766a0abb 81c2c92e 92722c85 " +
    "a2bfe8a1 a81a664b c24b8b70 c76c51a3 d192e819 d6990624 f40e3585 106aa070 " +
    "19a4c116 1e376c08 2748774c 34b0bcb5 391c0cb3 4ed8aa4a 5b9cca4f 682e6ff3 " +
    "748f82ee 78a5636f 84c87814 8cc70208 90befffa a4506ceb bef9a3f7 c67178f2"
  )
    .split(" ")
    .map((word) => parseInt(word, 16))
);

const SHA224_IV = new Uint32Array([
  0xc1059ed8, 0x367cd507, 0x3070dd17, 0xf70e5939, 0xffc00b31, 0x68581511, 0x64f98fa7,
  0xbefa4fa4
]);

const DIGESTS = new Map();

function rotr(value, bits) {
  return ((value >>> bits) | (value << (32 - bits))) >>> 0;
}

function sha224Hex(text) {
  const message = ENCODER.encode(String(text));
  const size = ((message.length + 9 + 63) >> 6) << 6;
  const block = new Uint8Array(size);
  block.set(message);
  block[message.length] = 0x80;
  const view = new DataView(block.buffer);
  const bits = message.length * 8;
  view.setUint32(size - 8, Math.floor(bits / 4294967296));
  view.setUint32(size - 4, bits >>> 0);

  const h = SHA224_IV.slice();
  const w = new Uint32Array(64);

  for (let offset = 0; offset < size; offset += 64) {
    for (let i = 0; i < 16; i++) w[i] = view.getUint32(offset + i * 4);
    for (let i = 16; i < 64; i++) {
      const x = w[i - 15];
      const y = w[i - 2];
      const s0 = (rotr(x, 7) ^ rotr(x, 18) ^ (x >>> 3)) >>> 0;
      const s1 = (rotr(y, 17) ^ rotr(y, 19) ^ (y >>> 10)) >>> 0;
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0;
    }

    let a = h[0];
    let b = h[1];
    let c = h[2];
    let d = h[3];
    let e = h[4];
    let f = h[5];
    let g = h[6];
    let t = h[7];

    for (let i = 0; i < 64; i++) {
      const s1 = (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) >>> 0;
      const ch = ((e & f) ^ (~e & g)) >>> 0;
      const t1 = (t + s1 + ch + K256[i] + w[i]) >>> 0;
      const s0 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) >>> 0;
      const mj = ((a & b) ^ (a & c) ^ (b & c)) >>> 0;
      const t2 = (s0 + mj) >>> 0;
      t = g;
      g = f;
      f = e;
      e = (d + t1) >>> 0;
      d = c;
      c = b;
      b = a;
      a = (t1 + t2) >>> 0;
    }

    h[0] = (h[0] + a) >>> 0;
    h[1] = (h[1] + b) >>> 0;
    h[2] = (h[2] + c) >>> 0;
    h[3] = (h[3] + d) >>> 0;
    h[4] = (h[4] + e) >>> 0;
    h[5] = (h[5] + f) >>> 0;
    h[6] = (h[6] + g) >>> 0;
    h[7] = (h[7] + t) >>> 0;
  }

  let out = "";
  for (let i = 0; i < 7; i++) out += h[i].toString(16).padStart(8, "0");
  return out;
}

function trojanDigest(cfg) {
  const key = cfg.trojanPassword || cfg.uuid;
  let hit = DIGESTS.get(key);
  if (!hit) {
    hit = sha224Hex(key);
    DIGESTS.set(key, hit);
  }
  return hit;
}

/* ------------------------------------------- shadowsocks: aead aes-256-gcm */

/*
 * Framing:  salt(32) || [ len(2) + tag(16) ] [ payload(len) + tag(16) ] ...
 * subkey  = HKDF-SHA1(master, salt, "ss-subkey", 32), one per direction
 * nonce   = 12 byte little-endian counter, advanced after every AEAD operation
 * chunks  cap at 0x3fff bytes
 * The first plaintext bytes are a SOCKS-shaped target address, parsed by the
 * same readSocksAddress the Trojan inbound uses.
 */
const SS_INFO = ENCODER.encode("ss-subkey");
const SS_SALT_BYTES = 32;
const SS_TAG_BYTES = 16;
const SS_MAX_CHUNK = 0x3fff;

function ssKeyBytes(text) {
  const hex = String(text || "").replace(/[^0-9a-f]/gi, "").toLowerCase();
  if (hex.length !== 64) return null;
  const out = new Uint8Array(32);
  for (let i = 0; i < 32; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

async function ssSubkey(master, salt) {
  const base = await crypto.subtle.importKey("raw", master, "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-1", salt, info: SS_INFO },
    base,
    256
  );
  return crypto.subtle.importKey("raw", new Uint8Array(bits), { name: "AES-GCM" }, false, [
    "encrypt",
    "decrypt"
  ]);
}

function ssBump(nonce) {
  for (let i = 0; i < nonce.length; i++) {
    if (++nonce[i] !== 0) break;
  }
}

/** A stateful reader: feed it frames, get back whole plaintext chunks. */
function ssOpener(key) {
  const nonce = new Uint8Array(12);
  let buffer = new Uint8Array(0);
  let expect = -1;

  const open = async (slice) => {
    try {
      const plain = await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: nonce, tagLength: 128 },
        key,
        slice
      );
      return new Uint8Array(plain);
    } catch (err) {
      return null;
    }
  };

  return async function push(chunk) {
    if (chunk && chunk.byteLength) buffer = concat(buffer, chunk);
    const out = [];
    for (;;) {
      if (expect < 0) {
        if (buffer.byteLength < 2 + SS_TAG_BYTES) break;
        const head = await open(buffer.slice(0, 2 + SS_TAG_BYTES));
        if (!head) throw new Error("ss length auth failed");
        ssBump(nonce);
        expect = (head[0] << 8) | head[1];
        if (expect < 1 || expect > SS_MAX_CHUNK) throw new Error("ss chunk size");
        buffer = buffer.slice(2 + SS_TAG_BYTES);
        continue;
      }
      if (buffer.byteLength < expect + SS_TAG_BYTES) break;
      const body = await open(buffer.slice(0, expect + SS_TAG_BYTES));
      if (!body) throw new Error("ss payload auth failed");
      ssBump(nonce);
      buffer = buffer.slice(expect + SS_TAG_BYTES);
      expect = -1;
      if (body.byteLength) out.push(body);
    }
    return out;
  };
}

/** The other direction. Splits anything over the protocol's chunk limit. */
function ssSealer(key) {
  const nonce = new Uint8Array(12);
  const seal = async (plain) => {
    const box = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv: nonce, tagLength: 128 },
      key,
      plain
    );
    ssBump(nonce);
    return new Uint8Array(box);
  };

  return async function push(payload) {
    let rest = payload;
    let out = new Uint8Array(0);
    while (rest.byteLength) {
      const piece = rest.slice(0, SS_MAX_CHUNK);
      rest = rest.slice(piece.byteLength);
      const size = new Uint8Array([(piece.byteLength >> 8) & 0xff, piece.byteLength & 0xff]);
      out = concat(out, await seal(size));
      out = concat(out, await seal(piece));
    }
    return out;
  };
}

async function ssSession(master, clientSalt) {
  const serverSalt = new Uint8Array(SS_SALT_BYTES);
  crypto.getRandomValues(serverSalt);
  return {
    serverSalt,
    read: ssOpener(await ssSubkey(master, clientSalt)),
    write: ssSealer(await ssSubkey(master, serverSalt))
  };
}

function ssPathMatch(pathname, configured) {
  const want = String(configured || "/ss").split("?")[0];
  const got = String(pathname || "/").split("?")[0];
  return got === want || got === want.replace(/\/+$/, "");
}

/**
 * One Shadowsocks session over one WebSocket.
 *
 * The first 32 bytes are the client's salt. After that everything is sealed
 * chunks; the first plaintext is the target address, and from then on the
 * plaintext is the client's stream. Answers go back sealed under our own salt,
 * which rides in front of the first sealed byte - the same "prefix on the first
 * answer" slot VLESS uses for its two byte response header.
 */
function handleSsTunnel(request, cfg) {
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
    mode: "ss",
    prefix: null,
    encode: null,
    spoke: false,
    done: false
  };
  const ss = { salt: new Uint8Array(0), session: null };

  wsReadable(server, "")
    .pipeTo(
      new WritableStream({
        async write(chunk) {
          await onSsChunk(state, ss, chunk);
        },
        close() {
          shutdown(state);
        },
        abort() {
          shutdown(state);
        }
      })
    )
    .catch(() => shutdown(state));

  return new Response(null, { status: 101, webSocket: client });
}

async function onSsChunk(state, ss, chunk) {
  let bytes = toBytes(chunk);
  if (!ss.session) {
    ss.salt = concat(ss.salt, bytes);
    if (ss.salt.byteLength < SS_SALT_BYTES) return;
    const clientSalt = ss.salt.slice(0, SS_SALT_BYTES);
    bytes = ss.salt.slice(SS_SALT_BYTES);
    ss.salt = null;
    ss.session = await ssSession(state.cfg.ssKey, clientSalt);
    state.prefix = ss.session.serverSalt;
    state.encode = ss.session.write;
  }

  // A wrong key throws here, which ends the session: to a prober this endpoint
  // is a web server that hung up.
  const plains = await ss.session.read(bytes);
  for (const plain of plains) {
    if (state.write) {
      await state.write(plain);
      continue;
    }
    state.header = state.header ? concat(state.header, plain) : plain;
    const target = readSocksAddress(state.header, 0);
    if (target.partial) continue;
    if (target.error) throw new Error(target.error);
    const head = {
      isUdp: false,
      port: target.port,
      address: target.address,
      hostname: target.hostname,
      payload: state.header.slice(target.cursor)
    };
    state.header = null;
    state.write = openTcp(state, head);
  }
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
    // Which protocol this session turned out to be, the bytes that have to be
    // prepended to the first answer (VLESS wants two, trojan wants none), and
    // whether the far end has said anything yet. That last flag is what decides
    // if a failover is still allowed.
    mode: "",
    prefix: null,
    encode: null,
    spoke: false,
    done: false
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
        }
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
    }
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

/**
 * Which protocol is this? A trojan client opens with 56 hex characters and CRLF;
 * a VLESS client opens with a zero byte. "" means the answer needs more bytes.
 */
function sniff(bytes) {
  const seen = Math.min(bytes.length, 56);
  for (let i = 0; i < seen; i++) {
    const c = bytes[i];
    const hex =
      (c >= 48 && c <= 57) || (c >= 97 && c <= 102) || (c >= 65 && c <= 70);
    if (!hex) return "vless";
  }
  if (bytes.length < TROJAN_HEAD) return "";
  if (bytes[56] === 13 && bytes[57] === 10) return "trojan";
  return "vless";
}

async function onClientChunk(state, chunk) {
  if (state.write) {
    await state.write(chunk);
    return;
  }

  // Some clients split the header across frames, especially when early data is
  // in play. Waiting for the rest beats killing the session.
  state.header = state.header ? concat(state.header, toBytes(chunk)) : toBytes(chunk);

  const mode = state.mode || sniff(state.header);
  if (!mode) return;
  if (mode === "trojan" && !state.cfg.trojan) throw new Error("trojan is disabled");
  state.mode = mode;

  const head =
    mode === "trojan"
      ? readTrojanHeader(state.header, state.cfg)
      : readVlessHeader(state.header, state.cfg.uuidBytes);
  if (head.partial) return;
  if (head.error) throw new Error(head.error);
  state.header = null;
  // VLESS expects a two byte response header before the first payload byte;
  // trojan expects the destination's bytes verbatim.
  state.prefix = mode === "trojan" ? null : VLESS_RESPONSE;

  if (head.isUdp) {
    if (mode === "trojan") {
      state.write = openTrojanUdp(state, head);
      return;
    }
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
  if (command !== 1 && command !== 2) return { error: "unsupported command " + command };

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
    hostname = "[" + address + "]";
    cursor += 16;
  } else {
    return { error: "bad address type " + type };
  }

  if (!address) return { error: "empty address" };

  return {
    isUdp: command === 2,
    port,
    address,
    hostname,
    payload: bytes.slice(cursor)
  };
}

/**
 * Trojan request layout
 *   0..55    hex sha224 of the password
 *   56..57   CRLF
 *   +0       command  1 connect, 3 udp associate
 *   +1       address type  1 ipv4, 3 domain, 4 ipv6   (SOCKS5 numbering)
 *   ...      address, then port, then CRLF, then payload
 */
function readTrojanHeader(raw, cfg) {
  const bytes = toBytes(raw);
  if (bytes.length < TROJAN_HEAD + 4) return { partial: true };

  const given = DECODER.decode(bytes.slice(0, 56)).toLowerCase();
  if (given !== trojanDigest(cfg)) return { error: "trojan auth failed" };

  let cursor = TROJAN_HEAD;
  const command = bytes[cursor++];
  if (command !== 1 && command !== 3) {
    return { error: "unsupported trojan command " + command };
  }

  const target = readSocksAddress(bytes, cursor);
  if (target.partial) return { partial: true };
  if (target.error) return { error: target.error };
  cursor = target.cursor;

  if (bytes.length < cursor + 2) return { partial: true };
  cursor += 2; // the CRLF that closes the request

  return {
    isUdp: command === 3,
    port: target.port,
    address: target.address,
    hostname: target.hostname,
    payload: bytes.slice(cursor)
  };
}

/** ATYP, address, big endian port. Shared by trojan, its UDP frames, and shadowsocks. */
function readSocksAddress(bytes, start) {
  let cursor = start;
  if (bytes.length < cursor + 1) return { partial: true };

  const type = bytes[cursor++];
  let address = "";
  let hostname = "";

  if (type === 1) {
    if (bytes.length < cursor + 4) return { partial: true };
    address = Array.from(bytes.slice(cursor, cursor + 4)).join(".");
    hostname = address;
    cursor += 4;
  } else if (type === 3) {
    if (bytes.length < cursor + 1) return { partial: true };
    const length = bytes[cursor++];
    if (!length) return { error: "empty address" };
    if (bytes.length < cursor + length) return { partial: true };
    address = DECODER.decode(bytes.slice(cursor, cursor + length));
    hostname = address;
    cursor += length;
  } else if (type === 4) {
    if (bytes.length < cursor + 16) return { partial: true };
    const parts = [];
    for (let i = 0; i < 8; i++) {
      parts.push(((bytes[cursor + i * 2] << 8) | bytes[cursor + i * 2 + 1]).toString(16));
    }
    address = parts.join(":");
    hostname = "[" + address + "]";
    cursor += 16;
  } else {
    return { error: "bad address type " + type };
  }

  if (bytes.length < cursor + 2) return { partial: true };
  const port = (bytes[cursor] << 8) | bytes[cursor + 1];
  cursor += 2;

  return { cursor, address, hostname, port };
}

/* --------------------------------------------------------------- outbounds */

/** Suffix match against the AI list. Case and trailing dots do not matter. */
function isAiHost(cfg, address) {
  if (!cfg.aiRoute) return false;
  const host = String(address || "")
    .toLowerCase()
    .replace(/\.+$/, "");
  if (!host || !host.includes(".")) return false;
  for (const domain of cfg.aiDomains) {
    if (host === domain || host.endsWith("." + domain)) return true;
  }
  return false;
}

/** FNV-1a. Small, stable, and it does not need to be a good hash. */
function hashOf(text) {
  let hash = 0x811c9dc5;
  const value = String(text || "");
  for (let i = 0; i < value.length; i++) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash >>> 0;
}

/** Rotate a list so a given seed always lands on the same head: the static-IP pin. */
function stickyOrder(list, seed) {
  if (list.length < 2) return list.slice();
  const offset = hashOf(seed) % list.length;
  return list.slice(offset).concat(list.slice(0, offset));
}

function relayTargets(raw, port) {
  const out = [];
  for (const item of raw) {
    const target = splitHostPort(item, port);
    if (target.hostname) out.push({ ...target, relay: true, source: item });
  }
  return out;
}

/**
 * The ordered list of places to try for this destination. Normal traffic goes
 * direct first, then through the relays; AI traffic is relay-first and pinned.
 */
function buildAttempts(cfg, head) {
  const direct = { hostname: head.hostname, port: head.port, relay: false, source: "direct" };
  const relays = relayTargets(cfg.proxies, head.port);

  if (!isAiHost(cfg, head.address)) return [direct, ...relays];

  const pool = cfg.aiProxies.length ? cfg.aiProxies : cfg.proxies;
  const pinned = stickyOrder(relayTargets(pool, head.port), head.address);
  if (!pinned.length) return [direct, ...relays];

  const seen = new Set();
  const out = [];
  for (const item of [...pinned, ...relays, direct]) {
    const key = item.hostname + ":" + item.port;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
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
 * so a failover replays the session from its first byte. Identical for all three
 * protocols: by this point the difference is only the prefix on the first
 * answer and, for shadowsocks, the sealing of every answer.
 */
function openTcp(state, head) {
  const attempts = buildAttempts(state.cfg, head);
  const box = {
    writer: null,
    replay: [head.payload],
    bytes: head.payload.byteLength,
    replayable: true
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
      received === 0 && !state.spoke && box.replayable && index + 1 < attempts.length;
    closeSocket(socket);
    if (retryable) return attempt(index + 1);
    shutdown(state);
  };

  attempt(0).catch(() => shutdown(state));

  return async (chunk) => {
    const bytes = toBytes(chunk);

    if (state.spoke) {
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

/**
 * Trojan UDP, for DNS and nothing else. A Worker has no UDP socket at all, so the
 * honest options are DNS through a TCP resolver or nothing.
 */
function openTrojanUdp(state, head) {
  const socket = connect({ hostname: state.cfg.dns, port: state.cfg.dnsPort });
  state.socket = socket;
  const writer = socket.writable.getWriter();
  const queue = [];

  const pump = async () => {
    let buffer = new Uint8Array(0);
    const reader = socket.readable.getReader();
    try {
      for (;;) {
        const step = await reader.read();
        if (step.done) break;
        buffer = concat(buffer, toBytes(step.value));
        while (buffer.byteLength >= 2) {
          const size = (buffer[0] << 8) | buffer[1];
          if (buffer.byteLength < size + 2) break;
          const answer = buffer.slice(2, size + 2);
          buffer = buffer.slice(size + 2);
          if (state.ws.readyState !== WS_OPEN) return;
          const target = queue.shift();
          if (!target) continue;
          state.spoke = true;
          state.ws.send(trojanUdpFrame(target, answer));
        }
      }
    } catch (err) {
      /* resolver hung up: the caller shuts the session down */
    }
  };

  pump()
    .then(() => shutdown(state))
    .catch(() => shutdown(state));

  let pending = head.payload;

  const feed = async (bytes) => {
    pending = bytes.byteLength ? concat(pending, bytes) : pending;
    for (;;) {
      const frame = readTrojanUdpFrame(pending);
      if (!frame) break;
      pending = frame.rest;
      if (frame.port !== 53) continue;
      queue.push(frame.head);
      await writer.write(lengthPrefixed(frame.payload));
    }
  };

  feed(new Uint8Array(0)).catch(() => shutdown(state));

  return async (chunk) => {
    try {
      await feed(toBytes(chunk));
    } catch (err) {
      shutdown(state);
    }
  };
}

/** One trojan UDP frame, or null when the rest of it has not arrived yet. */
function readTrojanUdpFrame(bytes) {
  if (bytes.byteLength < 7) return null;
  const target = readSocksAddress(bytes, 0);
  if (target.partial || target.error) return null;
  const cursor = target.cursor;
  if (bytes.byteLength < cursor + 4) return null;
  const size = (bytes[cursor] << 8) | bytes[cursor + 1];
  const start = cursor + 4; // length, then CRLF
  if (bytes.byteLength < start + size) return null;
  return {
    head: bytes.slice(0, cursor),
    port: target.port,
    payload: bytes.slice(start, start + size),
    rest: bytes.slice(start + size)
  };
}

function trojanUdpFrame(head, payload) {
  const out = new Uint8Array(head.byteLength + 4 + payload.byteLength);
  out.set(head, 0);
  out[head.byteLength] = (payload.byteLength >> 8) & 0xff;
  out[head.byteLength + 1] = payload.byteLength & 0xff;
  out[head.byteLength + 2] = 13;
  out[head.byteLength + 3] = 10;
  out.set(payload, head.byteLength + 4);
  return out;
}

function lengthPrefixed(payload) {
  const out = new Uint8Array(payload.byteLength + 2);
  out[0] = (payload.byteLength >> 8) & 0xff;
  out[1] = payload.byteLength & 0xff;
  out.set(payload, 2);
  return out;
}

/**
 * Destination -> client. ``state.encode`` is set only on a shadowsocks session,
 * where every answer has to be sealed; ``state.prefix`` rides in front of the
 * first answer (VLESS response header, or the shadowsocks server salt).
 */
async function pumpRemote(state, socket) {
  let received = 0;
  try {
    await socket.readable.pipeTo(
      new WritableStream({
        async write(chunk) {
          if (state.ws.readyState !== WS_OPEN) throw new Error("websocket closed");
          let bytes = toBytes(chunk);
          received += bytes.byteLength;
          if (state.encode) bytes = await state.encode(bytes);
          if (state.spoke) {
            state.ws.send(bytes);
          } else {
            state.spoke = true;
            state.ws.send(state.prefix ? concat(state.prefix, bytes) : bytes);
          }
        }
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
      kind: item.kind || "ip"
    });
  }
  return out;
}

/** Pull the public clean-IP lists through the edge cache. */
async function fetchSources(cfg) {
  const found = [];
  const LIMIT = 120;
  for (const url of cfg.sources.slice(0, 4)) {
    if (found.length >= LIMIT) break;
    try {
      const response = await fetch(url, {
        cf: { cacheTtl: cfg.refresh, cacheEverything: true },
        headers: { "user-agent": cfg.brand + "/1.3" }
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
          kind: "live"
        });
        if (found.length >= LIMIT) break;
      }
    } catch (err) {
      /* a dead list is not worth failing a subscription over */
    }
  }
  return found;
}

/** Rotate deterministically inside each refresh window. */
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
    { key: "http", ports: cfg.httpPorts, count: cfg.httpCount }
  ];

  const out = [];
  const seen = new Set();
  const take = (bag, item) => {
    if (!item || !item.ip) return;
    const key = item.ip + ":" + item.port;
    if (seen.has(key)) return;
    seen.add(key);
    bag.push(item);
  };

  for (const group of groups) {
    if (group.count <= 0 || !group.ports.length) continue;
    const ports = group.ports;
    const bag = [];

    const bakedGroup = baked.filter((item) => groupOf(item.port, cfg) === group.key);
    const deal = (items) =>
      items.map((item, index) => ({ ...item, port: ports[index % ports.length] }));

    const domainGroup = deal(
      cfg.domains.map((domain) => ({ ip: domain, latency: 0, colo: "AUTO", kind: "domain" }))
    );
    const freshGroup = fresh.map((item, index) => ({
      ...item,
      port:
        item.port && groupOf(item.port, cfg) === group.key
          ? item.port
          : ports[index % ports.length]
    }));

    const domainSlots = group.count >= 2 && domainGroup.length ? 1 : 0;
    const freshSlots = group.count >= 3 && freshGroup.length ? 1 : 0;
    const bakedSlots = Math.max(0, group.count - domainSlots - freshSlots);

    for (const item of bakedGroup.slice(0, bakedSlots)) take(bag, item);
    for (const item of domainGroup.slice(0, domainSlots)) take(bag, item);
    for (const item of freshGroup.slice(0, freshSlots)) take(bag, item);

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
    const protocols = ["vless"];
    if (cfg.trojan) protocols.push("trojan");
    if (cfg.ssActive) protocols.push("shadowsocks");
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
      ai_route: cfg.aiRoute,
      ai_proxies: cfg.aiProxies.length,
      ai_domains: cfg.aiDomains.length,
      protocols,
      trojan: cfg.trojan,
      shadowsocks: cfg.ssActive,
      ss_path: cfg.ssActive ? cfg.ssPath : null,
      tls_ports: cfg.tlsPorts,
      http_ports: cfg.httpPorts,
      colo: request.cf && request.cf.colo ? request.cf.colo : null
    });
  }

  if (kind === "probe") {
    return jsonResponse(await probe(cfg));
  }

  if (kind === "ai") {
    return jsonResponse(await aiReport(cfg));
  }

  const endpoints = await liveEndpoints(cfg);

  if (kind === "endpoints") {
    return jsonResponse({ count: endpoints.length, endpoints });
  }

  if (kind === "clash") {
    return new Response(buildClash(cfg, endpoints), {
      headers: { "content-type": "text/yaml; charset=utf-8", ...corsHeaders() }
    });
  }

  if (kind === "singbox" || kind === "sing-box") {
    return jsonResponse(buildSingbox(cfg, endpoints));
  }

  let links;
  if (kind === "trojan") {
    links = buildTrojanLinks(cfg, endpoints);
  } else if (kind === "ss" || kind === "shadowsocks") {
    links = buildSsLinks(cfg, endpoints);
  } else if (kind === "mix" || kind === "all") {
    links = [
      ...buildLinks(cfg, endpoints),
      ...buildTrojanLinks(cfg, endpoints),
      ...buildSsLinks(cfg, endpoints)
    ];
  } else {
    links = buildLinks(cfg, endpoints);
  }
  const body = links.join("\n");

  if (kind === "raw") {
    return new Response(body, {
      headers: { "content-type": "text/plain; charset=utf-8", ...corsHeaders() }
    });
  }

  return new Response(btoa(unescape(encodeURIComponent(body))), {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "profile-update-interval": "6",
      "profile-title": cfg.brand,
      "cache-control": "no-store",
      ...corsHeaders()
    }
  });
}

function landing(cfg) {
  const body =
    '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    "<title>" +
    cfg.brand +
    '</title></head><body style="font-family:system-ui;padding:3rem;">' +
    "<h1>" +
    cfg.brand +
    "</h1><p>Nothing to see here.</p></body></html>";
  return new Response(body, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" }
  });
}

/** Outbound reachability, measured from inside the worker. */
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
    usable_relays: relays.filter((item) => item.ok).length
  };
}

/** What the AI path looks like right now, and where each well known host is pinned. */
async function aiReport(cfg) {
  const pool = cfg.aiProxies.length ? cfg.aiProxies : cfg.proxies;
  const relays = [];
  for (const raw of pool.slice(0, 4)) {
    const target = splitHostPort(raw, 443);
    const result = await tcpProbe(target.hostname, target.port, "");
    relays.push({ target: raw, ...result });
  }

  const samples = ["chatgpt.com", "gemini.google.com", "claude.ai"];
  const pinning = {};
  for (const host of samples) {
    const order = stickyOrder(relayTargets(pool, 443), host);
    pinning[host] = order.length ? order[0].source : null;
  }

  return {
    ok: relays.some((item) => item.ok),
    enabled: cfg.aiRoute,
    dedicated: cfg.aiProxies.length > 0,
    relays,
    usable_relays: relays.filter((item) => item.ok).length,
    domains: cfg.aiDomains.length,
    pinning
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
          "GET / HTTP/1.1\r\nHost: " +
            readBackHost +
            "\r\nUser-Agent: AutoVless\r\nAccept: */*\r\nConnection: close\r\n\r\n"
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
    new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), ms))
  ]);
}

/* ------------------------------------------------------------ config export */

function remark(cfg, endpoint, index, protocol) {
  const secure = isTls(endpoint.port, cfg);
  const name = protocol === "ss" ? "SS" : (protocol || "vless").toUpperCase();
  let badge = secure ? "\u26a1" : "\ud83d\udfe1";
  if (endpoint.kind === "domain") badge = "\ud83c\udf00";
  if (endpoint.kind === "live") badge = "\ud83d\udd04";
  if (protocol === "trojan") badge = endpoint.kind === "domain" ? "\ud83c\udf00" : "\ud83c\udfaf";
  if (protocol === "ss") badge = endpoint.kind === "domain" ? "\ud83c\udf00" : "\ud83d\udee1";
  const ping = endpoint.latency ? Math.round(Number(endpoint.latency)) + "ms" : "auto";
  const tail = secure ? "" : " | \ud83d\udd0c" + endpoint.port;
  const lock = secure && Number(endpoint.port) !== 443 ? " | \ud83d\udd12" + endpoint.port : "";
  const ai = cfg.aiRoute ? " | \ud83e\udde0AI" : "";
  return (
    "@" +
    cfg.brand +
    " | " +
    badge +
    " " +
    name +
    " | \ud83c\udf0d GLOBAL" +
    ai +
    " | " +
    ping +
    " | " +
    (endpoint.colo || "CF") +
    lock +
    tail +
    " | #" +
    index
  );
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
      path: cfg.wsPath
    });
    if (secure) {
      params.set("sni", cfg.host);
      params.set("fp", "chrome");
      params.set("alpn", "http/1.1");
    }
    const label = encodeURIComponent(remark(cfg, endpoint, position + 1, "vless"));
    links.push(
      "vless://" +
        cfg.uuid +
        "@" +
        endpoint.ip +
        ":" +
        endpoint.port +
        "?" +
        params.toString() +
        "#" +
        label
    );
  });
  return links;
}

/** Trojan links, TLS endpoints only. */
function buildTrojanLinks(cfg, endpoints) {
  if (!cfg.trojan) return [];
  const links = [];
  let index = 0;
  for (const endpoint of endpoints) {
    if (!isTls(endpoint.port, cfg)) continue;
    index += 1;
    const params = new URLSearchParams({
      security: "tls",
      type: "ws",
      host: cfg.host,
      path: cfg.wsPath,
      sni: cfg.host,
      fp: "chrome",
      alpn: "http/1.1"
    });
    const label = encodeURIComponent(remark(cfg, endpoint, index, "trojan"));
    links.push(
      "trojan://" +
        encodeURIComponent(cfg.trojanPassword) +
        "@" +
        endpoint.ip +
        ":" +
        endpoint.port +
        "?" +
        params.toString() +
        "#" +
        label
    );
  }
  return links;
}

/**
 * SIP002 Shadowsocks links with the websocket plugin, TLS endpoints only. Needs
 * SS_PASSWORD: the worker only holds the derived key, and a link carries the
 * password a client derives that key from.
 */
function buildSsLinks(cfg, endpoints) {
  if (!cfg.ssActive || !cfg.ssPassword) return [];
  const userinfo = btoa(cfg.ssMethod + ":" + cfg.ssPassword)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
  const plugin = encodeURIComponent(
    "v2ray-plugin;mode=websocket;tls;host=" + cfg.host + ";path=" + cfg.ssPath + ";mux=0"
  );
  const links = [];
  let index = 0;
  for (const endpoint of endpoints) {
    if (!isTls(endpoint.port, cfg)) continue;
    index += 1;
    const label = encodeURIComponent(remark(cfg, endpoint, index, "ss"));
    links.push(
      "ss://" + userinfo + "@" + endpoint.ip + ":" + endpoint.port + "?plugin=" + plugin + "#" + label
    );
  }
  return links;
}

function buildClash(cfg, endpoints) {
  const proxies = [];
  const names = [];

  endpoints.forEach((endpoint, position) => {
    const secure = isTls(endpoint.port, cfg);
    const name = remark(cfg, endpoint, position + 1, "vless").replace(/"/g, "'");
    names.push('      - "' + name + '"');
    const lines = [
      '  - name: "' + name + '"',
      "    type: vless",
      "    server: " + endpoint.ip,
      "    port: " + endpoint.port,
      "    uuid: " + cfg.uuid,
      "    udp: true",
      "    tls: " + (secure ? "true" : "false")
    ];
    if (secure) {
      lines.push("    servername: " + cfg.host, "    client-fingerprint: chrome");
    }
    lines.push(
      "    network: ws",
      "    ws-opts:",
      '      path: "' + cfg.wsPath + '"',
      "      headers:",
      "        Host: " + cfg.host
    );
    proxies.push(lines.join("\n"));
  });

  if (cfg.trojan) {
    let index = 0;
    for (const endpoint of endpoints) {
      if (!isTls(endpoint.port, cfg)) continue;
      index += 1;
      const name = remark(cfg, endpoint, index, "trojan").replace(/"/g, "'");
      names.push('      - "' + name + '"');
      proxies.push(
        [
          '  - name: "' + name + '"',
          "    type: trojan",
          "    server: " + endpoint.ip,
          "    port: " + endpoint.port,
          "    password: " + cfg.trojanPassword,
          "    udp: true",
          "    sni: " + cfg.host,
          "    client-fingerprint: chrome",
          "    network: ws",
          "    ws-opts:",
          '      path: "' + cfg.wsPath + '"',
          "      headers:",
          "        Host: " + cfg.host
        ].join("\n")
      );
    }
  }

  return [
    "# " + cfg.brand + " - built on your own Cloudflare account",
    "mixed-port: 7890",
    "allow-lan: false",
    "mode: rule",
    "log-level: warning",
    "proxies:",
    proxies.join("\n"),
    "proxy-groups:",
    '  - name: "' + cfg.brand + '"',
    "    type: url-test",
    "    url: http://cp.cloudflare.com/generate_204",
    "    interval: 300",
    "    tolerance: 50",
    "    proxies:",
    names.join("\n"),
    "rules:",
    "  - MATCH," + cfg.brand,
    ""
  ].join("\n");
}

function buildSingbox(cfg, endpoints) {
  const outbounds = endpoints.map((endpoint, position) => {
    const secure = isTls(endpoint.port, cfg);
    const item = {
      type: "vless",
      tag: remark(cfg, endpoint, position + 1, "vless"),
      server: endpoint.ip,
      server_port: Number(endpoint.port),
      uuid: cfg.uuid,
      packet_encoding: "xudp",
      transport: {
        type: "ws",
        path: cfg.wsPath,
        headers: { Host: cfg.host },
        early_data_header_name: "Sec-WebSocket-Protocol"
      }
    };
    if (secure) {
      item.tls = {
        enabled: true,
        server_name: cfg.host,
        utls: { enabled: true, fingerprint: "chrome" }
      };
    }
    return item;
  });

  if (cfg.trojan) {
    let index = 0;
    for (const endpoint of endpoints) {
      if (!isTls(endpoint.port, cfg)) continue;
      index += 1;
      outbounds.push({
        type: "trojan",
        tag: remark(cfg, endpoint, index, "trojan"),
        server: endpoint.ip,
        server_port: Number(endpoint.port),
        password: cfg.trojanPassword,
        tls: {
          enabled: true,
          server_name: cfg.host,
          utls: { enabled: true, fingerprint: "chrome" }
        },
        transport: {
          type: "ws",
          path: cfg.wsPath,
          headers: { Host: cfg.host },
          early_data_header_name: "Sec-WebSocket-Protocol"
        }
      });
    }
  }

  return { outbounds };
}

/* --------------------------------------------------------------- responses */

function corsHeaders() {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, HEAD, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400"
  };
}

function textResponse(body, status) {
  return new Response(body, {
    status: status || 200,
    headers: { "content-type": "text/plain; charset=utf-8", ...corsHeaders() }
  });
}

function jsonResponse(payload, status) {
  return new Response(JSON.stringify(payload, null, 2), {
    status: status || 200,
    headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders() }
  });
}

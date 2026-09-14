/**
 * Shadowsocks AEAD (aes-256-gcm) inbound for the edge worker.
 *
 * Why this is its own file
 * -----------------------
 * The worker is uploaded to Cloudflare as a single script, so this code is
 * inlined into `vless-worker.js` when the inbound is switched on. It lives here
 * as a module anyway for one reason: it is the only part of the worker that can
 * be tested off the edge, and `scripts/test-shadowsocks.mjs` does exactly that -
 * against an independent client written on node:crypto rather than on these
 * functions. Verifying a cipher by asking it to agree with itself proves nothing.
 *
 * What it adds
 * ------------
 * A third handshake shape on the same address and port. VLESS opens with a zero
 * version byte; Trojan opens with 56 hex characters; Shadowsocks opens with 32
 * bytes of random salt and never says anything in the clear at all. A classifier
 * that has learned the first two has nothing to match on here.
 *
 * Why it is dispatched by path and not sniffed
 * -------------------------------------------
 * The bundle tells VLESS from Trojan by reading the first frame. That cannot
 * extend to Shadowsocks, and precisely because of the property above: random
 * bytes are indistinguishable from a VLESS header by inspection, so a guess is a
 * coin flip and a wrong guess is a silent auth failure that looks exactly like a
 * dead endpoint. The inbound therefore gets its own WebSocket path, `SS_PATH`,
 * and `fetch` dispatches on it before any sniffing happens.
 *
 * Why the key arrives pre-derived
 * ------------------------------
 * Every Shadowsocks client turns the password into a master key with
 * EVP_BytesToKey, which is an MD5 chain. Workers' WebCrypto offers SHA-1 through
 * SHA-512 and no MD5 at all, so that derivation cannot happen here. It does not
 * need to: `bot/shadowsocks.py` does it and binds the result as `SS_KEY` hex.
 * From there everything is HKDF-SHA1 and AES-GCM, both of which WebCrypto has.
 * The two sides were checked byte for byte against a stock client's key.
 *
 * Framing, for the next person to read this
 * ----------------------------------------
 *   salt(32) || [ len(2) + tag(16) ] [ payload(len) + tag(16) ] ...
 *
 * subkey  = HKDF-SHA1(master, salt, "ss-subkey", 32)
 * nonce   = 12 byte little-endian counter, incremented after every AEAD
 *           operation, counted separately per direction
 * chunks  cap at 0x3fff bytes, which is the protocol's own limit
 *
 * The first plaintext bytes are a SOCKS-shaped target address, so the bundle's
 * existing `readSocksAddress` parses them - the same function the Trojan inbound
 * already uses.
 */

const ENCODER = new TextEncoder();
const SS_INFO = ENCODER.encode("ss-subkey");

export const SS_SALT_BYTES = 32;
export const SS_TAG_BYTES = 16;
export const SS_MAX_CHUNK = 0x3fff;

export function ssConcat(a, b) {
  const out = new Uint8Array(a.byteLength + b.byteLength);
  out.set(a, 0);
  out.set(b, a.byteLength);
  return out;
}

/** `SS_KEY` as bytes, or null when the binding is missing or malformed. */
export function ssKeyBytes(text) {
  const hex = String(text || "").replace(/[^0-9a-f]/gi, "").toLowerCase();
  if (hex.length !== 64) return null;
  const out = new Uint8Array(32);
  for (let i = 0; i < 32; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

/** The per-connection key. One HKDF per direction, keyed by that side's salt. */
export async function ssSubkey(master, salt) {
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

/**
 * A stateful reader. Feed it whatever arrives, get back whole plaintext chunks.
 *
 * The buffering is the point: a WebSocket frame boundary has nothing to do with
 * a Shadowsocks chunk boundary, so a length header can and does arrive split in
 * half. The counter is only advanced after a chunk authenticates, because
 * advancing it on a partial read would desynchronise the stream permanently.
 */
export function ssOpener(key) {
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
    if (chunk && chunk.byteLength) buffer = ssConcat(buffer, chunk);
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
export function ssSealer(key) {
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
      out = ssConcat(out, await seal(size));
      out = ssConcat(out, await seal(piece));
    }
    return out;
  };
}

/**
 * Everything one connection needs: a reader for the client, a writer for the
 * answers, and the salt that has to be sent ahead of the first sealed byte.
 *
 * Two salts, two subkeys, and they are not interchangeable. The client picks its
 * own and the server picks its own, so a recorded session cannot be replayed in
 * either direction.
 */
export async function ssSession(master, clientSalt) {
  const serverSalt = new Uint8Array(SS_SALT_BYTES);
  crypto.getRandomValues(serverSalt);
  return {
    serverSalt,
    read: ssOpener(await ssSubkey(master, clientSalt)),
    write: ssSealer(await ssSubkey(master, serverSalt))
  };
}

/** True when this request should be handled as Shadowsocks rather than sniffed. */
export function ssPathMatch(pathname, configured) {
  const want = String(configured || "/ss").split("?")[0];
  const got = String(pathname || "/").split("?")[0];
  return got === want || got === want.replace(/\/+$/, "");
}

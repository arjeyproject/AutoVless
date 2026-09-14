/**
 * Shadowsocks inbound tests.
 *
 *   node scripts/test-shadowsocks.mjs
 *
 * The client side here is written on node:crypto - a different implementation of
 * the same spec, not a second call into the worker's own functions. That is the
 * only way this proves anything: a cipher asked to agree with itself always will.
 *
 * The key derivation is checked against EVP_BytesToKey, which is what a stock
 * client does with the password in the ss:// link, so a pass here means the key
 * `bot/shadowsocks.py` binds and the key a user's client derives are the same
 * bytes.
 */
import nodeCrypto from "node:crypto";
import {
  ssKeyBytes,
  ssOpener,
  ssSealer,
  ssSession,
  ssSubkey,
  ssConcat,
  ssPathMatch,
  SS_MAX_CHUNK
} from "../worker/shadowsocks.js";

const PASSWORD = "AutoVless-test-password-01";

function evpKey(pass, len) {
  let out = Buffer.alloc(0);
  let prev = Buffer.alloc(0);
  while (out.length < len) {
    prev = nodeCrypto.createHash("md5").update(Buffer.concat([prev, Buffer.from(pass, "utf8")])).digest();
    out = Buffer.concat([out, prev]);
  }
  return out.subarray(0, len);
}

const master = evpKey(PASSWORD, 32);
const clientSubkey = (salt) =>
  Buffer.from(nodeCrypto.hkdfSync("sha1", master, salt, Buffer.from("ss-subkey"), 32));
const nonceOf = (counter) => {
  const n = Buffer.alloc(12);
  n.writeUInt32LE(counter, 0);
  return n;
};
const clientSeal = (key, counter, plain) => {
  const c = nodeCrypto.createCipheriv("aes-256-gcm", key, nonceOf(counter));
  return Buffer.concat([c.update(plain), c.final(), c.getAuthTag()]);
};
const clientOpen = (key, counter, box) => {
  const d = nodeCrypto.createDecipheriv("aes-256-gcm", key, nonceOf(counter));
  d.setAuthTag(box.subarray(box.length - 16));
  return Buffer.concat([d.update(box.subarray(0, box.length - 16)), d.final()]);
};
const clientStream = (key, payload) => {
  let out = Buffer.alloc(0);
  let counter = 0;
  let rest = payload;
  while (rest.length) {
    const piece = rest.subarray(0, SS_MAX_CHUNK);
    rest = rest.subarray(piece.length);
    const size = Buffer.from([(piece.length >> 8) & 0xff, piece.length & 0xff]);
    out = Buffer.concat([out, clientSeal(key, counter++, size), clientSeal(key, counter++, piece)]);
  }
  return out;
};
const clientReadAll = (key, wire) => {
  let counter = 0;
  let cursor = 0;
  let got = Buffer.alloc(0);
  while (cursor < wire.length) {
    const size = clientOpen(key, counter++, wire.subarray(cursor, cursor + 18));
    cursor += 18;
    const len = (size[0] << 8) | size[1];
    got = Buffer.concat([got, clientOpen(key, counter++, wire.subarray(cursor, cursor + len + 16))]);
    cursor += len + 16;
  }
  return got;
};

/* the same address parser the bundle already uses for trojan */
function readSocksAddress(bytes, start) {
  let cursor = start;
  const type = bytes[cursor++];
  let address = "";
  if (type === 1) {
    address = Array.from(bytes.slice(cursor, cursor + 4)).join(".");
    cursor += 4;
  } else if (type === 3) {
    const n = bytes[cursor++];
    address = new TextDecoder().decode(bytes.slice(cursor, cursor + n));
    cursor += n;
  } else {
    return { error: "unsupported" };
  }
  const port = (bytes[cursor] << 8) | bytes[cursor + 1];
  return { cursor: cursor + 2, address, port };
}

let failures = 0;
const check = (name, ok) => {
  console.log((ok ? "  ok   " : "  FAIL ") + name);
  if (!ok) failures++;
};

/* 1. the binding the bot produces is the key a client derives */
check("SS_KEY hex parses to 32 bytes", (ssKeyBytes(master.toString("hex")) || []).length === 32);
check("SS_KEY rejects a truncated binding", ssKeyBytes("abcd") === null);

/* 2. client to server, header and payload, fed in seven byte slices */
{
  const salt = nodeCrypto.randomBytes(32);
  const key = clientSubkey(salt);
  const host = Buffer.from("chatgpt.com", "utf8");
  const header = Buffer.concat([Buffer.from([3, host.length]), host, Buffer.from([1, 0xbb])]);
  const body = Buffer.from("GET / HTTP/1.1\r\nHost: chatgpt.com\r\n\r\n");
  const wire = clientStream(key, Buffer.concat([header, body]));

  const push = ssOpener(await ssSubkey(new Uint8Array(master), new Uint8Array(salt)));
  let plain = new Uint8Array(0);
  for (let i = 0; i < wire.length; i += 7) {
    for (const part of await push(new Uint8Array(wire.subarray(i, i + 7)))) {
      plain = ssConcat(plain, part);
    }
  }
  const target = readSocksAddress(plain, 0);
  check("target address parses to chatgpt.com:443", target.address === "chatgpt.com" && target.port === 443);
  check("payload survives a frame boundary every 7 bytes",
    Buffer.from(plain.slice(target.cursor)).toString() === body.toString());
}

/* 3. server to client */
{
  const salt = nodeCrypto.randomBytes(32);
  const answer = Buffer.from("HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\nhi");
  const sealed = await ssSealer(await ssSubkey(new Uint8Array(master), new Uint8Array(salt)))(
    new Uint8Array(answer));
  check("client decrypts the server stream",
    clientReadAll(clientSubkey(salt), Buffer.from(sealed)).toString() === answer.toString());
}

/* 4. oversized payloads split at the protocol limit, both ways */
{
  const salt = nodeCrypto.randomBytes(32);
  const key = clientSubkey(salt);
  const serverKey = await ssSubkey(new Uint8Array(master), new Uint8Array(salt));
  const big = nodeCrypto.randomBytes(SS_MAX_CHUNK * 2 + 1234);
  const sealed = Buffer.from(await ssSealer(serverKey)(new Uint8Array(big)));
  check("a 2.07x oversized payload round trips downstream",
    clientReadAll(key, sealed).equals(big));
  let back = new Uint8Array(0);
  for (const part of await ssOpener(serverKey)(new Uint8Array(clientStream(key, big)))) {
    back = ssConcat(back, part);
  }
  check("and upstream", Buffer.from(back).equals(big));
}

/* 5. a wrong password authenticates nothing */
{
  const salt = nodeCrypto.randomBytes(32);
  const key = clientSubkey(salt);
  const wrong = await ssSubkey(new Uint8Array(evpKey("not-the-password", 32)), new Uint8Array(salt));
  let threw = false;
  try {
    await ssOpener(wrong)(new Uint8Array(clientStream(key, Buffer.from("x"))));
  } catch (error) {
    threw = /auth failed/.test(error.message);
  }
  check("a wrong password is rejected, not tolerated", threw);
}

/* 6. the two directions use different salts */
{
  const clientSalt = new Uint8Array(nodeCrypto.randomBytes(32));
  const session = await ssSession(new Uint8Array(master), clientSalt);
  check("the server picks its own salt", Buffer.from(session.serverSalt).length === 32 &&
    !Buffer.from(session.serverSalt).equals(Buffer.from(clientSalt)));
  const sealed = Buffer.from(await session.write(new Uint8Array(Buffer.from("pong"))));
  check("answers are readable with the server salt only",
    clientReadAll(clientSubkey(Buffer.from(session.serverSalt)), sealed).toString() === "pong");
}

/* 7. path dispatch */
check("path dispatch matches the configured path", ssPathMatch("/ss", "/ss") &&
  ssPathMatch("/ss?x=1", "/ss") && !ssPathMatch("/", "/ss"));

console.log(failures ? `\n${failures} failed` : "\nall shadowsocks checks passed");
process.exit(failures ? 1 : 0);

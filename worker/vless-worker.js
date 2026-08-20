/**
 * AutoVless Worker
 * VLESS over WebSocket running on Cloudflare Workers.
 *
 * Bindings (plain text vars) injected by the bot at deploy time:
 *   UUID    - the VLESS user id
 *   PROXYIP - optional fallback relay for blocked destinations (host or host:port)
 *   IPS     - JSON array of endpoints: [{"ip":"1.2.3.4","port":443,"latency":21,"colo":"CDG"}]
 *   BRAND   - display name used in config remarks
 *
 * Public routes:
 *   /                 camouflage page
 *   /healthz          liveness probe
 *   /<uuid>           subscription (base64, v2ray/v2rayNG/Nekobox/Streisand)
 *   /<uuid>/raw       subscription (plain text)
 *   /<uuid>/clash     Clash / Mihomo / Clash Meta profile
 *   /<uuid>/singbox   sing-box outbounds
 */

import { connect } from 'cloudflare:sockets';

const FALLBACK_UUID = '00000000-0000-0000-0000-000000000000';
const WS_OPEN = 1;
const WS_CLOSING = 2;
const TLS_PORTS = new Set([443, 2053, 2083, 2087, 2096, 8443]);
const WS_PATH = '/?ed=2560';

export default {
  async fetch(request, env) {
    const uuid = String(env.UUID || FALLBACK_UUID).trim().toLowerCase();
    const proxyIP = String(env.PROXYIP || '').trim();
    const brand = String(env.BRAND || 'AutoVless').trim();

    try {
      if ((request.headers.get('Upgrade') || '').toLowerCase() === 'websocket') {
        return await handleVless(request, uuid, proxyIP);
      }

      const url = new URL(request.url);
      const host = request.headers.get('Host') || url.hostname;
      const eps = endpoints(env);

      switch (url.pathname) {
        case '/healthz':
          return jsonResponse({ ok: true, endpoints: eps.length, ts: Date.now() });
        case `/${uuid}`:
        case `/${uuid}/sub`:
          return textResponse(b64utf8(links(eps, uuid, host, brand).join('\n')), brand);
        case `/${uuid}/raw`:
          return textResponse(links(eps, uuid, host, brand).join('\n'), brand);
        case `/${uuid}/clash`:
          return new Response(clashProfile(eps, uuid, host, brand), {
            headers: { 'content-type': 'text/yaml; charset=utf-8', 'profile-update-interval': '6' },
          });
        case `/${uuid}/singbox`:
          return jsonResponse({ outbounds: singboxOutbounds(eps, uuid, host, brand) });
        default:
          return new Response(camouflage(brand), {
            headers: { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' },
          });
      }
    } catch (err) {
      return new Response(`unavailable: ${err && err.message ? err.message : err}`, { status: 500 });
    }
  },
};

/* ------------------------------------------------------------------ *
 *  VLESS transport
 * ------------------------------------------------------------------ */

async function handleVless(request, uuid, proxyIP) {
  const pair = new WebSocketPair();
  const [client, server] = Object.values(pair);
  server.accept();

  const earlyData = request.headers.get('sec-websocket-protocol') || '';
  const readable = readableFromWebSocket(server, earlyData);
  const remote = { value: null };
  let udpWrite = null;
  let isDns = false;

  readable
    .pipeTo(
      new WritableStream({
        async write(chunk) {
          if (isDns && udpWrite) {
            return udpWrite(chunk);
          }
          if (remote.value) {
            const writer = remote.value.writable.getWriter();
            await writer.write(chunk);
            writer.releaseLock();
            return;
          }

          const head = parseVlessHeader(chunk, uuid);
          if (head.hasError) {
            throw new Error(head.message);
          }

          const responseHeader = new Uint8Array([head.version[0], 0]);
          const payload = chunk.slice(head.rawDataIndex);

          if (head.isUDP) {
            if (head.port !== 53) {
              throw new Error('udp is limited to dns');
            }
            isDns = true;
            udpWrite = (await dnsOutbound(server, responseHeader)).write;
            udpWrite(payload);
            return;
          }

          await tcpOutbound(remote, head.address, head.port, payload, server, responseHeader, proxyIP);
        },
        close() {},
        abort() {},
      })
    )
    .catch(() => closeWebSocket(server));

  return new Response(null, { status: 101, webSocket: client });
}

async function tcpOutbound(remote, address, port, payload, ws, responseHeader, proxyIP) {
  async function dial(host, dialPort) {
    const socket = connect({ hostname: host, port: dialPort });
    remote.value = socket;
    const writer = socket.writable.getWriter();
    await writer.write(payload);
    writer.releaseLock();
    return socket;
  }

  async function retry() {
    if (!proxyIP) {
      return closeWebSocket(ws);
    }
    const [relayHost, relayPort] = splitHostPort(proxyIP, port);
    try {
      const socket = await dial(relayHost, relayPort);
      socket.closed.catch(() => {}).finally(() => closeWebSocket(ws));
      pumpToWebSocket(socket, ws, responseHeader, null);
    } catch (_) {
      closeWebSocket(ws);
    }
  }

  try {
    const socket = await dial(address, port);
    pumpToWebSocket(socket, ws, responseHeader, retry);
  } catch (_) {
    await retry();
  }
}

async function pumpToWebSocket(socket, ws, responseHeader, retry) {
  let header = responseHeader;
  let received = false;

  await socket.readable
    .pipeTo(
      new WritableStream({
        async write(chunk) {
          received = true;
          if (ws.readyState !== WS_OPEN) {
            throw new Error('websocket is not open');
          }
          if (header) {
            ws.send(await new Blob([header, chunk]).arrayBuffer());
            header = null;
          } else {
            ws.send(chunk);
          }
        },
        close() {},
        abort() {},
      })
    )
    .catch(() => closeWebSocket(ws));

  if (!received && retry) {
    await retry();
  }
}

async function dnsOutbound(ws, responseHeader) {
  let headerSent = false;

  const framer = new TransformStream({
    transform(chunk, controller) {
      for (let i = 0; i + 2 <= chunk.byteLength; ) {
        const size = new DataView(chunk.slice(i, i + 2)).getUint16(0);
        controller.enqueue(new Uint8Array(chunk.slice(i + 2, i + 2 + size)));
        i += 2 + size;
      }
    },
  });

  framer.readable
    .pipeTo(
      new WritableStream({
        async write(query) {
          const upstream = await fetch('https://1.1.1.1/dns-query', {
            method: 'POST',
            headers: { 'content-type': 'application/dns-message' },
            body: query,
          });
          const answer = await upstream.arrayBuffer();
          const size = answer.byteLength;
          const prefix = new Uint8Array([(size >> 8) & 0xff, size & 0xff]);
          if (ws.readyState !== WS_OPEN) {
            return;
          }
          if (headerSent) {
            ws.send(await new Blob([prefix, answer]).arrayBuffer());
          } else {
            ws.send(await new Blob([responseHeader, prefix, answer]).arrayBuffer());
            headerSent = true;
          }
        },
      })
    )
    .catch(() => {});

  const writer = framer.writable.getWriter();
  return { write: (chunk) => writer.write(chunk) };
}

function readableFromWebSocket(ws, earlyDataHeader) {
  let cancelled = false;

  return new ReadableStream({
    start(controller) {
      ws.addEventListener('message', (event) => {
        if (!cancelled) {
          controller.enqueue(event.data);
        }
      });
      ws.addEventListener('close', () => {
        closeWebSocket(ws);
        if (!cancelled) {
          controller.close();
        }
      });
      ws.addEventListener('error', () => controller.error(new Error('websocket error')));

      const { earlyData, error } = base64ToBuffer(earlyDataHeader);
      if (error) {
        controller.error(error);
      } else if (earlyData) {
        controller.enqueue(earlyData);
      }
    },
    cancel() {
      cancelled = true;
      closeWebSocket(ws);
    },
  });
}

function parseVlessHeader(buffer, uuid) {
  if (!buffer || buffer.byteLength < 24) {
    return { hasError: true, message: 'short header' };
  }

  const bytes = new Uint8Array(buffer);
  const version = bytes.subarray(0, 1);

  if (uuidFromBytes(bytes.subarray(1, 17)) !== uuid) {
    return { hasError: true, message: 'unauthorized' };
  }

  const optLength = bytes[17];
  const command = bytes[18 + optLength];
  if (command !== 1 && command !== 2) {
    return { hasError: true, message: `command ${command} unsupported` };
  }

  const portIndex = 19 + optLength;
  const port = new DataView(buffer.slice(portIndex, portIndex + 2)).getUint16(0);
  const typeIndex = portIndex + 2;
  const addressType = bytes[typeIndex];

  let cursor = typeIndex + 1;
  let length = 0;
  let address = '';

  if (addressType === 1) {
    length = 4;
    address = Array.from(bytes.subarray(cursor, cursor + length)).join('.');
  } else if (addressType === 2) {
    length = bytes[cursor];
    cursor += 1;
    address = new TextDecoder().decode(buffer.slice(cursor, cursor + length));
  } else if (addressType === 3) {
    length = 16;
    const view = new DataView(buffer.slice(cursor, cursor + length));
    const parts = [];
    for (let i = 0; i < 8; i += 1) {
      parts.push(view.getUint16(i * 2).toString(16));
    }
    address = `[${parts.join(':')}]`;
  } else {
    return { hasError: true, message: `address type ${addressType} unsupported` };
  }

  if (!address) {
    return { hasError: true, message: 'empty address' };
  }

  return {
    hasError: false,
    address,
    port,
    isUDP: command === 2,
    version,
    rawDataIndex: cursor + length,
  };
}

const HEX = [];
for (let i = 0; i < 256; i += 1) {
  HEX.push((i + 256).toString(16).slice(1));
}

function uuidFromBytes(bytes) {
  const h = HEX;
  return (
    h[bytes[0]] + h[bytes[1]] + h[bytes[2]] + h[bytes[3]] + '-' +
    h[bytes[4]] + h[bytes[5]] + '-' +
    h[bytes[6]] + h[bytes[7]] + '-' +
    h[bytes[8]] + h[bytes[9]] + '-' +
    h[bytes[10]] + h[bytes[11]] + h[bytes[12]] + h[bytes[13]] + h[bytes[14]] + h[bytes[15]]
  ).toLowerCase();
}

function base64ToBuffer(value) {
  if (!value) {
    return { earlyData: null, error: null };
  }
  try {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const decoded = atob(normalized);
    const bytes = Uint8Array.from(decoded, (c) => c.charCodeAt(0));
    return { earlyData: bytes.buffer, error: null };
  } catch (error) {
    return { earlyData: null, error };
  }
}

function closeWebSocket(ws) {
  try {
    if (ws.readyState === WS_OPEN || ws.readyState === WS_CLOSING) {
      ws.close();
    }
  } catch (_) {
    /* ignore */
  }
}

function splitHostPort(value, fallbackPort) {
  const match = String(value).match(/^\[?([^\]]+?)\]?(?::(\d+))?$/);
  if (!match) {
    return [value, fallbackPort];
  }
  return [match[1], match[2] ? Number(match[2]) : fallbackPort];
}

/* ------------------------------------------------------------------ *
 *  Subscription output
 * ------------------------------------------------------------------ */

function endpoints(env) {
  try {
    const parsed = JSON.parse(env.IPS || '[]');
    return Array.isArray(parsed) ? parsed.filter((e) => e && e.ip && e.port) : [];
  } catch (_) {
    return [];
  }
}

function remark(ep, index, brand) {
  const secure = TLS_PORTS.has(Number(ep.port));
  const badge = secure ? '\u26a1' : '\ud83d\udfe1';
  const colo = ep.colo || 'CF';
  const ping = ep.latency ? `${Math.round(ep.latency)}ms` : '-';
  const tail = secure ? '' : ` | \ud83d\udd0c${ep.port}`;
  return `@${brand} | ${badge} VLESS | \ud83c\udf0d GLOBAL | ${ping} | ${colo}${tail} | #${index}`;
}

function links(eps, uuid, host, brand) {
  return eps.map((ep, i) => {
    const secure = TLS_PORTS.has(Number(ep.port));
    const params = new URLSearchParams({
      encryption: 'none',
      security: secure ? 'tls' : 'none',
      type: 'ws',
      host,
      path: WS_PATH,
    });
    if (secure) {
      params.set('sni', host);
      params.set('fp', 'chrome');
      params.set('alpn', 'http/1.1');
    }
    const query = params.toString();
    const label = encodeURIComponent(remark(ep, i + 1, brand));
    return `vless://${uuid}@${ep.ip}:${ep.port}?${query}#${label}`;
  });
}

function clashProfile(eps, uuid, host, brand) {
  const proxies = eps.map((ep, i) => {
    const secure = TLS_PORTS.has(Number(ep.port));
    const name = remark(ep, i + 1, brand);
    return [
      `  - name: "${name.replace(/"/g, "'")}"`,
      '    type: vless',
      `    server: ${ep.ip}`,
      `    port: ${ep.port}`,
      `    uuid: ${uuid}`,
      '    udp: true',
      `    tls: ${secure}`,
      secure ? `    servername: ${host}` : null,
      secure ? '    client-fingerprint: chrome' : null,
      '    network: ws',
      '    ws-opts:',
      `      path: "${WS_PATH}"`,
      '      headers:',
      `        Host: ${host}`,
    ]
      .filter(Boolean)
      .join('\n');
  });

  const names = eps.map((ep, i) => `      - "${remark(ep, i + 1, brand).replace(/"/g, "'")}"`).join('\n');

  return [
    `# ${brand} - generated on your own Cloudflare account`,
    'mixed-port: 7890',
    'allow-lan: false',
    'mode: rule',
    'log-level: warning',
    'proxies:',
    proxies.join('\n'),
    'proxy-groups:',
    `  - name: "${brand}"`,
    '    type: url-test',
    '    url: http://cp.cloudflare.com/generate_204',
    '    interval: 300',
    '    tolerance: 50',
    '    proxies:',
    names,
    'rules:',
    `  - MATCH,${brand}`,
    '',
  ].join('\n');
}

function singboxOutbounds(eps, uuid, host, brand) {
  return eps.map((ep, i) => {
    const secure = TLS_PORTS.has(Number(ep.port));
    const outbound = {
      type: 'vless',
      tag: remark(ep, i + 1, brand),
      server: ep.ip,
      server_port: Number(ep.port),
      uuid,
      packet_encoding: 'xudp',
      transport: { type: 'ws', path: WS_PATH, headers: { Host: host }, early_data_header_name: 'Sec-WebSocket-Protocol' },
    };
    if (secure) {
      outbound.tls = { enabled: true, server_name: host, utls: { enabled: true, fingerprint: 'chrome' } };
    }
    return outbound;
  });
}

function b64utf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = '';
  for (let i = 0; i < bytes.length; i += 1) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function jsonResponse(payload) {
  return new Response(JSON.stringify(payload, null, 2), {
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
  });
}

function textResponse(body, brand) {
  return new Response(body, {
    headers: {
      'content-type': 'text/plain; charset=utf-8',
      'profile-title': `base64:${b64utf8(brand)}`,
      'profile-update-interval': '6',
      'cache-control': 'no-store',
    },
  });
}

function camouflage(brand) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${brand} status</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#fbfbfd;color:#1d1d20;font:400 16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif}main{text-align:center}h1{font-size:1.25rem;font-weight:600;margin:0 0 .25rem}p{margin:0;color:#6b6b75;font-size:.875rem}</style></head><body><main><h1>Service is running</h1><p>All systems operational.</p></main></body></html>`;
}

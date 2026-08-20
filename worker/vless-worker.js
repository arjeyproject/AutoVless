export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const hostname = url.hostname;
    try {
      if (url.pathname === '/health') return new Response('OK', { status: 200 });
      const kv = env.AUTOVLESS_KV;
      if (!kv) return new Response('KV not ready', { status: 503 });
      const ipsData = await kv.get('ips', 'json') || [];
      const proxyIp = url.searchParams.get('proxyip');
      let ip, port;
      if (proxyIp && proxyIp !== 'false') {
        [ip, port] = proxyIp.split(':');
      } else if (ipsData.length) {
        const selected = ipsData[Math.floor(Math.random() * ipsData.length)];
        ip = selected.ip;
        port = selected.port;
      } else {
        return new Response('No IPs available', { status: 503 });
      }
      const isTls = [443, 2053, 2083, 2087, 2096, 8443].includes(parseInt(port));
      const protocol = isTls ? 'https' : 'http';
      const upstreamReq = new Request(
        `${protocol}://${ip}:${port}${url.pathname}${url.search}`,
        { method: request.method, headers: {...request.headers, 'Host': hostname}, body: request.body, duplex: 'half' }
      );
      return await fetch(upstreamReq);
    } catch (e) {
      return new Response(`Error: ${e.message}`, { status: 500 });
    }
  }
};

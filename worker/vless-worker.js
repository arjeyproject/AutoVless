export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);
      const kv = env.AUTOVLESS_KV;
      if (!kv) return new Response('KV not configured', {status: 500});
      
      // Get clean IPs from KV
      const ipsRaw = await kv.get('ips');
      if (!ipsRaw) return new Response('No IPs', {status: 503});
      
      const ips = JSON.parse(ipsRaw);
      if (!ips.length) return new Response('Empty IPs', {status: 503});
      
      // Select random IP
      const ip = ips[Math.floor(Math.random() * ips.length)];
      const protocol = [443, 2053, 2083, 2087, 2096, 8443].includes(ip.port) ? 'https' : 'http';
      
      // Forward to clean IP
      const upstream = `${protocol}://${ip.ip}:${ip.port}${url.pathname}${url.search}`;
      const req = new Request(upstream, {
        method: request.method,
        headers: {...request.headers, 'Host': url.hostname},
        body: request.body,
        duplex: 'half'
      });
      
      return await fetch(req);
    } catch (e) {
      return new Response(`Error: ${e.message}`, {status: 500});
    }
  }
};

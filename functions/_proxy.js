const HOP_BY_HOP = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"]);

export function proxyToOrigin(request, env) {
  const origin = String(env.AUTOVLESS_ORIGIN || "").trim().replace(/\/+$/, "");
  if (!origin || !/^https:\/\//i.test(origin)) {
    return new Response("AUTOVLESS_ORIGIN is not configured", { status: 503 });
  }

  const incoming = new URL(request.url);
  const target = new URL(origin + incoming.pathname + incoming.search);
  const headers = new Headers(request.headers);
  for (const name of HOP_BY_HOP) headers.delete(name);
  headers.set("x-forwarded-host", incoming.host);
  headers.set("x-forwarded-proto", incoming.protocol.replace(":", ""));
  headers.set("cache-control", "no-store");

  return fetch(new Request(target, {
    method: request.method,
    headers,
    body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
    redirect: "manual"
  }));
}

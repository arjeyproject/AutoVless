import { proxyToOrigin } from "../../_proxy.js";

export async function onRequest(context) {
  return proxyToOrigin(context.request, context.env);
}

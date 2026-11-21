import { NextResponse } from "next/server";
import { apiBase, sessionToken } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP = new Set(["connection", "keep-alive", "transfer-encoding", "content-encoding", "content-length", "host"]);

/** Same-origin proxy: forwards the request to the API with the HttpOnly session token. The browser never sees the token.
 * Bodies are limited by the platform (serverless ~4.5 MB); file uploads/downloads use scoped short tokens directly instead. */
async function handle(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const token = await sessionToken();
  const url = new URL(req.url);
  const target = `${apiBase()}/api/${path.map(encodeURIComponent).join("/")}${url.search}`;
  const headers: Record<string, string> = {};
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  if (token) headers["authorization"] = `Bearer ${token}`;
  const accept = req.headers.get("accept");
  if (accept) headers["accept"] = accept;
  const method = req.method.toUpperCase();
  const body = method === "GET" || method === "HEAD" ? undefined : Buffer.from(await req.arrayBuffer());
  let upstream: Response;
  try {
    upstream = await fetch(target, { method, headers, body, cache: "no-store", redirect: "manual" });
  } catch {
    return NextResponse.json({ detail: "API unreachable (it may be waking up). Retry in a few seconds." }, { status: 503 });
  }
  const out = new Headers();
  upstream.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase())) out.set(k, v); });
  out.set("cache-control", "no-store");
  return new NextResponse(upstream.body, { status: upstream.status, headers: out });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };

import { NextResponse } from "next/server";
import { apiBase, sessionToken } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;

/** How long to wait on the API before answering the browser.
 *
 * The API runs on a free plan that sleeps when idle and takes 30-60 s to wake. Holding the request until the platform
 * kills the function produced a bare 504 with no body, which the interface could only report as "Could not load".
 * Waiting a bounded time and answering 503 with a reason instead lets the client retry on its own, so the first page
 * after a sleep recovers rather than failing. */
const UPSTREAM_TIMEOUT_MS = 25_000;

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
    upstream = await fetch(target, { method, headers, body, cache: "no-store", redirect: "manual", signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
  } catch (err: any) {
    const waking = err?.name === "TimeoutError" || err?.name === "AbortError";
    return NextResponse.json({
      detail: waking
        ? "The analysis API did not answer in time. Free-plan services sleep when idle and can take up to a minute to wake; this request will be retried."
        : "The analysis API is not reachable right now.",
      waking,
      retryable: true,
    }, { status: 503, headers: { "retry-after": "5" } });
  }
  const out = new Headers();
  upstream.headers.forEach((v, k) => { if (!HOP.has(k.toLowerCase())) out.set(k, v); });
  out.set("cache-control", "no-store");
  return new NextResponse(upstream.body, { status: upstream.status, headers: out });
}

export { handle as GET, handle as POST, handle as PUT, handle as PATCH, handle as DELETE };

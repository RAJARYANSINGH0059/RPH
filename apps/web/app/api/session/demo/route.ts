import { NextResponse } from "next/server";
import { apiBase, cookieOptions, sameOrigin } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;  // a cold free-plan API can take 30-60 s to answer the first request

/** One-click demo: the API creates an isolated demo principal; the token lives only in an HttpOnly cookie on this origin. */
export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-site session creation refused" }, { status: 403 });
  const forward = req.headers.get("x-forwarded-for") || "";
  const call = (ms: number) => fetch(`${apiBase()}/api/auth/demo-session`, {
    method: "POST",
    headers: { origin: req.headers.get("origin") || "", "x-forwarded-for": forward },
    cache: "no-store",
    signal: AbortSignal.timeout(ms),
  });
  let upstream: Response;
  try {
    // First attempt is short; a sleeping free-plan instance starts waking during it, so one longer retry usually lands.
    try {
      upstream = await call(12_000);
    } catch {
      upstream = await call(40_000);
    }
  } catch {
    return NextResponse.json({ detail: "The API did not answer in time (free-plan services can take 30–60 s to wake). Wait a few seconds and press SIGN IN again." }, { status: 503 });
  }
  const body = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json(body, { status: upstream.status });
  const res = NextResponse.json({ user: body.user, expires_at: body.expires_at, workspace: body.workspace, notice: body.notice });
  res.cookies.set({ ...cookieOptions(4 * 3600), value: body.access_token });
  return res;
}

import { NextResponse } from "next/server";
import { apiBase, cookieOptions, sameOrigin } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/** One-click demo: the API creates an isolated demo principal; the token lives only in an HttpOnly cookie on this origin. */
export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-site session creation refused" }, { status: 403 });
  const forward = req.headers.get("x-forwarded-for") || "";
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/api/auth/demo-session`, { method: "POST", headers: { origin: req.headers.get("origin") || "", "x-forwarded-for": forward }, cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "The API is not reachable right now (free-tier services can take 30–60 s to wake). Try again shortly." }, { status: 503 });
  }
  const body = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json(body, { status: upstream.status });
  const res = NextResponse.json({ user: body.user, expires_at: body.expires_at, workspace: body.workspace, notice: body.notice });
  res.cookies.set({ ...cookieOptions(4 * 3600), value: body.access_token });
  return res;
}

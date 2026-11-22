import { NextResponse } from "next/server";
import { apiBase, cookieOptions, sameOrigin } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
export const maxDuration = 60;  // the API runs on a free plan that can take 30-60 s to wake

/** Protected staff sign-in. Credentials are forwarded once to the API and never stored; the JWT goes into the HttpOnly cookie. */
export async function POST(req: Request) {
  if (!sameOrigin(req)) return NextResponse.json({ detail: "Cross-site sign-in refused" }, { status: 403 });
  const creds = await req.json().catch(() => null);
  if (!creds?.email || !creds?.password) return NextResponse.json({ detail: "email and password required" }, { status: 400 });
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBase()}/api/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: creds.email, password: creds.password }), cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "The API is not reachable right now. Try again shortly." }, { status: 503 });
  }
  const body = await upstream.json().catch(() => ({}));
  if (!upstream.ok) return NextResponse.json(body, { status: upstream.status });
  const res = NextResponse.json({ user: body.user });
  res.cookies.set({ ...cookieOptions(8 * 3600), value: body.access_token });
  return res;
}

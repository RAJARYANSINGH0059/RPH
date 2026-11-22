import { NextResponse } from "next/server";
import { apiBase, cookieOptions, csrfCookieOptions, sessionToken } from "@/lib/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST() {
  const token = await sessionToken();
  if (token) {
    try { await fetch(`${apiBase()}/api/auth/logout`, { method: "POST", headers: { Authorization: `Bearer ${token}` }, cache: "no-store" }); } catch { /* best effort */ }
  }
  const res = NextResponse.json({ ok: true });
  res.cookies.set({ ...cookieOptions(0), value: "" });
  res.cookies.set(csrfCookieOptions(0, ""));  // the paired CSRF cookie goes with the session
  return res;
}

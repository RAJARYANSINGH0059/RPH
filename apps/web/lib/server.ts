/** Server-only helpers for the BFF routes (never imported by client components). */
import { cookies } from "next/headers";

export const COOKIE = "ps05x_session";
export const apiBase = () => (process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
export const isProd = () => process.env.NODE_ENV === "production";

export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE)?.value || null;
}

export function cookieOptions(maxAgeSeconds: number) {
  return { name: COOKIE, httpOnly: true, secure: isProd(), sameSite: "lax" as const, path: "/", maxAge: maxAgeSeconds };
}

/** Same-site check for session-creating routes: the browser's Origin (or Referer) must match this deployment's host. */
export function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin") || (req.headers.get("referer") ? new URL(req.headers.get("referer")!).origin : "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "";
  if (!origin) return false;
  try { return new URL(origin).host === host; } catch { return false; }
}

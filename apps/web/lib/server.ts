/** Server-only helpers for the BFF routes (never imported by client components). */
import { cookies } from "next/headers";

export const COOKIE = "ps05x_session";
/** Readable by scripts on this origin, by design: the browser must echo it back in a header (double submit). */
export const CSRF_COOKIE = "ps05x_csrf";
export const apiBase = () => (process.env.API_BASE_URL || process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
export const isProd = () => process.env.NODE_ENV === "production";

export async function sessionToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(COOKIE)?.value || null;
}

export function cookieOptions(maxAgeSeconds: number) {
  return { name: COOKIE, httpOnly: true, secure: isProd(), sameSite: "lax" as const, path: "/", maxAge: maxAgeSeconds };
}

export function csrfCookieOptions(maxAgeSeconds: number, value: string) {
  // Not HttpOnly: the page has to read it to echo it back. It is not a credential on its own; the session cookie is.
  return { name: CSRF_COOKIE, value, httpOnly: false, secure: isProd(), sameSite: "lax" as const, path: "/", maxAge: maxAgeSeconds };
}

export function newCsrfToken(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(24)), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time-ish comparison; the values are same-length hex, so a simple accumulate is enough here. */
function equals(a: string, b: string): boolean {
  if (a.length !== b.length || a.length === 0) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Double-submit check for a state-changing request: the header must match the cookie this origin set. */
export async function csrfOk(req: Request): Promise<boolean> {
  const store = await cookies();
  const cookie = store.get(CSRF_COOKIE)?.value || "";
  const header = req.headers.get("x-csrf-token") || "";
  return equals(cookie, header);
}

/** Same-site check for session-creating routes: the browser's Origin (or Referer) must match this deployment's host. */
export function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin") || (req.headers.get("referer") ? new URL(req.headers.get("referer")!).origin : "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "";
  if (!origin) return false;
  try { return new URL(origin).host === host; } catch { return false; }
}

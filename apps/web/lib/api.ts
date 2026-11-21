"use client";

/** Browser-side API client. Authenticated calls go through the same-origin BFF proxy (`/api/proxy/*`), which attaches the
 * HttpOnly session cookie server-side. No token is ever stored in localStorage; only a display profile (name/role) is kept
 * so the shell can render before the first round trip. Large binary transfers (uploads/downloads) use a 10-minute scoped
 * token fetched through the proxy and go directly to the API to avoid serverless body limits. */

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const USER_KEY = "ps05x_profile_v4";
const CASE_KEY = "ps05x_case_context";

export type User = { id: string; email: string; display_name: string; role: string };

export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try { const u = window.localStorage.getItem(USER_KEY); return u ? (JSON.parse(u) as User) : null; } catch { return null; }
}
export function setProfile(user: User) { try { window.localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch { /* ignore */ } }
export function clearSession() { try { window.localStorage.removeItem(USER_KEY); } catch { /* ignore */ } }
export const isDemo = (u: User | null) => u?.role === "demo_analyst";
export const isReviewer = (u: User | null) => u?.role === "supervisor" || u?.role === "admin";

/** Selected case context (id + title) used by the sidebar to build case-scoped links. Not sensitive. */
export function getCaseContext(): { id: string; title: string } | null {
  if (typeof window === "undefined") return null;
  try { const c = window.localStorage.getItem(CASE_KEY); return c ? JSON.parse(c) : null; } catch { return null; }
}
export function setCaseContext(c: { id: string; title: string } | null) {
  try { if (c) window.localStorage.setItem(CASE_KEY, JSON.stringify(c)); else window.localStorage.removeItem(CASE_KEY); window.dispatchEvent(new Event("ps05x:case")); } catch { /* ignore */ }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function readError(res: Response): Promise<string> {
  let detail = res.statusText || `HTTP ${res.status}`;
  try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
  return detail;
}

function onUnauthorised() {
  if (typeof window === "undefined") return;
  clearSession();
  const p = window.location.pathname;
  if (p !== "/" && !p.startsWith("/staff")) window.location.href = "/?expired=1";
}

/** JSON call through the BFF proxy. `raw: true` downloads a Blob directly from the API with a scoped short token. */
export async function api<T = any>(path: string, init: RequestInit & { raw?: boolean } = {}): Promise<T> {
  if (init.raw) return (await download(path)) as unknown as T;
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`/api/proxy${path}`, { ...init, headers, credentials: "same-origin", cache: "no-store" });
  } catch {
    throw new ApiError(0, "Cannot reach the application server. Check your connection and try again.");
  }
  if (res.status === 401) onUnauthorised();
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

async function shortToken(scope: "upload" | "download"): Promise<string> {
  const r = await api<{ access_token: string }>("/auth/short-token", { method: "POST", body: JSON.stringify({ scope }) });
  return r.access_token;
}

export async function download(path: string): Promise<Blob> {
  const token = await shortToken("download");
  const res = await fetch(`${API_BASE}/api${path}`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return await res.blob();
}

export async function saveAs(path: string, filename: string) {
  const blob = await download(path);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** Multipart upload directly to the API (scoped token); the server applies the same checks as any upload. */
export async function upload<T = any>(path: string, form: FormData): Promise<T> {
  const token = await shortToken("upload");
  const res = await fetch(`${API_BASE}/api${path}`, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as T;
}

/** One-click synthetic demo session. The BFF creates the server-side session and sets the HttpOnly cookie. */
export async function signInDemo(): Promise<User> {
  const res = await fetch("/api/session/demo", { method: "POST", credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const j = await res.json();
  setProfile(j.user);
  return j.user;
}

export async function signInStaff(email: string, password: string): Promise<User> {
  const res = await fetch("/api/session/login", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const j = await res.json();
  setProfile(j.user);
  return j.user;
}

export async function signOut() {
  try { await fetch("/api/session/logout", { method: "POST", credentials: "same-origin" }); } catch { /* ignore */ }
  clearSession();
  setCaseContext(null);
}

export const paise = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `₹${(n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`);
export const fmtTime = (iso: string | null | undefined) => (iso ? new Date(iso).toISOString().replace("T", " ").slice(0, 19) + " UTC" : "unknown");
export const short = (s: string | null | undefined, n = 12) => (s ? (s.length > n ? s.slice(0, n) + "…" : s) : "—");

export const LEVEL_COLORS: Record<string, string> = {
  directly_observed: "#1f5fa8", corroborated: "#136f63", derived: "#5b6775", candidate: "#b7791f", contradicted: "#a33a3a", stale: "#8d6e63", insufficient: "#9aa3ad",
};
export const NODE_COLORS: Record<string, string> = {
  account: "#1f5fa8", vpa: "#2b7bbf", person: "#6c5ce7", phone: "#7b8794", email: "#7b8794", url: "#c0392b", domain: "#d35400", ip: "#8e44ad", asn: "#5d6d7e", hosting_provider: "#5d6d7e",
  evidence_file: "#2d3436", reference: "#95a5a6", payment_instruction: "#b66a4d",
};

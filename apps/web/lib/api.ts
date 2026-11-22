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
export function clearSession() { try { window.localStorage.removeItem(USER_KEY); } catch { /* ignore */ } invalidateCache(); }
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

/** The CSRF cookie is readable on purpose; the session cookie it is paired with is not. */
function readCsrfCookie(): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(/(?:^|;\s*)ps05x_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
/** Jittered backoff: 1s, 2s, 4s, 8s, then 10s, so a cold start is ridden out without hammering the API. */
const backoff = (attempt: number) => Math.round([1000, 2000, 4000, 8000, 10000][Math.min(attempt, 4)] * (0.75 + Math.random() * 0.5));

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

/* ---------------------------------------------------------------------------------------------------------------
 * Read cache. Every page in this app renders the shell (which needs /cases and /health/ready) and then its own data,
 * and each call is a round trip through the same-origin proxy to a free-plan API. Without a cache, revisiting a page
 * means waiting for all of that again, which is why navigation felt slow. GET results are therefore kept in memory for
 * the tab's lifetime: a revisit renders immediately from cache and revalidates in the background, identical in-flight
 * GETs are shared instead of duplicated, and any successful write clears the cache so nothing stale survives a change.
 * Nothing is written to disk or to browser storage, so no case data outlives the tab. */
const FRESH_MS = 30_000;       // within this window a cached GET is used as-is, with no background revalidation
const MAX_ENTRIES = 150;
const _cache = new Map<string, { at: number; data: unknown }>();
const _inflight = new Map<string, Promise<unknown>>();

export function peekCache<T>(path: string): { data: T; fresh: boolean } | null {
  const hit = _cache.get(path);
  if (!hit) return null;
  return { data: hit.data as T, fresh: Date.now() - hit.at < FRESH_MS };
}

export function invalidateCache() { _cache.clear(); }

function remember(path: string, data: unknown) {
  if (_cache.size >= MAX_ENTRIES) { const oldest = _cache.keys().next().value; if (oldest) _cache.delete(oldest); }
  _cache.delete(path);
  _cache.set(path, { at: Date.now(), data });
}

/** GET through the proxy, de-duplicated and cached. Concurrent callers for the same path share one request. */
export function apiGet<T = any>(path: string): Promise<T> {
  const running = _inflight.get(path);
  if (running) return running as Promise<T>;
  const p = request<T>(path, {})
    .then((d) => { if (isCacheable(d)) remember(path, d); return d; })
    .finally(() => { _inflight.delete(path); });
  _inflight.set(path, p);
  return p;
}

const isCacheable = (d: unknown) => d !== undefined && !(typeof Blob !== "undefined" && d instanceof Blob);

/** JSON call through the BFF proxy. `raw: true` downloads a Blob directly from the API with a scoped short token.
 * Plain GETs are served through the shared read cache (see above), so pages that fetch the same path on every visit
 * do not pay a fresh round trip each time; pass `fresh: true` to force the network. Writes always go to the network
 * and clear the cache. */
export async function api<T = any>(path: string, init: RequestInit & { raw?: boolean; fresh?: boolean } = {}): Promise<T> {
  if (init.raw) return (await download(path)) as unknown as T;
  const method = (init.method || "GET").toUpperCase();
  if (method === "GET" && !init.body) {
    if (init.fresh) _cache.delete(path);
    else { const hit = peekCache<T>(path); if (hit?.fresh) return hit.data; }
    return apiGet<T>(path);
  }
  return request<T>(path, init);
}

/** Raw call: no cache, no de-duplication. */
async function request<T = any>(path: string, init: RequestInit & { raw?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  // Double-submit: echo the CSRF cookie this origin set, so a cross-site page cannot forge a state-changing call.
  if ((init.method || "GET").toUpperCase() !== "GET") {
    const csrf = readCsrfCookie();
    if (csrf) headers["x-csrf-token"] = csrf;
  }
  // A sleeping free-plan API answers 503 (or the platform answers 504) until it has woken. Those are transient, so a
  // read is retried with jittered backoff inside a budget rather than reported as a failure the person must act on.
  const retryable = (status: number) => status === 503 || status === 504 || status === 502;
  const isRead = (init.method || "GET").toUpperCase() === "GET";
  const deadline = Date.now() + (isRead ? 70_000 : 20_000);
  let res!: Response;
  for (let attempt = 0; ; attempt++) {
    try {
      res = await fetch(`/api/proxy${path}`, { ...init, headers, credentials: "same-origin", cache: "no-store" });
    } catch {
      if (!isRead || Date.now() >= deadline) throw new ApiError(0, "Cannot reach the application server. Check your connection and try again.");
      await sleep(backoff(attempt));
      continue;
    }
    if (!retryable(res.status) || Date.now() >= deadline) break;
    await sleep(backoff(attempt));
  }
  if (res.status === 401) onUnauthorised();
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  // A write may change anything the user is looking at, so drop every cached read rather than guess which. Minting a
  // short-lived transfer token changes no data, so it is excluded.
  if ((init.method || "GET").toUpperCase() !== "GET" && !path.startsWith("/auth/short-token")) invalidateCache();
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.blob()) as unknown as T;
}

/** The case a transfer path belongs to, so the short token can be bound to it and cannot be replayed elsewhere. */
function caseOf(path: string): string | null {
  const m = path.match(/^\/cases\/([0-9a-f-]{36})(\/|$)/i);
  return m ? m[1] : null;
}

async function shortToken(scope: "upload" | "download", caseId: string | null): Promise<string> {
  const r = await api<{ access_token: string }>("/auth/short-token", { method: "POST", body: JSON.stringify({ scope, case_id: caseId }) });
  return r.access_token;
}

export async function download(path: string): Promise<Blob> {
  const token = await shortToken("download", caseOf(path));
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
  const token = await shortToken("upload", caseOf(path));
  const res = await fetch(`${API_BASE}/api${path}`, { method: "POST", body: form, headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  return (await res.json()) as T;
}

/** One-click synthetic demo session. The BFF creates the server-side session and sets the HttpOnly cookie. */
export async function signInDemo(): Promise<User> {
  // The API runs on a free plan that sleeps when idle: a cold start can take up to a minute, so the call is given a
  // generous but finite budget and always ends in a message the visitor can act on, never an endless spinner.
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), 90_000);
  let res: Response;
  try {
    res = await fetch("/api/session/demo", { method: "POST", credentials: "same-origin", cache: "no-store", signal: ctl.signal });
  } catch (e: any) {
    throw new ApiError(0, e?.name === "AbortError"
      ? "The analysis API did not answer within 90 seconds. Free-plan services sleep when idle; wait a few seconds and try again."
      : "Cannot reach the application server. Check your connection and try again.");
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw new ApiError(res.status, await readError(res));
  const j = await res.json();
  setProfile(j.user);
  return j.user;
}

/** Wake the API without authenticating, so the cold start happens while the visitor reads the landing page. */
export function warmApi(): void {
  try { void fetch("/api/proxy/health/live", { cache: "no-store", credentials: "same-origin" }).catch(() => undefined); } catch { /* ignore */ }
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

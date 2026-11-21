"use client";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "ps05x_token";
const USER_KEY = "ps05x_user";

export type User = { id: string; email: string; display_name: string; role: string };

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function getUser(): User | null {
  if (typeof window === "undefined") return null;
  try { const u = window.localStorage.getItem(USER_KEY); return u ? (JSON.parse(u) as User) : null; } catch { return null; }
}
export function setSession(token: string, user: User) {
  try { window.localStorage.setItem(TOKEN_KEY, token); window.localStorage.setItem(USER_KEY, JSON.stringify(user)); } catch { /* ignore */ }
}
export function clearSession() {
  try { window.localStorage.removeItem(TOKEN_KEY); window.localStorage.removeItem(USER_KEY); } catch { /* ignore */ }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function api<T = any>(path: string, init: RequestInit & { raw?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string> | undefined) };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init.body && !(init.body instanceof FormData)) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_BASE}. Is the backend running and NEXT_PUBLIC_API_BASE_URL set?`);
  }
  if (res.status === 401 && typeof window !== "undefined") {
    clearSession();
    if (!window.location.pathname.startsWith("/")) window.location.href = "/";
  }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j); } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (init.raw) return (await res.blob()) as unknown as T;
  return (await res.json()) as T;
}

export const paise = (n: number | null | undefined) => (n === null || n === undefined ? "—" : `₹${(n / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })}`);
export const fmtTime = (iso: string | null | undefined) => (iso ? new Date(iso).toISOString().replace("T", " ").slice(0, 19) + " UTC" : "unknown");

export const LEVEL_COLORS: Record<string, string> = {
  directly_observed: "#1f5fa8", corroborated: "#136f63", derived: "#5b6775", candidate: "#b7791f", contradicted: "#a33a3a", stale: "#8d6e63", insufficient: "#9aa3ad",
};
export const NODE_COLORS: Record<string, string> = {
  account: "#1f5fa8", vpa: "#2b7bbf", person: "#6c5ce7", phone: "#7b8794", email: "#7b8794", url: "#c0392b", domain: "#d35400", ip: "#8e44ad", asn: "#5d6d7e", hosting_provider: "#5d6d7e", evidence_file: "#2d3436", reference: "#95a5a6",
};

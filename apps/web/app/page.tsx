"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { api, getUser, setSession, API_BASE } from "@/lib/api";
import { Banner } from "@/components/Shell";

export default function SignIn() {
  const router = useRouter();
  const [email, setEmail] = useState("analyst@demo.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<string>("checking…");
  useEffect(() => {
    if (getUser()) router.replace("/cases");
    api("/health/ready").then((h) => setHealth(h.status)).catch((e) => setHealth(`unreachable (${e.message})`));
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      const r = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      setSession(r.access_token, r.user);
      router.push("/cases");
    } catch (err: any) { setError(err.message || "Sign-in failed"); } finally { setBusy(false); }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center p-4">
      <div className="card">
        <h1 className="text-2xl font-bold">PS05-X</h1>
        <p className="mb-3 text-sm text-ink-muted">Evidence-centred financial-cybercrime investigation workbench. Demo build for Rajasthan Police Cyber Security Hackathon 2026, PS05.</p>
        <Banner synthetic />
        <form onSubmit={submit} className="mt-4 space-y-3" aria-label="Sign in">
          <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
          <div><label className="label" htmlFor="password">Password</label><input id="password" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></div>
          {error && <div role="alert" className="rounded bg-[#fff5f5] p-2 text-sm text-[#8a1c1c]">{error}</div>}
          <button className="btn w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="mt-4 text-xs text-ink-muted">
          <p>Demo accounts are configured by the operator through <code>DEMO_*_PASSWORD</code> environment variables; no credentials are built in.</p>
          <p className="mt-1">API: <code>{API_BASE}</code> · readiness: <span className="font-medium">{health}</span></p>
          <p className="mt-2">Two paths after sign-in: <strong>Try a synthetic investigation</strong> (no keys, no confidential data) or <strong>Upload investigation files</strong> (only if you are authorised to process them).</p>
        </div>
      </div>
    </main>
  );
}

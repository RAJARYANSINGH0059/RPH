"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { I } from "@/components/icons";
import { api, API_BASE, getUser, setSession } from "@/lib/api";

const FEATURES = [
  { icon: <I.upload />, t: "Ingest messy evidence", d: "Statements in any column layout, complaint PDFs, technical observations. Every value keeps its raw text and exact cell, row or page." },
  { icon: <I.money />, t: "Follow the money", d: "Multi-hop fund paths across accounts, duplicate and date warnings, balance checks, triage signals that always say why." },
  { icon: <I.graph />, t: "Inspect every link", d: "Each relationship carries its source, time validity, method, limitations and counter-evidence. Shared hosting is never treated as proof." },
  { icon: <I.report />, t: "Export a defensible report", d: "PDF, JSON and CSV with hashes, locators, unresolved gaps and the human-verification disclaimer." },
];

export default function SignIn() {
  const router = useRouter();
  const [email, setEmail] = useState("analyst@demo.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<"checking" | "ready" | "down">("checking");
  useEffect(() => {
    if (getUser()) router.replace("/cases");
    api("/health/ready").then((h) => setHealth(h.status === "ready" ? "ready" : "down")).catch(() => setHealth("down"));
  }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError(null);
    try { const r = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); setSession(r.access_token, r.user); router.push("/cases"); }
    catch (err: any) { setError(err.status === 401 ? "Email or password is incorrect." : err.message || "Sign-in failed"); } finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(1200px_600px_at_10%_-10%,#e7eff9_0%,transparent_60%),radial-gradient(900px_500px_at_100%_0%,#f3e9dc_0%,transparent_55%)]">
      <div className="mx-auto grid min-h-screen max-w-6xl items-center gap-10 px-5 py-10 lg:grid-cols-[1.2fr_1fr]">
        <section>
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-line bg-white px-3 py-1 text-xs font-semibold text-ink-muted"><I.shield width={14} height={14} /> Rajasthan Police Cyber Security Hackathon 2026 · PS05</div>
          <h1 className="text-4xl font-extrabold leading-tight tracking-tight sm:text-5xl">Evidence-centred <span className="text-accent">money-trail</span> and infrastructure investigation</h1>
          <p className="mt-4 max-w-xl text-lg text-ink-muted">PS05-X turns bank statements, complaints and domain/IP observations into a time-aware evidence graph where every link can be checked, challenged and exported.</p>
          <div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide"><span className="rounded-full bg-synthetic px-2.5 py-0.5 text-white">Synthetic demo data</span><span className="rounded-full border border-synthetic/60 px-2.5 py-0.5 text-synthetic">No live police/bank connection</span><span className="rounded-full border border-line bg-white px-2.5 py-0.5 text-ink-muted">Human verification required</span></div>
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <div key={f.t} className="card flex gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-light text-accent">{f.icon}</div><div><div className="font-semibold">{f.t}</div><div className="mt-0.5 text-sm text-ink-muted">{f.d}</div></div></div>
            ))}
          </div>
          <div className="mt-6 rounded-xl border border-line bg-white/70 p-4 text-sm">
            <div className="mb-2 font-semibold">How a first session goes</div>
            <ol className="grid gap-2 sm:grid-cols-4">
              {["Sign in", "Generate a synthetic case", "Open graph, click a link", "Export the report"].map((s, i) => <li key={s} className="flex items-center gap-2"><span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-white">{i + 1}</span><span>{s}</span></li>)}
            </ol>
          </div>
        </section>
        <section className="card p-6 shadow-lg">
          <h2 className="text-xl font-bold">Sign in</h2>
          <p className="mb-4 text-sm text-ink-muted">Use the demo analyst account your operator configured.</p>
          <form onSubmit={submit} className="space-y-3" aria-label="Sign in">
            <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
            <div><label className="label" htmlFor="password">Password</label><input id="password" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus /></div>
            {error && <div role="alert" className="flex items-start gap-2 rounded-lg bg-[#fff5f5] p-2.5 text-sm text-[#8a1c1c]"><I.alert /> {error}</div>}
            <button className="btn w-full justify-center" disabled={busy}>{busy ? "Signing in…" : <>Sign in <I.arrow /></>}</button>
          </form>
          <div className="mt-4 space-y-2 text-xs text-ink-muted">
            <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${health === "ready" ? "bg-[#136f63]" : health === "down" ? "bg-[#a33a3a]" : "bg-[#b7791f]"}`} />API {health === "ready" ? "ready" : health === "down" ? "unreachable" : "checking…"} · <code className="text-[11px]">{API_BASE}</code></div>
            <p>Demo accounts exist only when the operator sets <code>DEMO_*_PASSWORD</code> environment variables. Roles: analyst (investigate), supervisor (approve candidate links), admin (all cases, connector checks).</p>
            <p>Upload real files only when you are authorised to process them. Do not use personal data for demonstrations.</p>
          </div>
        </section>
      </div>
    </main>
  );
}

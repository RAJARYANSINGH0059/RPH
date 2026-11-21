"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { I } from "@/components/icons";
import { api, API_BASE, getUser, setSession } from "@/lib/api";

const FEATURES = [
  { icon: <I.upload />, t: "Ingest messy evidence", d: "Statements in any column layout, complaint PDFs, scans and screenshots (OCR), technical observations. Every value keeps its raw text and exact cell, row or page." },
  { icon: <I.money />, t: "Follow the money", d: "Multi-hop fund paths with unresolved hops made explicit, duplicate and date warnings, balance checks, triage signals that always say why." },
  { icon: <I.link />, t: "Correlate across cases", d: "Exact identifier and reference bridges between authorised cases; shared hosting stays a candidate with its counter-explanation." },
  { icon: <I.report />, t: "Prepare defensible packs", d: "Source-backed PDF/JSON reports, restitution-readiness reconciliation and cooperation request packs with hashes." },
];

export default function SignIn() {
  const router = useRouter();
  const [email, setEmail] = useState("analyst@demo.local");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [health, setHealth] = useState<"checking" | "ready" | "down">("checking");
  const check = () => api("/health/ready").then((h) => setHealth(h.status === "ready" ? "ready" : "down")).catch(() => setHealth("down"));
  useEffect(() => { if (getUser()) router.replace("/cases"); check(); }, [router]);

  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { const r = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }); setSession(r.access_token, r.user); router.push("/cases"); }
    catch (err: any) { setError(err.status === 401 ? "Email or password is incorrect." : err.status === 0 ? "The API is not reachable. Check the API URL below and that the backend is running." : err.message || "Sign-in failed"); }
    finally { setBusy(false); }
  }

  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[1.15fr_1fr]">
      <section className="jaali relative hidden overflow-hidden bg-rail px-10 py-12 text-rail-text lg:flex lg:flex-col lg:justify-between">
        <div className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full border border-white/10" aria-hidden />
        <div className="pointer-events-none absolute -right-10 -top-10 h-64 w-64 rounded-full border border-saffron/30" aria-hidden />
        <div className="pointer-events-none absolute -bottom-32 -left-20 h-[28rem] w-[28rem] rounded-full border border-accent/30" aria-hidden />
        <div>
          <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-white shadow"><I.shield /></div><div><div className="text-lg font-bold text-white">PS05-X</div><div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-rail-text/70">Investigative prototype</div></div></div>
          <h1 className="mt-10 max-w-xl text-4xl font-extrabold leading-tight tracking-tight text-white">Evidence-centred <span className="text-saffron">money-trail</span> and infrastructure investigation</h1>
          <p className="mt-4 max-w-lg text-base text-rail-text/85">A workstation for cyber-enabled financial fraud: ingest bank statements, complaints and domain/IP observations into a time-aware evidence graph where every link can be checked, challenged, correlated across cases and exported.</p>
          <ul className="mt-8 grid gap-3 sm:grid-cols-2">
            {FEATURES.map((f) => <li key={f.t} className="rounded-xl border border-white/10 bg-white/5 p-3"><div className="flex items-center gap-2 text-white"><span className="text-saffron">{f.icon}</span><span className="font-semibold">{f.t}</span></div><p className="mt-1 text-xs text-rail-text/80">{f.d}</p></li>)}
          </ul>
        </div>
        <div className="mt-10 flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide"><span className="rounded-full bg-terracotta px-2.5 py-0.5 text-white">Synthetic demo data</span><span className="rounded-full border border-terracotta/70 px-2.5 py-0.5 text-terracotta">No live police/bank connection</span><span className="rounded-full border border-white/20 px-2.5 py-0.5 text-rail-text/80">Human verification required</span><span className="rounded-full border border-white/20 px-2.5 py-0.5 text-rail-text/80">Rajasthan Police Cyber Security Hackathon 2026 · PS05</span></div>
      </section>
      <section className="flex items-center justify-center p-6 sm:p-10">
        <div className="w-full max-w-md">
          <div className="mb-6 lg:hidden"><div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-white"><I.shield /></div><div><div className="text-lg font-bold">PS05-X</div><div className="eyebrow">Investigative prototype</div></div></div><div className="mt-3 flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide"><span className="rounded-full bg-terracotta px-2.5 py-0.5 text-white">Synthetic demo</span><span className="rounded-full border border-terracotta/60 px-2.5 py-0.5 text-terracotta">No live police/bank connection</span></div></div>
          <div className="card p-6">
            <div className="eyebrow">Sign in</div>
            <h2 className="mt-1 text-xl font-bold">Investigator workstation</h2>
            <p className="mb-4 text-sm muted">Use the demo account your operator configured. Roles: analyst (investigate), supervisor (approve candidate links, endorse packs), admin.</p>
            <form onSubmit={submit} className="space-y-3" aria-label="Sign in">
              <div><label className="label" htmlFor="email">Email</label><input id="email" className="input" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></div>
              <div><label className="label" htmlFor="password">Password</label><input id="password" type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" autoFocus /></div>
              {error && <div role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft p-2.5 text-sm text-danger"><I.alert className="shrink-0" /> {error}</div>}
              <button className="btn w-full justify-center" disabled={busy || health === "down"}>{busy ? "Signing in…" : <>Sign in <I.arrow /></>}</button>
            </form>
            <div className="mt-4 space-y-2 text-xs muted">
              <div className="flex items-center gap-2"><span className={`h-2 w-2 rounded-full ${health === "ready" ? "bg-ok" : health === "down" ? "bg-danger" : "bg-saffron"}`} />API {health === "ready" ? "ready" : health === "down" ? "unreachable" : "checking…"} · <span className="mono">{API_BASE}</span>{health === "down" && <button className="underline" onClick={check}>retry</button>}</div>
              <p>Demo accounts exist only when the operator sets <span className="mono">DEMO_*_PASSWORD</span>. Upload real files only when authorised; never use personal data for demonstrations.</p>
            </div>
          </div>
          <ol className="mt-5 grid grid-cols-4 gap-2 text-center text-[11px] muted">{["Sign in", "Generate a case", "Inspect a link", "Export a pack"].map((s, i) => <li key={s} className="inset p-2"><div className="mx-auto mb-1 flex h-6 w-6 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white">{i + 1}</div>{s}</li>)}</ol>
        </div>
      </section>
    </main>
  );
}

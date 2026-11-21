"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { MotionScene } from "@/components/motion";
import { I } from "@/components/icons";
import { getUser, signInDemo } from "@/lib/api";

function SignIn() {
  const router = useRouter();
  const params = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (getUser() && !params.get("expired")) router.replace("/overview"); }, [router, params]);
  async function enter() {
    setBusy(true); setError(null);
    try { await signInDemo(); router.push("/overview"); }
    catch (e: any) { setError(e.message || "Could not start the demo session."); setBusy(false); }
  }
  return (
    <main className="min-h-screen md:grid md:grid-cols-[1.05fr_1fr]">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-rail p-10 text-rail-text md:flex jaali">
        <div>
          <div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white shadow"><I.shield width={22} height={22} /></div><div><div className="text-xl font-bold tracking-tight text-white">PS05-X</div><div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-rail-text/70">Investigative prototype · Rajasthan Police Hackathon 2026 · PS05</div></div></div>
          <h1 className="mt-10 max-w-xl text-3xl font-bold leading-tight text-white">Reconstruct the operation behind the money trail, then try to break your own conclusions.</h1>
          <p className="mt-4 max-w-xl text-sm leading-relaxed text-rail-text/85">Ingest → validate → reconstruct → challenge → identify missing evidence → compare scenarios → prepare authorised next steps → reproduce. Every finding carries its source locator, hash, method version, counter-evidence and limitations.</p>
          <ul className="mt-6 grid gap-2 text-sm text-rail-text/90 sm:grid-cols-2">
            {["QR / UPI instruction → recorded transaction bridge", "Bounded fund attribution under balance constraints", "Evidence Adversary with alternative explanations", "FATF-attributed lifecycle and dependency map", "Account-control timeline (holder ≠ controller)", "Proof manifests verified offline"].map((t: any) => <li key={t} className="flex items-start gap-2"><I.check className="mt-0.5 shrink-0 text-accent" width={14} height={14} />{t}</li>)}
          </ul>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-3"><MotionScene scene="login" height={150} /></div>
      </section>
      <section className="flex min-h-screen flex-col items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-md">
          <div className="mb-6 flex items-center gap-3 md:hidden"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-white"><I.shield /></div><div><div className="text-lg font-bold">PS05-X</div><div className="text-[10px] font-semibold uppercase tracking-[0.14em] muted">Investigative prototype</div></div></div>
          <div className="eyebrow">Public synthetic demo</div>
          <h2 className="mt-1 text-3xl font-bold tracking-tight">Enter the demo workspace</h2>
          <p className="mt-2 text-sm muted">One click creates an isolated, time-limited workspace with synthetic data only. No email, password or OTP. Nothing you do here touches a real case.</p>
          <button onClick={enter} disabled={busy} className="btn mt-6 w-full justify-center py-4 text-lg font-bold" aria-busy={busy}>
            {busy ? <><span className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden /> Entering secure demo workspace…</> : <>SIGN IN <I.arrow /></>}
          </button>
          {params.get("expired") && !error && <p className="mt-3 text-sm warn" role="status">Your previous session ended. Sign in again to continue.</p>}
          {error && <div role="alert" className="mt-3 rounded-lg bg-danger-soft p-3 text-sm text-danger"><div className="font-semibold">Could not enter the demo</div><div>{error}</div><button className="btn-secondary mt-2" onClick={enter}>Try again</button></div>}
          <div className="mt-6 rounded-xl border border-terracotta/40 bg-terracotta-soft p-3 text-xs"><span className="font-semibold uppercase tracking-wide text-terracotta">Synthetic demo — not real case data.</span> Every record is fictional (reserved .test domains, documentation IP ranges, invented banks). No live police, bank, telecom or registrar connection exists.</div>
          <div className="mt-8 flex flex-wrap items-center justify-between gap-2 text-xs muted">
            <Link href="/staff/login" className="underline hover:text-ink">Staff sign-in (protected)</Link>
            <span>v0.4 · Render API · Vercel web</span>
          </div>
        </div>
      </section>
    </main>
  );
}

export default function Page() {
  return <Suspense fallback={null}><SignIn /></Suspense>;
}

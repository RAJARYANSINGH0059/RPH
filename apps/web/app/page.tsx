"use client";

/** Entry page. Two panels: an editorial introduction to what PS05-X is, and a single unmistakable way in.
 * The public demo creates a server-side, isolated, expiring synthetic workspace with no credentials; staff sign-in
 * stays behind its own protected route. Neither path weakens authentication or role checks. */
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { MotionScene } from "@/components/motion";
import { I } from "@/components/icons";
import { getUser, signInDemo, warmApi } from "@/lib/api";

const CAPABILITIES = [
  ["Fund-trail reconstruction", "Multi-hop paths with hop classes, split and merge flags, and unresolved ends named, not hidden."],
  ["Bounded fund provenance", "A feasible minimum and maximum per transfer under the recorded balances, never a false exact figure."],
  ["Proof-carrying evidence", "Every derivation exports a manifest that reproduces offline from the cited source rows."],
  ["Evidence adversary", "Each relationship is challenged with the innocent explanations that would also fit."],
];

function SignIn() {
  const router = useRouter();
  const params = useSearchParams();
  const [busy, setBusy] = useState(false);
  const [waited, setWaited] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { if (getUser() && !params.get("expired")) router.replace("/overview"); }, [router, params]);
  useEffect(() => { warmApi(); }, []);  // wake the sleeping free-plan API while the visitor reads this page
  useEffect(() => {
    if (!busy) { setWaited(0); return; }
    const started = Date.now();
    const t = setInterval(() => setWaited(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, [busy]);

  async function enter() {
    setBusy(true); setError(null);
    try {
      await signInDemo();
      // Full document load rather than a client-side push: the session cookie is applied to a fresh document and a
      // stalled payload can never leave the button spinning with no way out.
      window.location.assign("/overview");
    } catch (e: any) {
      setError(e?.message || "Could not start the demo session.");
      setBusy(false);
    }
  }

  const waitNote = waited >= 8 ? "The analysis API is waking up. Free-plan services sleep when idle, so the first visit can take up to a minute." : null;

  return (
    <main className="min-h-screen lg:grid lg:grid-cols-[1.08fr_1fr]">
      {/* Left: what this is, in the product's own editorial voice. */}
      <section className="jaali relative flex flex-col justify-between overflow-hidden bg-rail p-8 text-rail-text md:p-12">
        <div>
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white shadow"><I.shield width={22} height={22} /></div>
            <div>
              <div className="text-lg font-bold leading-tight tracking-tight text-white">PS05-X</div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-rail-text/70">Investigative prototype</div>
            </div>
          </div>

          <h1 className="display mt-10 max-w-xl text-[34px] leading-[1.08] text-white md:text-[46px]">Investigative Intelligence Workbench</h1>
          <p className="mt-5 max-w-xl text-[15px] leading-relaxed text-rail-text/85">
            An evidence-centred environment for financial cybercrime investigation, fund-trail reconstruction and digital evidence analysis.
            Every finding carries its source locator, hash, method version, counter-evidence and limitations.
          </p>

          <dl className="mt-9 max-w-xl space-y-4">
            {CAPABILITIES.map(([name, what]) => (
              <div key={name} className="flex gap-3">
                <I.check className="mt-1 shrink-0 text-accent" width={15} height={15} />
                <div>
                  <dt className="text-[14px] font-semibold text-white">{name}</dt>
                  <dd className="mt-0.5 text-[13px] leading-relaxed text-rail-text/70">{what}</dd>
                </div>
              </div>
            ))}
          </dl>
        </div>

        <div className="mt-10 rounded-2xl border border-white/10 bg-white/5 p-3">
          <MotionScene scene="login" height={150} />
        </div>
      </section>

      {/* Right: one way in, and an honest account of what the visitor is entering. */}
      <section className="flex min-h-screen flex-col items-center justify-center p-6 md:p-12">
        <div className="w-full max-w-md">
          <div className="eyebrow">Public synthetic demo</div>
          <h2 className="display mt-2 text-[30px] leading-tight md:text-[34px]">Enter the demo workspace</h2>
          <p className="mt-3 text-[15px] leading-relaxed muted">
            One click creates an isolated, time-limited workspace containing synthetic data only. No email, password or one-time code.
            Nothing you do here touches a real case.
          </p>

          <button onClick={enter} disabled={busy} className="btn mt-7 w-full justify-center py-4 text-[15px] font-bold tracking-wide" aria-busy={busy}>
            {busy
              ? <><span className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" aria-hidden /> Preparing your workspace{waited >= 3 ? ` · ${waited}s` : ""}</>
              : <>Enter synthetic demo <I.arrow /></>}
          </button>

          {busy && waitNote && <p className="mt-3 text-sm muted" role="status">{waitNote}</p>}
          {busy && waited >= 25 && (
            <button className="btn-secondary mt-2 w-full justify-center" onClick={() => { setBusy(false); setError("Cancelled. The API may still be waking up; try again in a few seconds."); }}>
              Cancel and try again
            </button>
          )}
          {params.get("expired") && !error && !busy && <p className="mt-3 text-sm warn" role="status">Your previous session ended. Enter again to continue.</p>}
          {error && (
            <div role="alert" className="mt-3 rounded-xl bg-danger-soft p-3 text-sm text-danger">
              <div className="font-semibold">Could not enter the demo</div>
              <div className="mt-0.5">{error}</div>
              <button className="btn-secondary mt-2" onClick={enter}>Try again</button>
            </div>
          )}

          <div className="mt-7 rounded-2xl border border-terracotta/40 bg-terracotta-soft p-3.5 text-[13px] leading-relaxed">
            <span className="font-semibold uppercase tracking-wide text-terracotta">Synthetic demo — not real case data.</span>{" "}
            Every record is fictional: reserved <span className="mono">.test</span> domains, documentation IP ranges, invented banks.
            No live police, bank, telecom or registrar connection exists, and a demo analyst can never open uploaded evidence.
          </div>

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

"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

const SCENARIO_HELP: Record<string, string> = {
  phishing_to_mule: "Victim clicks a fake KYC link and pays a mule VPA; funds hop through two accounts to an exit.",
  fake_customer_care: "A fake support number convinces the victim to pay a “refund fee”.",
  fake_loan_job: "A processing fee for a loan or job that never comes.",
  investment_scam: "Large deposits into a “guaranteed returns” scheme.",
  qr_marketplace: "A buyer sends a QR code that debits instead of credits the seller.",
  multi_victim_network: "Several victims pay the same collection accounts; good for cross-case patterns.",
};
const DIFF_HELP: Record<string, string> = {
  clean: "Complete fields, one layout, no decoys. Best to learn the tool.",
  messy: "Missing names, some ambiguous dates, a duplicate row, a balance mismatch, one decoy domain on a shared CDN.",
  high_noise: "More of everything plus OCR-style substitutions and similar names.",
  adversarial: "Adds a stale, conflicting DNS record and more decoys designed to look connected.",
};

export default function FactoryPage() {
  const [opts, setOpts] = useState<any>(null);
  const [form, setForm] = useState({ scenario_type: "phishing_to_mule", difficulty: "messy", size: "small", seed: 42 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  useEffect(() => { api("/synthetic/options").then(setOpts).catch((e) => setError(e.message)); }, []);

  async function generate(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null); setResult(null);
    try { setResult(await api("/synthetic/generate", { method: "POST", body: JSON.stringify(form) })); }
    catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }
  const Chips = ({ name, values, help }: { name: "scenario_type" | "difficulty" | "size"; values: string[]; help?: Record<string, string> }) => (
    <div role="radiogroup" aria-label={name} className="flex flex-wrap gap-1.5">
      {values.map((v) => <button type="button" key={v} role="radio" aria-checked={form[name] === v} title={help?.[v]} className={`chip ${form[name] === v ? "chip-on" : ""}`} onClick={() => setForm({ ...form, [name]: v })}>{v.replace(/_/g, " ")}</button>)}
    </div>
  );

  return (
    <Shell title="Synthetic Case Factory" subtitle="Generate a fictional investigation with hidden ground truth. Files pass through the ordinary upload pipeline." synthetic pageKey="factory">
      <div className="grid gap-4 lg:grid-cols-[420px_1fr]">
        <form onSubmit={generate} className="card space-y-4">
          <State loading={!opts && !error} error={!opts ? error : null}>
            <div><div className="label">1 · Scenario</div><Chips name="scenario_type" values={opts?.scenario_types || []} help={SCENARIO_HELP} /><p className="mt-1.5 text-xs text-ink-muted">{SCENARIO_HELP[form.scenario_type]}</p></div>
            <div><div className="label">2 · Difficulty</div><Chips name="difficulty" values={opts?.difficulties || []} help={DIFF_HELP} /><p className="mt-1.5 text-xs text-ink-muted">{DIFF_HELP[form.difficulty]}</p></div>
            <div className="grid grid-cols-2 gap-3">
              <div><div className="label">3 · Size</div><Chips name="size" values={opts?.sizes || []} /></div>
              <div><label className="label" htmlFor="seed">4 · Seed</label><input id="seed" type="number" min={0} className="input" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} /><p className="mt-1 text-[11px] text-ink-muted">Same seed ⇒ identical files.</p></div>
            </div>
            <button className="btn w-full justify-center" disabled={busy}>{busy ? <><span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" /> Generating and ingesting…</> : <><I.factory /> Generate case</>}</button>
            {opts && <p className="text-[11px] text-ink-muted">Generator v{opts.generator_version}. Ground truth is sealed in a benchmark-only store and is never served by case APIs.</p>}
          </State>
          {error && opts && <div role="alert" className="rounded-lg bg-danger-soft p-2.5 text-sm text-danger">{error}</div>}
        </form>
        <div>
          {!result && !busy && (
            <div className="card h-full border-dashed">
              <div className="label">What you will get</div>
              <ul className="grid gap-2 text-sm sm:grid-cols-2">
                {[["Bank statements", "CSV and XLSX, victims and first-layer accounts, three different column layouts"], ["Complaint PDF", "A short fictional complaint naming the URL, VPA and UTR"], ["Technical observations", "DNS, hosting/CDN, URL and RDAP entries with observation times"], ["Screenshot", "Noisy PNG for OCR testing (read only if an OCR engine is installed)"]].map(([t, d]) => <li key={t} className="flex gap-2 rounded-lg bg-canvas p-2.5"><I.file className="mt-0.5 shrink-0 text-accent" width={16} height={16} /><div><div className="font-medium">{t}</div><div className="text-xs text-ink-muted">{d}</div></div></li>)}
              </ul>
              <div className="callout mt-3"><I.shield className="shrink-0 text-accent" /><div>Everything is fictional: <code>.test</code> domains, documentation-only IP ranges, invented banks and VPAs, and a SYNTHETIC DATA watermark in every file.</div></div>
            </div>
          )}
          {busy && <div className="card flex items-center gap-3 text-sm text-ink-muted" role="status"><span className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />Generating truth → writing files → injecting noise → ingesting through the upload pipeline…</div>}
          {result && (
            <div className="space-y-3">
              <div className="card border-ok/30">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div><div className="flex items-center gap-2 font-semibold"><I.check className="text-ok" /> {result.case.title}</div><div className="text-xs text-ink-muted">{result.public_manifest.transactions_generated} transactions and {result.public_manifest.accounts_generated} accounts generated · {result.files.length} files ingested</div></div>
                  <div className="flex gap-2"><Link className="btn" href={`/cases/${result.case.id}`}>Open case <I.arrow /></Link><Link className="btn-secondary" href={`/cases/${result.case.id}/graph`}>Go to graph</Link></div>
                </div>
              </div>
              <div className="card overflow-x-auto p-0">
                <table className="data">
                  <thead><tr><th>File</th><th>Kind</th><th>Parser result</th><th>Warnings (information, not errors)</th></tr></thead>
                  <tbody>{result.files.map((f: any) => (
                    <tr key={f.file.id}><td className="font-medium">{f.file.original_name}<div className="mono text-[11px] text-ink-muted">sha256 {f.file.sha256.slice(0, 16)}…</div></td><td>{f.file.detected_kind}</td>
                      <td className="text-xs">{f.parse_run?.stats?.transactions !== undefined ? `${f.parse_run.stats.transactions} transactions` : f.parse_run?.stats?.observations !== undefined ? `${f.parse_run.stats.observations} observations` : `${f.parse_run?.stats?.blocks ?? 0} text blocks`}<div><span className={`badge ${f.file.status === "parsed" ? "bg-ok-soft text-ok" : "bg-saffron-soft text-warn"}`}>{f.file.status.replace("_", " ")}</span></div></td>
                      <td className="text-xs warn">{(f.parse_run?.warnings || []).slice(0, 4).map((w: string) => w.replace(/_/g, " ")).join("; ") || "—"}</td></tr>))}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}

"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api } from "@/lib/api";

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

  return (
    <Shell title="Synthetic Case Factory" synthetic>
      <div className="grid gap-4 lg:grid-cols-3">
        <form onSubmit={generate} className="card space-y-3">
          <p className="text-sm text-ink-muted">Truth is generated first, then artefacts, then controlled chaos. The public files are imported through the ordinary upload pipeline. Ground truth is sealed in a benchmark-only store.</p>
          <State loading={!opts && !error} error={!opts ? error : null}>
            <div><label className="label" htmlFor="sc">Scenario</label>
              <select id="sc" className="input" value={form.scenario_type} onChange={(e) => setForm({ ...form, scenario_type: e.target.value })}>{opts?.scenario_types.map((s: string) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select></div>
            <div><label className="label" htmlFor="df">Difficulty</label>
              <select id="df" className="input" value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value })}>{opts?.difficulties.map((s: string) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select></div>
            <div><label className="label" htmlFor="sz">Size</label>
              <select id="sz" className="input" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })}>{opts?.sizes.map((s: string) => <option key={s} value={s}>{s}</option>)}</select></div>
            <div><label className="label" htmlFor="seed">Seed</label><input id="seed" type="number" min={0} className="input" value={form.seed} onChange={(e) => setForm({ ...form, seed: Number(e.target.value) })} /></div>
            <button className="btn" disabled={busy}>{busy ? "Generating and ingesting…" : "Generate case"}</button>
            {opts && <p className="text-xs text-ink-muted">Generator v{opts.generator_version}. Same seed + version ⇒ identical files.</p>}
          </State>
          {error && opts && <div role="alert" className="rounded bg-[#fff5f5] p-2 text-sm text-[#8a1c1c]">{error}</div>}
        </form>
        <div className="lg:col-span-2">
          {!result && <div className="card text-sm text-ink-muted">Generated bundle and parser preview will appear here.</div>}
          {result && (
            <div className="space-y-3">
              <div className="card">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><div className="font-semibold">{result.case.title}</div><div className="text-xs text-ink-muted">scenario {result.public_manifest.scenario_type} · {result.public_manifest.difficulty} · seed {result.public_manifest.seed} · {result.public_manifest.transactions_generated} transactions generated</div></div>
                  <Link className="btn" href={`/cases/${result.case.id}`}>Open case</Link>
                </div>
                <p className="mt-2 text-xs text-synthetic">{result.public_manifest.watermark}</p>
              </div>
              <div className="card overflow-x-auto p-0">
                <table className="data">
                  <thead><tr><th>File</th><th>Kind</th><th>SHA-256</th><th>Parser</th><th>Status</th><th>Warnings</th></tr></thead>
                  <tbody>{result.files.map((f: any) => (
                    <tr key={f.file.id}><td>{f.file.original_name}</td><td>{f.file.detected_kind}</td><td className="font-mono text-xs">{f.file.sha256.slice(0, 16)}…</td><td>{f.parse_run?.parser_name}</td><td>{f.file.status}</td>
                      <td className="text-xs">{(f.parse_run?.warnings || []).slice(0, 4).join("; ") || "—"}</td></tr>))}</tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </Shell>
  );
}

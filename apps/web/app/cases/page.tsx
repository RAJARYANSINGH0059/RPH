"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, setCaseContext } from "@/lib/api";

type Case = { id: string; title: string; internal_ref: string; summary: string; status: string; is_synthetic: boolean; updated_at: string };

export default function CasesPage() {
  const [cases, setCases] = useState<Case[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [ref, setRef] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const [quick, setQuick] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [q, setQ] = useState("");
  const load = () => api<Case[]>("/cases").then(setCases).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await api("/cases", { method: "POST", body: JSON.stringify({ title, internal_ref: ref, summary }) }); setTitle(""); setRef(""); setSummary(""); setShowForm(false); await load(); }
    catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }
  async function quickDemo() {
    setQuick(true); setError(null);
    try { const r = await api("/synthetic/generate", { method: "POST", body: JSON.stringify({ scenario_type: "desert_mirage", difficulty: "messy", size: "small", seed: Math.floor(Math.random() * 100000) }) }); setCaseContext({ id: r.case.id, title: r.case.title }); window.location.href = `/cases/${r.case.id}`; }
    catch (err: any) { setError(err.message); setQuick(false); }
  }
  const shown = (cases || []).filter((c: any) => !q || `${c.title} ${c.internal_ref} ${c.summary}`.toLowerCase().includes(q.toLowerCase()));

  return (
    <Shell title="Cases" subtitle="One case per investigation. Pick a case to continue, or start a new one." pageKey="cases"
      actions={<><button className="btn" onClick={quickDemo} disabled={quick}>{quick ? "Generating Operation Desert Mirage…" : <><I.factory /> One-click demo: Operation Desert Mirage</>}</button><button className="btn-secondary" onClick={() => setShowForm((v) => !v)}><I.cases /> New case</button></>}>
      {showForm && (
        <form onSubmit={create} className="card mb-4 grid gap-3 md:grid-cols-[1fr_1fr_2fr_auto]" aria-label="Create case">
          <div><label className="label" htmlFor="t">Title *</label><input id="t" className="input" required value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Complaint 2026/118 – UPI fraud" /></div>
          <div><label className="label" htmlFor="r">Internal reference</label><input id="r" className="input" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="FIR / NCRP / file no." /></div>
          <div><label className="label" htmlFor="s">Allegation summary</label><input id="s" className="input" value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="One or two sentences" /></div>
          <div className="flex items-end"><button className="btn" disabled={busy}>Create</button></div>
          <p className="text-xs text-ink-muted md:col-span-4">Upload real files only when you are authorised to process them. For demonstrations use the synthetic factory.</p>
        </form>
      )}
      <State loading={cases === null && !error} error={error}>
        {cases && cases.length === 0 ? (
          <div className="card border-dashed py-10 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-light text-accent"><I.cases width={24} height={24} /></div>
            <h2 className="section-title">No cases yet</h2>
            <p className="mx-auto mt-1 max-w-md text-sm text-ink-muted">The fastest way to learn the tool is a synthetic case: fictional statements, a complaint and technical observations, all generated with hidden ground truth.</p>
            <div className="mt-4 flex justify-center gap-2"><button className="btn" onClick={quickDemo} disabled={quick}>{quick ? "Generating…" : <><I.factory /> Generate a demo case</>}</button><Link href="/factory" className="btn-secondary">Choose scenario &amp; difficulty</Link></div>
          </div>
        ) : (
          <>
            <div className="mb-3 flex items-center gap-2"><div className="relative max-w-sm flex-1"><I.search className="absolute left-2.5 top-2.5 text-ink-muted" width={16} height={16} /><input className="input pl-8" placeholder="Search cases…" aria-label="Search cases" value={q} onChange={(e) => setQ(e.target.value)} /></div><span className="text-xs text-ink-muted">{shown.length} of {cases?.length}</span></div>
            <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {shown.map((c: any) => (
                <li key={c.id}>
                  <Link href={`/cases/${c.id}`} className="card flex h-full flex-col gap-2 transition hover:-translate-y-0.5 hover:shadow-md">
                    <div className="flex items-start justify-between gap-2"><div className="font-semibold leading-snug">{c.title}</div>{c.is_synthetic ? <span className="badge shrink-0 bg-synthetic text-white">synthetic</span> : <span className="badge shrink-0 bg-panel">uploaded</span>}</div>
                    <p className="line-clamp-2 text-sm text-ink-muted">{c.summary || "No summary recorded."}</p>
                    <div className="mt-auto flex items-center justify-between pt-1 text-xs text-ink-muted"><span>{c.internal_ref ? `ref ${c.internal_ref}` : "no reference"} · {c.status}</span><span>{fmtTime(c.updated_at).slice(0, 16)}</span></div>
                    <span className="inline-flex items-center gap-1 text-sm font-medium text-accent">Open case <I.arrow width={14} height={14} /></span>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </State>
    </Shell>
  );
}

"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime } from "@/lib/api";

type Case = { id: string; title: string; internal_ref: string; status: string; is_synthetic: boolean; updated_at: string };

export default function CasesPage() {
  const [cases, setCases] = useState<Case[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [ref, setRef] = useState("");
  const [summary, setSummary] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api<Case[]>("/cases").then(setCases).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true);
    try { await api("/cases", { method: "POST", body: JSON.stringify({ title, internal_ref: ref, summary }) }); setTitle(""); setRef(""); setSummary(""); await load(); }
    catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <Shell title="Cases">
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <State loading={cases === null && !error} error={error} empty={cases && cases.length === 0 ? "No cases yet. Create one, or generate a synthetic investigation." : null}>
            <div className="card overflow-x-auto p-0">
              <table className="data">
                <thead><tr><th>Title</th><th>Ref</th><th>Data</th><th>Status</th><th>Updated</th></tr></thead>
                <tbody>
                  {cases?.map((c) => (
                    <tr key={c.id}>
                      <td><Link className="font-medium text-accent underline" href={`/cases/${c.id}`}>{c.title}</Link></td>
                      <td>{c.internal_ref || "—"}</td>
                      <td>{c.is_synthetic ? <span className="badge bg-synthetic text-white">synthetic</span> : <span className="badge bg-[#eef1f4]">uploaded</span>}</td>
                      <td>{c.status}</td>
                      <td className="whitespace-nowrap text-xs text-ink-muted">{fmtTime(c.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </State>
        </div>
        <div className="space-y-4">
          <div className="card">
            <h2 className="mb-2 font-semibold">Try a synthetic investigation</h2>
            <p className="mb-3 text-sm text-ink-muted">Generate a fresh, reproducible case with hidden ground truth. Files pass through the same upload pipeline as real evidence.</p>
            <Link href="/factory" className="btn">Open Synthetic Case Factory</Link>
          </div>
          <form onSubmit={create} className="card space-y-2">
            <h2 className="font-semibold">Create case for uploaded files</h2>
            <p className="text-xs text-ink-muted">Upload real files only when you are authorised to process them. Do not upload personal data for demonstration.</p>
            <div><label className="label" htmlFor="t">Title</label><input id="t" className="input" required value={title} onChange={(e) => setTitle(e.target.value)} /></div>
            <div><label className="label" htmlFor="r">Internal reference</label><input id="r" className="input" value={ref} onChange={(e) => setRef(e.target.value)} /></div>
            <div><label className="label" htmlFor="s">Allegation summary</label><textarea id="s" className="input" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} /></div>
            <button className="btn" disabled={busy}>Create case</button>
          </form>
        </div>
      </div>
    </Shell>
  );
}

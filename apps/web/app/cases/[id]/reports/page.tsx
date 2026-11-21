"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api } from "@/lib/api";

export default function ReportsPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [rep, setRep] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/report.json`)]).then(([cc, r]) => { setC(cc); setRep(r); }).catch((e) => setError(e.message)); }, [id]);
  async function download(path: string, name: string) {
    setBusy(name);
    try { const blob: Blob = await api(path, { raw: true }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); }
    catch (e: any) { setError(e.message); } finally { setBusy(null); }
  }
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Reports and export">
      <State loading={!rep && !error} error={error}>
        {rep && (
          <div className="space-y-4">
            <div className="card flex flex-wrap items-center gap-2">
              <button className="btn" disabled={!!busy} onClick={() => download(`/cases/${id}/report.pdf`, `ps05x_report_${id.slice(0, 8)}.pdf`)}>{busy === "pdf" ? "…" : "Download PDF report"}</button>
              <button className="btn-secondary" disabled={!!busy} onClick={() => download(`/cases/${id}/report.json`, `ps05x_report_${id.slice(0, 8)}.json`)}>JSON audit bundle</button>
              <button className="btn-secondary" disabled={!!busy} onClick={() => download(`/cases/${id}/report/transactions.csv`, `ps05x_transactions_${id.slice(0, 8)}.csv`)}>Transactions CSV</button>
              <span className="text-xs text-ink-muted">{rep.disclaimer}</span>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="card text-sm"><h2 className="font-semibold">Observed facts</h2><ul className="mt-1 text-xs"><li>{rep.sources.length} source files with SHA-256 hashes</li><li>{rep.transactions.count} transaction rows ({rep.transactions.with_amount} with amount; {rep.transactions.ambiguous_dates} ambiguous dates; {rep.transactions.duplicate_candidates} duplicate candidates)</li><li>{rep.infrastructure_observations.length} domain/IP/DNS/hosting observations with observation times</li></ul></div>
              <div className="card text-sm"><h2 className="font-semibold">Derived analysis</h2><ul className="mt-1 text-xs"><li>{rep.fund_paths.length} reconstructed fund paths</li><li>{rep.account_triage.filter((a: any) => a.reasons.length).length} accounts with rule-based triage signals (review required)</li><li>{rep.relationships.filter((r: any) => ["derived", "corroborated"].includes(r.evidence_level)).length} derived/corroborated relationships</li></ul></div>
              <div className="card text-sm"><h2 className="font-semibold">Hypotheses / candidates</h2><ul className="mt-1 text-xs"><li>{rep.relationships.filter((r: any) => r.evidence_level === "candidate").length} candidate relationships</li><li>{rep.counter_evidence.length} counter-evidence records</li><li>{rep.relationships.filter((r: any) => r.evidence_level === "stale").length} stale observations</li></ul></div>
              <div className="card text-sm"><h2 className="font-semibold">Unresolved</h2><ul className="mt-1 text-xs"><li>{rep.unresolved.relationships_requiring_review} relationships await review</li><li>{rep.unresolved.parser_warnings.length} parser warnings</li></ul></div>
            </div>
            <div className="card overflow-x-auto p-0"><table className="data"><thead><tr><th>Type</th><th>Source → Target</th><th>Level</th><th>Source locator</th><th>Limitations</th></tr></thead>
              <tbody>{rep.relationships.slice(0, 150).map((r: any) => <tr key={r.id}><td className="font-mono text-xs">{r.type}</td><td className="text-xs">{r.source} → {r.target}</td><td className="text-xs">{r.evidence_level}</td><td className="text-xs">{r.sources.map((s: any) => `${s.file}:${JSON.stringify(s.locator)}`).join("; ") || "—"}</td><td className="text-xs">{r.limitations.join("; ")}</td></tr>)}</tbody></table></div>
          </div>
        )}
      </State>
    </Shell>
  );
}

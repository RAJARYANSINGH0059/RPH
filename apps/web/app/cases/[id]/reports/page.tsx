"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { LevelBadge, Stat, State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

export default function ReportsPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [rep, setRep] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/report.json`)]).then(([cc, r]) => { setC(cc); setRep(r); }).catch((e) => setError(e.message)); }, [id]);
  async function download(path: string, name: string, key: string) {
    setBusy(key);
    try { const blob: Blob = await api(path, { raw: true }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); }
    catch (e: any) { setError(e.message); } finally { setBusy(null); }
  }
  const n = (f: (r: any) => boolean) => rep ? rep.relationships.filter(f).length : 0;
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Reports and export" subtitle="A source-backed report that separates observed facts, derived analysis, hypotheses and open questions." pageKey="reports" step="report"
      actions={rep && <><button className="btn" disabled={!!busy} onClick={() => download(`/cases/${id}/report.pdf`, `ps05x_report_${id.slice(0, 8)}.pdf`, "pdf")}><I.download /> {busy === "pdf" ? "Preparing…" : "PDF report"}</button><button className="btn-secondary" disabled={!!busy} onClick={() => download(`/cases/${id}/report.json`, `ps05x_report_${id.slice(0, 8)}.json`, "json")}>JSON</button><button className="btn-secondary" disabled={!!busy} onClick={() => download(`/cases/${id}/report/transactions.csv`, `ps05x_transactions_${id.slice(0, 8)}.csv`, "csv")}>CSV</button></>}>
      <State loading={!rep && !error} error={error}>
        {rep && (
          <div className="space-y-4">
            <div className="callout"><I.shield className="shrink-0 text-accent" /><div><strong>{rep.case.data_status}</strong> · {rep.case.live_connections}. {rep.disclaimer}</div></div>
            <div className="grid gap-3 md:grid-cols-4">
              <Stat label="Observed facts" value={rep.sources.length + rep.transactions.count} hint={`${rep.sources.length} files · ${rep.transactions.count} transaction rows · ${rep.infrastructure_observations.length} infra observations`} tone="info" />
              <Stat label="Derived analysis" value={rep.fund_paths.length + n((r) => ["derived", "corroborated"].includes(r.evidence_level))} hint={`${rep.fund_paths.length} fund paths · ${n((r) => ["derived", "corroborated"].includes(r.evidence_level))} derived/corroborated links`} tone="ok" />
              <Stat label="Hypotheses" value={n((r) => ["candidate", "stale", "contradicted"].includes(r.evidence_level))} hint={`${rep.counter_evidence.length} counter-evidence records`} tone="warn" />
              <Stat label="Unresolved" value={rep.unresolved.relationships_requiring_review} hint={`${rep.unresolved.parser_warnings.length} parser warnings`} tone={rep.unresolved.relationships_requiring_review ? "warn" : "ok"} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="card"><h2 className="font-semibold">What the PDF contains</h2><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm">{["Case metadata and synthetic/real-data status", "Sources with SHA-256 hashes", "Parsing methods and warnings", "Transaction trail with raw strings and locators", "Reconstructed fund paths", "Account triage signals (rules; review required)", "Domain / IP / DNS / hosting observations with observation times", "Relationship table with evidence level and source locator", "Counter-evidence and alternative explanations", "Unresolved gaps and manual review items", "Disclaimer"].map((x) => <li key={x}>{x}</li>)}</ol></div>
              <div className="card"><h2 className="font-semibold">Sources and hashes</h2><ul className="mt-2 space-y-1.5 text-xs">{rep.sources.map((s: any) => <li key={s.id} className="flex items-start gap-2"><I.file width={14} height={14} className="mt-0.5 shrink-0 text-ink-muted" /><div><div className="font-medium">{s.name} <span className="text-ink-muted">({s.kind})</span></div><div className="break-all font-mono text-[10px] text-ink-muted">{s.sha256}</div></div></li>)}</ul></div>
            </div>
            <div className="card p-0">
              <div className="px-4 py-3"><h2 className="font-semibold">Relationship table</h2><p className="text-xs text-ink-muted">Each row names its evidence level, its method and the exact source locator.</p></div>
              <div className="max-h-[480px] overflow-auto"><table className="data"><thead><tr><th>Type</th><th>Source → Target</th><th>Level</th><th>Source locator</th><th>Limitations</th></tr></thead>
                <tbody>{rep.relationships.slice(0, 200).map((r: any) => <tr key={r.id}><td className="text-xs">{r.type.replace(/_/g, " ").toLowerCase()}</td><td className="text-xs">{r.source} → {r.target}</td><td><LevelBadge level={r.evidence_level} /></td><td className="text-xs">{r.sources.map((s: any) => `${s.file}: ${Object.entries(s.locator).map(([k, v]) => `${k} ${v}`).join(", ")}`).join("; ") || "—"}</td><td className="text-xs text-ink-muted">{r.limitations.map((l: string) => l.replace(/_/g, " ")).join("; ")}</td></tr>)}</tbody></table></div>
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

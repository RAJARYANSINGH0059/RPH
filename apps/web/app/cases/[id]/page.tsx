"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { Stat, State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime } from "@/lib/api";

export default function CaseOverview() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/files`)]).then(([cc, ff]: [any, any]) => { setC(cc); setFiles(ff); }).catch((e) => setError(e.message)); }, [id]);
  const next = !c ? null : c.files_count === 0 ? { href: `/cases/${id}/upload`, label: "Upload the first evidence file", why: "Nothing has been ingested yet." }
    : c.transactions_count === 0 ? { href: `/cases/${id}/upload`, label: "Add a bank statement (CSV/XLSX)", why: "No transactions were parsed, so there is no money trail yet." }
    : c.findings_awaiting_review > 0 ? { href: `/cases/${id}/graph`, label: `Review ${c.findings_awaiting_review} candidate relationship${c.findings_awaiting_review > 1 ? "s" : ""}`, why: "Candidate and stale links need a human decision before the report." }
    : { href: `/cases/${id}/reports`, label: "Export the report", why: "Everything is reviewed." };
  const step = !c ? "upload" : c.files_count === 0 ? "upload" : c.transactions_count === 0 ? "parse" : c.findings_awaiting_review > 0 ? "review" : "report";
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title={c?.title || "Case workspace"} subtitle={c ? `${c.internal_ref ? `Ref ${c.internal_ref} · ` : ""}${c.status} · ${c.is_synthetic ? "synthetic data" : "uploaded data"} · last activity ${fmtTime(c.last_activity)} · suggested step: ${step}` : undefined} pageKey="overview">
      <State loading={!c && !error} error={error}>
        {c && (
          <div className="space-y-4">
            <div className="callout items-center justify-between">
              <div className="flex items-center gap-3"><I.arrow className="shrink-0 text-accent" /><div><div className="font-semibold">Suggested next step: {next!.label}</div><div className="text-xs text-ink-muted">{next!.why}</div></div></div>
              <Link href={next!.href} className="btn">Go</Link>
            </div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Stat label="Evidence files" value={c.files_count} hint="hashed and parsed" href={`/cases/${id}/upload`} />
              <Stat label="Transactions" value={c.transactions_count} hint="rows with raw text kept" href={`/cases/${id}/transactions`} />
              <Stat label="Infrastructure indicators" value={c.indicators_count} hint="domains, URLs, IPs, hosts" href={`/cases/${id}/graph`} />
              <Stat label="Relationships" value={c.relationships_count} hint="each with an evidence level" href={`/cases/${id}/graph`} />
              <Stat label="Parser warnings" value={c.unresolved_warnings} hint="information to check, not errors" href={`/cases/${id}/upload`} tone={c.unresolved_warnings ? "warn" : "ok"} />
              <Stat label="Awaiting review" value={c.findings_awaiting_review} hint="candidate or stale links" href={`/cases/${id}/graph`} tone={c.findings_awaiting_review ? "warn" : "ok"} />
              <Stat label="Entities" value={c.entities_count} hint="accounts, VPAs, domains…" />
              <Stat label="Export" value={<span className="text-base">PDF · JSON · CSV</span>} hint="source-backed report" href={`/cases/${id}/reports`} />
            </div>
            <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
              <div className="card overflow-x-auto p-0">
                <div className="flex items-center justify-between px-4 py-3"><h2 className="section-title">Evidence files</h2><Link href={`/cases/${id}/upload`} className="btn-secondary"><I.upload /> Upload more</Link></div>
                <table className="data"><thead><tr><th>File</th><th>Kind</th><th>Size</th><th>Status</th><th>Uploaded</th></tr></thead>
                  <tbody>{files.length === 0 && <tr><td colSpan={5} className="py-6 text-center text-ink-muted">No files yet.</td></tr>}
                    {files.map((f: any) => <tr key={f.id}><td><div className="font-medium">{f.original_name}</div><div className="mono text-[11px] text-ink-muted">sha256 {f.sha256.slice(0, 20)}…</div></td><td>{f.detected_kind}</td><td>{(f.size_bytes / 1024).toFixed(1)} KB</td><td><span className={`badge ${f.status === "parsed" ? "bg-ok-soft text-ok" : f.status === "failed" ? "bg-danger-soft text-danger" : "bg-saffron-soft text-warn"}`}>{f.status.replace("_", " ")}</span></td><td className="text-xs">{fmtTime(f.uploaded_at)}</td></tr>)}
                  </tbody></table>
              </div>
              <div className="space-y-3">
                <div className="card text-sm"><div className="label">Allegation summary</div><p>{c.summary || "No summary recorded."}</p></div>
                <div className="card text-sm">
                  <div className="label">Where things are</div>
                  <ul className="space-y-1.5">
                    {[["Money trail", `/cases/${id}/transactions`, <I.money key="m" width={16} height={16} />], ["Relationships & evidence", `/cases/${id}/graph`, <I.graph key="g" width={16} height={16} />], ["Chronology", `/cases/${id}/timeline`, <I.timeline key="t" width={16} height={16} />], ["Report & export", `/cases/${id}/reports`, <I.report key="r" width={16} height={16} />], ["Digital twin", `/cases/${id}/twin`, <I.radar key="tw" width={16} height={16} />], ["Payment instruction bridge", `/cases/${id}/payment-bridge`, <I.qr key="q" width={16} height={16} />], ["Bounded fund provenance", `/cases/${id}/bounded-flow`, <I.scale key="b" width={16} height={16} />], ["CounterProof", `/cases/${id}/counterproof`, <I.shield key="cp" width={16} height={16} />], ["Next-best evidence", `/cases/${id}/ivoi`, <I.sparkle key="iv" width={16} height={16} />], ["Related authorised cases", `/cases/${id}/crosscase`, <I.link key="x" width={16} height={16} />], ["Victim claims & restitution readiness", `/cases/${id}/claims`, <I.shield key="c" width={16} height={16} />], ["Cooperation pack", `/cases/${id}/cooperation`, <I.file key="p" width={16} height={16} />]].map(([l, h, ic]) => <li key={l as string}><Link className="flex items-center gap-2 text-accent hover:underline" href={h as string}>{ic}{l as string}</Link></li>)}
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

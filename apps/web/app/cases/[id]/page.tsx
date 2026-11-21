"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime } from "@/lib/api";

export default function CaseOverview() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    Promise.all([api(`/cases/${id}`), api(`/cases/${id}/files`)]).then(([cc, ff]) => { setC(cc); setFiles(ff); }).catch((e) => setError(e.message));
  }, [id]);
  const stat = (label: string, v: any, href?: string) => (
    <div className="card"><div className="text-xs uppercase tracking-wide text-ink-muted">{label}</div><div className="text-2xl font-semibold">{v}</div>{href && <Link className="text-xs text-accent underline" href={href}>Open</Link>}</div>
  );
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title={c?.title || "Case"}>
      <State loading={!c && !error} error={error}>
        {c && (
          <div className="space-y-4">
            <div className="card text-sm"><span className="badge bg-[#eef1f4]">{c.status}</span> {c.internal_ref && <span className="ml-2 text-ink-muted">ref {c.internal_ref}</span>}<p className="mt-2">{c.summary || "No summary recorded."}</p><p className="mt-1 text-xs text-ink-muted">Last activity {fmtTime(c.last_activity)}</p></div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {stat("Evidence files", c.files_count, `/cases/${id}/upload`)}
              {stat("Transactions parsed", c.transactions_count, `/cases/${id}/transactions`)}
              {stat("Infrastructure indicators", c.indicators_count, `/cases/${id}/graph`)}
              {stat("Relationships", c.relationships_count, `/cases/${id}/graph`)}
              {stat("Unresolved parser warnings", c.unresolved_warnings, `/cases/${id}/upload`)}
              {stat("Findings awaiting review", c.findings_awaiting_review, `/cases/${id}/graph`)}
              {stat("Entities", c.entities_count)}
              {stat("Export", "PDF / JSON / CSV", `/cases/${id}/reports`)}
            </div>
            <div className="card overflow-x-auto p-0">
              <table className="data"><thead><tr><th>File</th><th>Kind</th><th>Size</th><th>SHA-256</th><th>Status</th><th>Uploaded</th></tr></thead>
                <tbody>{files.length === 0 && <tr><td colSpan={6} className="text-ink-muted">No files yet. <Link className="underline" href={`/cases/${id}/upload`}>Upload evidence</Link>.</td></tr>}
                  {files.map((f) => <tr key={f.id}><td>{f.original_name}</td><td>{f.detected_kind}</td><td>{(f.size_bytes / 1024).toFixed(1)} KB</td><td className="font-mono text-xs">{f.sha256.slice(0, 20)}…</td><td>{f.status}</td><td className="text-xs">{fmtTime(f.uploaded_at)}</td></tr>)}
                </tbody></table>
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

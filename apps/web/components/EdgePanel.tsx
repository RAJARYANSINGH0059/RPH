"use client";

import { useEffect, useState } from "react";
import { LevelBadge } from "@/components/Shell";
import { api, fmtTime, getUser } from "@/lib/api";

export default function EdgePanel({ caseId, edgeId, onClose, onReviewed }: { caseId: string; edgeId: string | null; onClose: () => void; onReviewed?: () => void }) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { setD(null); setMsg(null); if (edgeId) api(`/cases/${caseId}/edges/${edgeId}`).then(setD).catch((e) => setError(e.message)); }, [caseId, edgeId]);
  if (!edgeId) return null;
  async function review(decision: string) {
    setMsg(null);
    try { await api(`/cases/${caseId}/edges/${edgeId}/review`, { method: "POST", body: JSON.stringify({ decision, reason }) }); setMsg(`Recorded: ${decision}`); setD(await api(`/cases/${caseId}/edges/${edgeId}`)); onReviewed?.(); }
    catch (e: any) { setMsg(e.message); }
  }
  const role = getUser()?.role;
  return (
    <aside aria-label="Relationship evidence" className="card max-h-[80vh] overflow-y-auto text-sm">
      <div className="flex items-start justify-between gap-2"><h2 className="font-semibold">Relationship evidence</h2><button className="btn-secondary" onClick={onClose} aria-label="Close panel">Close</button></div>
      {error && <div role="alert" className="text-[#8a1c1c]">{error}</div>}
      {!d && !error && <div className="text-ink-muted">Loading…</div>}
      {d && (
        <div className="space-y-3">
          <div><div className="font-mono text-xs text-ink-muted">{d.edge.type}</div><div><strong>{d.source_entity.label}</strong> <span className="text-ink-muted">({d.source_entity.type})</span> → <strong>{d.target_entity.label}</strong> <span className="text-ink-muted">({d.target_entity.type})</span></div>
            <div className="mt-1 flex flex-wrap gap-1"><LevelBadge level={d.edge.evidence_level} /><span className="badge bg-[#eef1f4]">review: {d.edge.review_status}</span>{d.edge.heuristic_score !== null && <span className="badge bg-[#eef1f4]">heuristic score {d.edge.heuristic_score} (not a probability)</span>}</div></div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-ink-muted">Valid time</dt><dd>{fmtTime(d.edge.valid_from)} → {d.edge.valid_to ? fmtTime(d.edge.valid_to) : "open"}</dd>
            <dt className="text-ink-muted">Observed</dt><dd>{fmtTime(d.edge.observed_at)}</dd>
            <dt className="text-ink-muted">Method</dt><dd>{d.method.name}@{d.method.version}</dd>
            <dt className="text-ink-muted">Attributes</dt><dd className="break-all font-mono">{JSON.stringify(d.edge.attributes)}</dd>
          </dl>
          {d.method.limitations.length > 0 && <div><div className="label">Limitations</div><ul className="list-disc pl-4 text-xs">{d.method.limitations.map((l: string) => <li key={l}>{l.replace(/_/g, " ")}</li>)}</ul></div>}
          <div><div className="label">Supporting evidence ({d.supporting_evidence.length})</div>
            {d.supporting_evidence.length === 0 && <div className="text-xs text-ink-muted">None attached — this is a candidate requiring an independent identifier bridge.</div>}
            <ul className="space-y-1">{d.supporting_evidence.map((e: any) => <li key={e.id} className="rounded bg-[#f6f8fa] p-2 text-xs"><div><span className="badge bg-[#eef1f4]">{e.source_type}</span> <span className="font-mono">{JSON.stringify(e.source_locator)}</span> · {e.extraction_method} · {e.parser_name}@{e.parser_version}</div><div className="mt-1 break-all font-mono text-[11px] text-ink-muted">{(e.raw_value || "").slice(0, 300)}</div><div className="text-ink-muted">event {fmtTime(e.event_time_start)} [{e.time_precision}] · observed {fmtTime(e.observed_at)} · ingested {fmtTime(e.ingested_at)}{e.quality_flags.length > 0 && ` · flags: ${e.quality_flags.join(", ")}`}</div></li>)}</ul></div>
          <div><div className="label">Counter-evidence and alternative explanations ({d.counter_evidence.length})</div>
            {d.counter_evidence.length === 0 ? <div className="text-xs text-ink-muted">None recorded.</div> : <ul className="space-y-1">{d.counter_evidence.map((c: any) => <li key={c.id} className="rounded border border-[#f1c5c5] bg-[#fff5f5] p-2 text-xs"><span className="badge bg-[#fde8e8] text-[#8a1c1c]">{c.severity}</span> <strong>{c.kind.replace(/_/g, " ")}</strong>: {c.description}</li>)}</ul>}</div>
          <div><div className="label">Analyst review</div>
            <textarea className="input" rows={2} placeholder="Reason (recorded in audit log)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => review("supported")} title={["candidate", "stale", "contradicted"].includes(d.edge.evidence_level) && role === "analyst" ? "Supervisor required to promote a candidate" : ""}>Supported</button>
              <button className="btn-secondary" onClick={() => review("rejected")}>Rejected</button>
              <button className="btn-secondary" onClick={() => review("needs_more_evidence")}>Needs more evidence</button>
            </div>
            {msg && <div className="mt-1 text-xs">{msg}</div>}
            {d.reviews.length > 0 && <ul className="mt-2 text-xs text-ink-muted">{d.reviews.map((r: any) => <li key={r.id}>{fmtTime(r.created_at)}: {r.decision} — {r.reason}</li>)}</ul>}
          </div>
        </div>
      )}
    </aside>
  );
}

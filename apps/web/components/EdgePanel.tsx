"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LevelBadge } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, getUser } from "@/lib/api";
import { EVIDENCE_LEVEL_HELP } from "@/lib/guide";

const PLAIN: Record<string, string> = {
  TRANSFERRED_TO: "Money moved from the first account to the second, as recorded in a statement row.",
  SAME_ACCOUNT_IDENTIFIER: "These two identifiers refer to the same account: a transfer with the same reference and amount appears in both statements.",
  SAME_IDENTIFIER: "The same identifier appears in a document and in a bank statement.",
  SIMILAR_NAME: "The names look alike, but the identifiers differ. The system did not merge them.",
  MENTIONS: "The document contains this indicator. Mention is not involvement.",
  RESOLVES_TO: "At the observation time, the domain pointed to this IP address.",
  HOSTED_ON: "At the observation time, the IP was on this provider/ASN.",
  SHARED_INFRASTRUCTURE: "Both domains were observed on the same IP. Unrelated sites commonly share hosting; this is a pivot, not proof of common control.",
  REGISTRATION_OBSERVED: "Current registration data was observed for this domain.",
  BELONGS_TO_DOMAIN: "The URL is part of this domain.",
};

export default function EdgePanel({ caseId, edgeId, onClose, onReviewed }: { caseId: string; edgeId: string | null; onClose: () => void; onReviewed?: () => void }) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  useEffect(() => { setD(null); setMsg(null); setError(null); if (edgeId) api(`/cases/${caseId}/edges/${edgeId}`).then(setD).catch((e) => setError(e.message)); }, [caseId, edgeId]);
  if (!edgeId) return null;
  async function review(decision: string) {
    setMsg(null);
    try { await api(`/cases/${caseId}/edges/${edgeId}/review`, { method: "POST", body: JSON.stringify({ decision, reason }) }); setMsg(`Recorded: ${decision.replace(/_/g, " ")}.`); setD(await api(`/cases/${caseId}/edges/${edgeId}`)); onReviewed?.(); }
    catch (e: any) { setMsg(e.message); }
  }
  const role = getUser()?.role;
  const needsSupervisor = d && ["candidate", "stale", "contradicted"].includes(d.edge.evidence_level) && role === "analyst";
  return (
    <aside aria-label="Relationship evidence" className="card max-h-[85vh] overflow-y-auto text-sm">
      <div className="flex items-start justify-between gap-2"><div><div className="text-[11px] font-semibold uppercase tracking-wide text-accent">Relationship evidence</div>{d && <h2 className="font-semibold">{d.edge.type.replace(/_/g, " ").toLowerCase()}</h2>}</div><button className="btn-icon" onClick={onClose} aria-label="Close panel"><I.close /></button></div>
      {error && <div role="alert" className="mt-2 text-danger">{error}</div>}
      {d && <Link href={`/cases/${caseId}/counterproof?edge=${edgeId}`} className="mt-2 inline-flex items-center gap-1 text-xs text-accent-deep underline">Open the Attribution Challenge Report (alternatives, counter-evidence, dissent)</Link>}
      {!d && !error && <div className="mt-2 text-ink-muted">Loading…</div>}
      {d && (
        <div className="mt-2 space-y-3">
          <div className="rounded-lg bg-canvas p-2.5">
            <div className="flex flex-wrap items-center gap-1.5"><strong>{d.source_entity.label}</strong><span className="text-xs text-ink-muted">({d.source_entity.type.replace("_", " ")})</span><I.arrow width={14} height={14} className="text-ink-muted" /><strong>{d.target_entity.label}</strong><span className="text-xs text-ink-muted">({d.target_entity.type.replace("_", " ")})</span></div>
            <p className="mt-1 text-xs text-ink-muted">{PLAIN[d.edge.type] || ""}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5"><LevelBadge level={d.edge.evidence_level} /><span className="text-xs text-ink-muted">{EVIDENCE_LEVEL_HELP[d.edge.evidence_level]}</span></div>
          <div className="flex flex-wrap gap-1.5"><span className="badge bg-panel">review: {d.edge.review_status.replace(/_/g, " ")}</span>{d.edge.heuristic_score !== null && <span className="badge bg-panel" title="Heuristic ranking score 0–100; not a calibrated probability">rank score {d.edge.heuristic_score}</span>}</div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <dt className="text-ink-muted">Valid</dt><dd>{fmtTime(d.edge.valid_from)} → {d.edge.valid_to ? fmtTime(d.edge.valid_to) : "open"}</dd>
            <dt className="text-ink-muted">Observed</dt><dd>{fmtTime(d.edge.observed_at)}</dd>
            <dt className="text-ink-muted">Method</dt><dd>{d.method.name.replace(/_/g, " ")} v{d.method.version}</dd>
            {d.edge.attributes.amount_minor !== undefined && <><dt className="text-ink-muted">Amount</dt><dd>₹{(d.edge.attributes.amount_minor / 100).toLocaleString("en-IN", { minimumFractionDigits: 2 })} {d.edge.attributes.reference ? `· ref ${d.edge.attributes.reference}` : ""} {d.edge.attributes.channel ? `· ${d.edge.attributes.channel}` : ""}</dd></>}
            {d.edge.attributes.shared_ip && <><dt className="text-ink-muted">Shared IP</dt><dd className="mono">{d.edge.attributes.shared_ip}{d.edge.attributes.multi_tenant ? " (multi-tenant / CDN)" : ""}</dd></>}
            {d.edge.attributes.similarity && <><dt className="text-ink-muted">Similarity</dt><dd>{d.edge.attributes.similarity} ({d.edge.attributes.name_a} vs {d.edge.attributes.name_b})</dd></>}
          </dl>
          {d.method.limitations.length > 0 && <div><div className="label">Limitations</div><ul className="list-disc space-y-0.5 pl-4 text-xs">{d.method.limitations.map((l: string) => <li key={l}>{l.replace(/_/g, " ")}</li>)}</ul></div>}
          <div>
            <div className="label">Supporting evidence ({d.supporting_evidence.length})</div>
            {d.supporting_evidence.length === 0 && <div className="text-xs text-ink-muted">None attached. This is a hypothesis; an independent identifier bridge is needed.</div>}
            <ul className="space-y-1.5">{d.supporting_evidence.slice(0, 8).map((e: any) => (
              <li key={e.id} className="rounded-lg border border-line p-2 text-xs">
                <div className="flex flex-wrap items-center gap-1.5"><span className="badge bg-panel">{e.source_type.replace("_", " ")}</span><span className="mono text-[11px]">{Object.entries(e.source_locator).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join("–") : v}`).join(" · ")}</span></div>
                <div className="mt-1 text-ink-muted">{e.extraction_method.replace(/_/g, " ")} · {e.parser_name}@{e.parser_version}</div>
                <div className="text-ink-muted">event {fmtTime(e.event_time_start)} <span className="badge bg-saffron-soft text-warn">{e.time_precision}</span> · observed {fmtTime(e.observed_at)}</div>
                {e.quality_flags.length > 0 && <div className="warn">flags: {e.quality_flags.map((f: string) => f.replace(/_/g, " ")).join(", ")}</div>}
                {showRaw && <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all rounded bg-canvas p-1.5 mono text-[10px]">{e.raw_value}</pre>}
              </li>
            ))}</ul>
            {d.supporting_evidence.length > 0 && <button className="mt-1 text-xs text-accent underline" onClick={() => setShowRaw((v) => !v)}>{showRaw ? "Hide raw source text" : "Show raw source text"}</button>}
          </div>
          <div>
            <div className="label">Counter-evidence and alternative explanations ({d.counter_evidence.length})</div>
            {d.counter_evidence.length === 0 ? <div className="text-xs text-ink-muted">None recorded.</div> : <ul className="space-y-1.5">{d.counter_evidence.map((c: any) => <li key={c.id} className="rounded-lg border border-danger/30 bg-danger-soft p-2 text-xs"><div className="flex items-center gap-1.5"><I.alert width={14} height={14} className="text-danger" /><strong>{c.kind.replace(/_/g, " ")}</strong><span className="badge bg-danger-soft text-danger">{c.severity}</span></div><div className="mt-1">{c.description}</div></li>)}</ul>}
          </div>
          <div className="rounded-lg border border-line p-2.5">
            <div className="label">Your decision</div>
            <textarea className="input" rows={2} placeholder="Reason (goes into the audit log)" value={reason} onChange={(e) => setReason(e.target.value)} />
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn-secondary" onClick={() => review("supported")} disabled={!!needsSupervisor} title={needsSupervisor ? "A supervisor must promote a candidate/stale link" : ""}><I.check /> Supported</button>
              <button className="btn-secondary" onClick={() => review("rejected")}><I.close /> Rejected</button>
              <button className="btn-secondary" onClick={() => review("needs_more_evidence")}><I.help /> Needs more evidence</button>
            </div>
            {needsSupervisor && <p className="mt-1 text-[11px] text-ink-muted">Analysts can reject or request evidence; promoting a candidate requires a supervisor.</p>}
            {msg && <div className="mt-1 text-xs">{msg}</div>}
            {d.reviews.length > 0 && <ul className="mt-2 space-y-0.5 text-xs text-ink-muted">{d.reviews.map((r: any) => <li key={r.id}>{fmtTime(r.created_at)}: <strong>{r.decision.replace(/_/g, " ")}</strong>{r.reason ? ` — ${r.reason}` : ""}</li>)}</ul>}
          </div>
        </div>
      )}
    </aside>
  );
}

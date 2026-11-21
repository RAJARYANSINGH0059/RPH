"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Locator, Section, State, Toast, useApi, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api, getUser, isReviewer } from "@/lib/api";

export default function CounterProofPage() {
  return <CasePage title="CounterProof — Evidence Adversary" subtitle="Every material relationship is tested against alternative explanations. Supporting, contradicting and missing evidence, temporal compatibility and source reliability are shown separately. A candidate never silently becomes a fact." pageKey="counterproof" wide>{(c, id) => <Suspense fallback={null}><Body id={id} /></Suspense>}</CasePage>;
}

function Body({ id }: { id: string }) {
  const params = useSearchParams();
  const { data, error, reload } = useApi<any>(`/cases/${id}/adversary?limit=120`);
  const [edge, setEdge] = useState<string | null>(params.get("edge"));
  const [filter, setFilter] = useState<string>("");
  const [reason, setReason] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const detail = useApi<any>(edge ? `/cases/${id}/adversary/${edge}` : null, [edge]);
  useEffect(() => { const e = params.get("edge"); if (e) setEdge(e); }, [params]);
  const reviewer = isReviewer(getUser());
  async function act(action: string) {
    if (!edge) return;
    setMsg(null);
    try { await api(`/cases/${id}/adversary/${edge}/action`, { method: "POST", body: JSON.stringify({ action, reason }) }); setMsg(`Recorded: ${action.replace(/_/g, " ")}.`); setReason(""); detail.reload(); reload(); }
    catch (e: any) { setMsg(e.message); }
  }
  const rows = (data?.rows || []).filter((r: any) => !filter || r.state === filter);
  const rep = detail.data?.report;
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-xs"><span className="label mb-0">State</span><button className={`chip ${!filter ? "chip-on" : ""}`} onClick={() => setFilter("")}>all ({data.rows.length})</button>{Object.entries(data.by_state).map(([k, n]: [any, any]) => <button key={k} className={`chip ${filter === k ? "chip-on" : ""}`} onClick={() => setFilter(k)}><Chip v={k} /> {String(n)}</button>)}</div>
          <div className="wb-grid">
            <Section title="Relationships under challenge" hint="Weakest evidence first. Click a row to open its Attribution Challenge Report.">
              <div className="max-h-[70vh] overflow-auto">
                <table className="data text-xs"><thead><tr><th>Type</th><th>From → To</th><th>State</th><th>Strength</th><th>Counter</th><th>Alts</th><th>Review</th></tr></thead>
                  <tbody>{rows.map((r: any) => <tr key={r.relationship_id} onClick={() => setEdge(r.relationship_id)} className={`cursor-pointer ${edge === r.relationship_id ? "bg-accent-soft/40" : ""}`} aria-selected={edge === r.relationship_id}><td className="mono">{r.type}</td><td className="max-w-[260px] truncate">{r.from?.label} → {r.to?.label}</td><td><Chip v={r.state} /></td><td>{r.strength}</td><td className="num">{r.counter_evidence}</td><td className="num">{r.alternatives}</td><td>{r.review_status.replace(/_/g, " ")}</td></tr>)}{rows.length === 0 && <tr><td colSpan={7} className="py-6 text-center muted">No relationships in this state.</td></tr>}</tbody></table>
              </div>
            </Section>
            <div className="space-y-3">
              {edge ? (
                <State loading={detail.loading} error={detail.error}>
                  {rep && (
                    <Section title="Attribution Challenge Report" actions={<button className="btn-icon" onClick={() => setEdge(null)} aria-label="Close"><I.close /></button>}>
                      <div className="flex items-center gap-2"><Chip v={detail.data.state} /><span className="mono text-sm font-semibold">{rep.alleged_relationship.type}</span></div>
                      <p className="mt-1 text-sm">{rep.alleged_relationship.from?.label} <span className="muted">({rep.alleged_relationship.from?.type})</span> → {rep.alleged_relationship.to?.label} <span className="muted">({rep.alleged_relationship.to?.type})</span></p>
                      <p className="mt-2 rounded-lg bg-panel p-2 text-sm">{rep.current_conclusion.text}</p>
                      <KV className="mt-3" rows={[["Evidence level", <Chip key="l" v={rep.alleged_relationship.evidence_level} />], ["Method", <span key="m" className="mono text-xs">{rep.alleged_relationship.method}</span>], ["Strength", `${rep.strength.label} — ${rep.strength.kind}`], ["Why", rep.strength.why], ["What records establish", rep.what_records_establish], ["Temporal compatibility", <span key="t">{rep.temporal_compatibility.compatible_with_events === null ? "cannot be assessed" : rep.temporal_compatibility.compatible_with_events ? "✓ compatible" : "✗ incompatible"} <span className="muted">— {rep.temporal_compatibility.note}</span></span>]]} />
                      <div className="mt-3"><div className="label">Supporting records ({rep.supporting_records.length})</div><ul className="space-y-1 text-xs">{rep.supporting_records.slice(0, 6).map((e: any) => <li key={e.evidence_id} className="flex flex-wrap items-center gap-2"><Chip v={e.source_type === "bank_statement" ? "observed" : e.source_type === "complaint" ? "reported" : "extracted"} /><Locator caseId={id} file={e.file} sha256={e.sha256} locator={e.locator} evidenceId={e.evidence_id} /><span className="muted">{e.reliability?.[1]}</span>{e.time_precision === "ambiguous" && <span className="badge lvl-candidate">ambiguous time</span>}</li>)}</ul></div>
                      <div className="mt-3"><div className="label">Counter-evidence ({rep.counter_evidence.length})</div><ul className="space-y-1 text-xs">{rep.counter_evidence.map((c: any, i: number) => <li key={i} className="flex items-start gap-2"><span className={`badge ${c.severity === "high" ? "lvl-contradicted" : "lvl-candidate"}`}>{c.severity}</span><span><span className="mono">{c.kind}</span> — {c.description}</span></li>)}{rep.counter_evidence.length === 0 && <li className="muted">None on file.</li>}</ul></div>
                      <div className="mt-3"><div className="label">Alternative hypotheses</div><ul className="space-y-2 text-xs">{rep.alternative_hypotheses.map((a: any) => <li key={a.hypothesis} className="inset p-2"><div className="font-semibold">{a.hypothesis}</div><div className="muted">{a.why_relevant}</div><div><span className="font-medium">Would distinguish:</span> {a.would_distinguish}</div></li>)}</ul></div>
                      {rep.competing_hypotheses_on_file.length > 0 && <div className="mt-3"><div className="label">Competing hypotheses on file</div><ul className="text-xs">{rep.competing_hypotheses_on_file.map((h: any) => <li key={h.id}>{h.title} · v{h.version} · {h.status}</li>)}</ul></div>}
                      {rep.review_history.length > 0 && <div className="mt-3"><div className="label">Review history</div><ul className="text-xs">{rep.review_history.map((r: any, i: number) => <li key={i}><Chip v={r.decision} /> {r.reason} <span className="muted">· <When v={r.at} /></span></li>)}</ul></div>}
                      <div className="mt-4 border-t border-line pt-3">
                        <div className="label">Investigator action (audited, reversible by a new event)</div>
                        <input className="input mb-2" placeholder="Reason (min 5 chars)" value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" />
                        <div className="flex flex-wrap gap-1.5">
                          <button className="btn-secondary !py-1" disabled={reason.length < 5 || (!reviewer && ["candidate", "stale", "contradicted"].includes(rep.alleged_relationship.evidence_level))} title={!reviewer ? "Accepting a candidate/stale/contradicted relationship needs a supervisor" : undefined} onClick={() => act("accept")}>Accept</button>
                          <button className="btn-secondary !py-1" disabled={reason.length < 5} onClick={() => act("reject")}>Reject</button>
                          <button className="btn-secondary !py-1" disabled={reason.length < 5} onClick={() => act("retain_as_candidate")}>Retain as candidate</button>
                          <button className="btn-secondary !py-1" disabled={reason.length < 5} onClick={() => act("add_competing_hypothesis")}>Add competing hypothesis</button>
                          <button className="btn-secondary !py-1" disabled={reason.length < 5} onClick={() => act("record_dissent")}>Record dissent</button>
                        </div>
                        <Toast msg={msg} onClose={() => setMsg(null)} />
                      </div>
                      <Limitations items={detail.data.limitations} />
                    </Section>
                  )}
                </State>
              ) : <div className="card text-sm muted">Select a relationship to see its challenge report.</div>}
              <MotionScene scene="counterproof" height={120} />
            </div>
          </div>
        </div>
      )}
    </State>
  );
}

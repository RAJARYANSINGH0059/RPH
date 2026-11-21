"use client";

import { FormEvent, useState } from "react";
import CasePage from "@/components/CasePage";
import { Chip, KV, Limitations, Section, State, Toast, useApi, When } from "@/components/ui";
import { api, getUser, isReviewer } from "@/lib/api";

export default function RolesPage() {
  return <CasePage title="Account Involvement vs Human Attribution" subtitle="Facts about an account are kept apart from propositions about the human associated with it. Nine propositions, a status, open questions, and a dated account-control timeline in which holder, possessor, controller, initiator, recruiter, cash-out actor and beneficiary may all be different people." pageKey="roles" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const paths = useApi<any>(`/cases/${id}/paths`);
  const accounts: string[] = Array.from(new Set((paths.data?.paths || []).flatMap((p: any) => p.accounts.slice(1)))) as string[];
  const [acct, setAcct] = useState<string>("");
  const current = acct || accounts[0] || "";
  const review = useApi<any>(current ? `/cases/${id}/roles/${encodeURIComponent(current)}` : null, [current]);
  const timeline = useApi<any>(current ? `/cases/${id}/roles/${encodeURIComponent(current)}/control-timeline` : null, [current]);
  const [msg, setMsg] = useState<string | null>(null);
  const [claim, setClaim] = useState({ role_dimension: "registered_holder", actor_label: "", claim_state: "alleged", description: "", source_evidence_item_id: "", counter_evidence: "" });
  const [decision, setDecision] = useState({ status: "HUMAN_REVIEWED", rationale: "" });
  const reviewer = isReviewer(getUser());
  async function setProp(key: string, status: string) {
    setMsg(null);
    try { await api(`/cases/${id}/roles/${encodeURIComponent(current)}`, { method: "POST", body: JSON.stringify({ propositions: { [key]: { status } }, note: "set from UI" }) }); review.reload(); }
    catch (e: any) { setMsg(e.message); }
  }
  async function addClaim(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await api(`/cases/${id}/roles/${encodeURIComponent(current)}/control-timeline`, { method: "POST", body: JSON.stringify({ ...claim, source_evidence_item_id: claim.source_evidence_item_id || null }) }); setMsg("Role claim recorded."); setClaim({ ...claim, actor_label: "", description: "" }); timeline.reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  async function decide(e: FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await api(`/cases/${id}/roles/${encodeURIComponent(current)}/decision`, { method: "POST", body: JSON.stringify(decision) }); setMsg("Reviewer decision recorded."); review.reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  const r = review.data, t = timeline.data;
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-3 text-sm">
        <label>Account <select className="input !w-auto" value={current} onChange={(e) => setAcct(e.target.value)} aria-label="Account">{accounts.map((a: any) => <option key={a} value={a}>{a}</option>)}</select></label>
        {r && <span className="ml-auto flex items-center gap-2">Status <Chip v={r.status} /></span>}
      </div>
      <Toast msg={msg} onClose={() => setMsg(null)} />
      <State loading={review.loading && !!current} error={review.error} empty={!current ? "No downstream account in this case yet." : undefined}>
        {r && (
          <div className="space-y-4">
            <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr]">
              <Section title="Account facts (record level)" hint={r.facts.note}>
                <KV rows={[["Account", <span key="a" className="mono">{r.facts.account_ref}</span>], ["Aliases", r.facts.aliases.join(", ") || "none"], ["Own statement supplied", r.facts.own_statement_supplied ? "yes" : "no"], ["Credits / debits observed", `${r.facts.credits_observed} / ${r.facts.debits_observed}`], ["Names shown by counterparties", r.facts.names_shown_by_counterparties.join(", ") || "—"]]} />
              </Section>
              <Section title="Propositions about the human" hint="Not mutually exclusive; none is a legal finding. 'Supported' needs evidence; account presence alone is never evidence of knowledge or intent.">
                <ul className="space-y-1.5 text-sm">{r.propositions.map((p: any) => <li key={p.key} className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-1.5"><span><span className="mono text-xs muted">{p.key}</span> {p.label}</span><span className="flex items-center gap-1"><Chip v={p.status === "supported" ? "supported" : p.status === "contradicted" ? "contradicted" : p.status === "conflicting" ? "contested" : p.status === "insufficient" ? "unresolved" : "insufficient"} title={p.status} />{!p.auto && <select className="input !w-auto !py-0.5 text-xs" value={p.status} onChange={(e) => setProp(p.key, e.target.value)} aria-label={`Status of ${p.key}`}>{["unassessed", "insufficient", "conflicting", "contradicted", "supported"].map((s: any) => <option key={s} value={s}>{s}</option>)}</select>}</span>{p.notes && <span className="w-full text-xs muted">{p.notes}</span>}</li>)}</ul>
              </Section>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <Section title="Open questions for a trained reviewer"><ul className="list-disc pl-5 text-sm">{r.open_questions.map((q: string) => <li key={q}>{q}</li>)}</ul><p className="mt-2 text-xs muted">Non-exclusive hypotheses: {r.hypotheses_non_exclusive.join(" · ")}</p><p className="mt-1 text-xs muted">Never used as inputs: {r.prohibited_inputs.join(", ")}.</p></Section>
              <Section title="Reviewer decision" hint={reviewer ? "Supervisor/admin records the human-review outcome." : "Only a supervisor or admin can record the decision."}>
                <form onSubmit={decide} className="space-y-2 text-sm"><select className="input" value={decision.status} onChange={(e) => setDecision({ ...decision, status: e.target.value })} disabled={!reviewer} aria-label="Decision">{["HUMAN_REVIEWED", "INDETERMINATE", "REVIEW_REQUIRED", "CONFLICTING_EVIDENCE"].map((s: any) => <option key={s}>{s}</option>)}</select><textarea className="input" placeholder="Rationale (min 10 chars)" value={decision.rationale} onChange={(e) => setDecision({ ...decision, rationale: e.target.value })} disabled={!reviewer} required minLength={10} /><button className="btn-secondary" disabled={!reviewer}>Record decision</button></form>
                {r.reviewer_rationale && <p className="mt-2 text-xs">Last decision: <Chip v={r.status} /> — {r.reviewer_rationale}</p>}
              </Section>
            </div>
            {t && (
              <Section title="Account-control timeline" hint={`Dated, source-linked claims per role dimension. ${t.holder_differs_from_controller ? "Registered holder and controller differ in the recorded claims." : "No evidence yet that holder and controller differ."}`}>
                {t.lanes && Object.entries(t.lanes).map(([dim, items]: [string, any]) => (
                  <div key={dim} className="swimlane text-xs"><div className="lane-label pt-1">{dim.replace(/_/g, " ")}</div><div className="flex flex-wrap gap-1.5">{(items as any[]).length === 0 ? <span className="muted">unknown / no claim</span> : (items as any[]).map((c: any) => <span key={c.id} className="inset flex flex-col gap-0.5 p-1.5" title={c.description}><span className="flex items-center gap-1"><Chip v={c.claim_state === "direct" ? "observed" : c.claim_state === "alleged" ? "reported" : c.claim_state} /><span className="font-medium">{c.actor_label}</span></span><span className="muted"><When v={c.event_time} /></span>{c.counter_evidence && <span className="danger">counter: {c.counter_evidence}</span>}</span>)}</div></div>
                ))}
                {t.counter_evidence?.length > 0 && <p className="mt-2 text-xs danger">Contradictions: {t.counter_evidence.map((c: any) => c.detail).join("; ")}</p>}
                <form onSubmit={addClaim} className="mt-3 grid gap-2 text-xs md:grid-cols-6">
                  <select className="input" value={claim.role_dimension} onChange={(e) => setClaim({ ...claim, role_dimension: e.target.value })} aria-label="Role dimension">{t.dimensions.map((d: string) => <option key={d} value={d}>{d.replace(/_/g, " ")}</option>)}</select>
                  <input className="input" placeholder="Actor label (pseudonymous)" value={claim.actor_label} onChange={(e) => setClaim({ ...claim, actor_label: e.target.value })} required />
                  <select className="input" value={claim.claim_state} onChange={(e) => setClaim({ ...claim, claim_state: e.target.value })} aria-label="Claim state">{t.claim_states.map((s: string) => <option key={s}>{s}</option>)}</select>
                  <input className="input" placeholder="Source evidence id (needed for direct/corroborated)" value={claim.source_evidence_item_id} onChange={(e) => setClaim({ ...claim, source_evidence_item_id: e.target.value })} />
                  <input className="input" placeholder="Description" value={claim.description} onChange={(e) => setClaim({ ...claim, description: e.target.value })} required minLength={3} />
                  <button className="btn-secondary justify-center">Add claim</button>
                </form>
                <Limitations items={t.limitations} />
              </Section>
            )}
            <p className="text-xs muted">{r.disclaimer}</p>
          </div>
        )}
      </State>
    </div>
  );
}

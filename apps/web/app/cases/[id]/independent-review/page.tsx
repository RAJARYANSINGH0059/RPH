"use client";

import { FormEvent, useState } from "react";
import ListPage from "@/components/ListPage";
import { Chip, KV, Section, State, Toast, useApi, When } from "@/components/ui";
import { api, getUser } from "@/lib/api";

export default function Page() {
  return <ListPage title="Independent Investigation Review" subtitle="A reviewer assesses a hypothesis on its evidence. Blind mode hides the analyst's conclusion until the reviewer has recorded an assessment. Disagreement is preserved as dissent; nothing is overwritten." pageKey="independent-review">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any[]>(`/cases/${id}/hypotheses`);
  const [sel, setSel] = useState<string | null>(null);
  const [blind, setBlind] = useState(true);
  const view = useApi<any>(sel ? `/cases/${id}/hypotheses/${sel}/review-view?blind=${blind}` : null, [sel, blind]);
  const [form, setForm] = useState({ decision: "agree", rationale: "", requested: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const me = getUser();
  async function submit(e: FormEvent) { e.preventDefault(); if (!sel) return; setMsg(null); try { await api(`/cases/${id}/hypotheses/${sel}/reviews`, { method: "POST", body: JSON.stringify({ decision: form.decision, rationale: form.rationale, mode: blind ? "blind" : "open", requested_evidence: form.requested.split("\n").filter(Boolean) }) }); setMsg("Review recorded."); setBlind(false); reload(); view.reload(); } catch (err: any) { setMsg(err.message); } }
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="wb-grid">
          <Section title="Hypotheses to review">
            <ul className="space-y-1 text-sm">{data.map((h: any) => <li key={h.id}><button className={`w-full rounded-lg border p-2 text-left hover:bg-panel ${sel === h.id ? "border-accent bg-accent-soft/40" : "border-line"}`} onClick={() => setSel(h.id)}><div className="flex items-center justify-between gap-2"><span className="font-medium">{h.title}</span><Chip v={h.status === "supported" ? "supported" : h.status === "disputed" ? "contested" : "unresolved"} title={h.status} /></div><div className="text-xs muted">v{h.version} · {h.reviews.length} review(s){h.dissent_on_file ? " · dissent on file" : ""}{h.created_by === me?.id ? " · yours (cannot self-review)" : ""}</div></button></li>)}{data.length === 0 && <li className="muted">No hypotheses yet.</li>}</ul>
          </Section>
          <div className="space-y-3">
            {sel && view.data && (
              <Section title="Structured review view" actions={<label className="flex items-center gap-2 text-xs"><input type="checkbox" checked={blind} onChange={(e) => setBlind(e.target.checked)} /> blind (hide analyst conclusion)</label>}>
                <KV rows={[["Title", view.data.title], ["Kind", view.data.kind], ["Alternatives", view.data.alternatives.join("; ") || "—"], ["Supporting evidence ids", view.data.supporting_evidence_ids.join(", ") || "none"], ["Analyst conclusion", view.data.analyst_conclusion ? `${view.data.analyst_conclusion.statement} (${view.data.analyst_conclusion.status}, v${view.data.analyst_conclusion.version})` : "hidden (blind mode)"]]} />
                {view.data.challenges.length > 0 && <div className="mt-2 text-xs"><div className="label">Related challenge reports</div>{view.data.challenges.map((c: any) => <div key={c.alleged_relationship.id}><span className="mono">{c.alleged_relationship.type}</span> · {c.current_conclusion.state} · {c.counter_evidence.length} counter-evidence</div>)}</div>}
                <form onSubmit={submit} className="mt-3 space-y-2 text-sm border-t border-line pt-3"><select className="input" value={form.decision} onChange={(e) => setForm({ ...form, decision: e.target.value })}>{["agree", "disagree", "request_evidence", "unresolved"].map((d: any) => <option key={d} value={d}>{d.replace("_", " ")}</option>)}</select><textarea className="input" placeholder="Independent rationale (min 10 chars)" value={form.rationale} onChange={(e) => setForm({ ...form, rationale: e.target.value })} required minLength={10} /><textarea className="input" placeholder="Evidence you would need (one per line)" value={form.requested} onChange={(e) => setForm({ ...form, requested: e.target.value })} /><button className="btn">Record review</button></form>
                <Toast msg={msg} onClose={() => setMsg(null)} />
              </Section>
            )}
            {sel && (() => { const h = data.find((x: any) => x.id === sel); return h && h.reviews.length > 0 && <Section title="Review history (append-only)"><ul className="space-y-1 text-xs">{h.reviews.map((r: any) => <li key={r.id}><Chip v={r.decision === "agree" ? "supported" : r.decision === "disagree" ? "contradicted" : "unresolved"} title={r.decision} /> v{r.hypothesis_version} · {r.mode} · {r.rationale} <span className="muted"><When v={r.created_at} /></span>{r.is_dissent && <span className="badge lvl-contradicted ml-1">dissent</span>}</li>)}</ul></Section>; })()}
            {!sel && <div className="card text-sm muted">Select a hypothesis. Reviews are recorded independently; a reviewer cannot review their own hypothesis.</div>}
          </div>
        </div>
      )}
    </State>
  );
}

"use client";

import { useState } from "react";
import CasePage from "@/components/CasePage";
import { KV, Section, State, Toast, useApi } from "@/components/ui";
import { api } from "@/lib/api";

export default function ChallengePage() {
  return <CasePage title="Blind Investigation Challenge" subtitle="Investigate with the ordinary tools, record your conclusions, lock them, then reveal the sealed ground truth and your measured scores. Synthetic evaluation only; it says nothing about real-world accuracy." pageKey="challenge">{(c, id) => <Body id={id} synthetic={c.is_synthetic} />}</CasePage>;
}

function Body({ id, synthetic }: { id: string; synthetic: boolean }) {
  const st = useApi<any>(`/synthetic/cases/${id}/challenge`);
  const paths = useApi<any>(`/cases/${id}/paths`);
  const [mules, setMules] = useState<string[]>([]);
  const [domains, setDomains] = useState("");
  const [notes, setNotes] = useState("");
  const [reveal, setReveal] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const accounts: string[] = Array.from(new Set((paths.data?.paths || []).flatMap((p: any) => p.accounts.slice(1)))) as string[];
  async function submit() { setMsg(null); try { await api(`/synthetic/cases/${id}/challenge/submit`, { method: "POST", body: JSON.stringify({ mule_pattern_accounts: mules, common_operator_domains: domains.split(/[\s,]+/).filter(Boolean), unresolved_notes: notes }) }); setMsg("Submission locked."); st.reload(); } catch (e: any) { setMsg(e.message); } }
  async function doReveal() { setMsg(null); try { setReveal(await api(`/synthetic/cases/${id}/challenge/reveal`)); } catch (e: any) { setMsg(e.message); } }
  if (!synthetic) return <div className="card text-sm">Challenge mode exists only for synthetic cases: there is no sealed truth for an uploaded case.</div>;
  return (
    <State loading={st.loading} error={st.error} onRetry={st.reload}>
      {st.data && (
        <div className="space-y-4">
          <div className="callout text-sm"><ol className="list-decimal pl-5">{st.data.instructions.map((x: string) => <li key={x}>{x}</li>)}</ol></div>
          <Toast msg={msg} onClose={() => setMsg(null)} />
          {!st.data.submitted ? (
            <Section title="Your conclusions" hint="Tick the accounts you consider mule-pattern (after your own investigation) and list any domains you would assert share an operator.">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-sm">{accounts.map((a: any) => <label key={a} className="inset flex items-center gap-2 p-2"><input type="checkbox" checked={mules.includes(a)} onChange={(e) => setMules((c) => e.target.checked ? [...c, a] : c.filter((x: any) => x !== a))} /><span className="mono text-xs">{a}</span></label>)}</div>
              <input className="input mt-3" placeholder="Domains you would assert share an operator (comma separated; leave empty if none)" value={domains} onChange={(e) => setDomains(e.target.value)} />
              <textarea className="input mt-2" placeholder="What remains unresolved, in your view" value={notes} onChange={(e) => setNotes(e.target.value)} />
              <button className="btn mt-3" onClick={submit}>Submit and lock</button>
            </Section>
          ) : (
            <Section title="Submission locked" hint={`Locked at ${st.data.locked_at}`}>
              {!reveal && <button className="btn" onClick={doReveal}>Reveal sealed truth and scores</button>}
              {reveal && (
                <div className="space-y-3">
                  <div className="badge simulated">{reveal.label}</div>
                  <KV rows={[["Mule accounts identified", `${reveal.scores.mule_accounts_identified} of ${reveal.scores.mule_accounts_total}`], ["Recall / precision", `${reveal.scores.mule_recall ?? "—"} / ${reveal.scores.mule_precision ?? "—"}`], ["Innocent or victim accounts you flagged", reveal.scores.innocent_or_victim_accounts_flagged.join(", ") || "none"], ["Decoy domains asserted as common operator", reveal.scores.decoy_domains_asserted_as_common_operator.join(", ") || "none"], ["Decoy rejection", String(reveal.scores.decoy_rejection)], ["System path coverage of true chains", String(reveal.scores.system_path_coverage_of_true_chains)]]} />
                  <div className="grid gap-3 md:grid-cols-2 text-xs"><div><div className="label">Truth summary (generator labels, fictional)</div><KV rows={[["Victims", reveal.truth_summary.victims.join(", ")], ["Collection / layering accounts", reveal.truth_summary.collection_and_layering_accounts.join(", ")], ["Campaign domains", reveal.truth_summary.campaign_domains.join(", ")], ["Decoy domains", reveal.truth_summary.decoy_domains.join(", ")], ["Planted chaos", reveal.truth_summary.planted_chaos.join(", ")]]} /></div><div><div className="label">Scenario specifics</div><pre className="mono max-h-60 overflow-auto rounded-lg bg-panel p-2 text-[11px]">{JSON.stringify({ rotation: reveal.truth_summary.rotation, missing_period: reveal.truth_summary.missing_period, control_hypothesis: reveal.truth_summary.control_hypothesis, allocation_sample: reveal.truth_summary.simulated_allocation_sample }, null, 1)}</pre></div></div>
                  {reveal.baseline_comparison && (
                    <div className="inset p-3 text-xs">
                      <div className="label">Graph-only baseline vs PS05-X on this case</div>
                      <p className="muted mb-2">{reveal.baseline_comparison.baseline_definition}</p>
                      <KV rows={[["Flagged accounts (baseline vs PS05-X paths vs triage cue)", `${reveal.baseline_comparison.graph_only_baseline.flagged_accounts} vs ${reveal.baseline_comparison.ps05x_paths?.flagged_accounts ?? "—"} vs ${reveal.baseline_comparison.ps05x.flagged_accounts}`], ["Mule recall", `${reveal.baseline_comparison.graph_only_baseline.mule_recall ?? "—"} vs ${reveal.baseline_comparison.ps05x_paths?.mule_recall ?? "—"} vs ${reveal.baseline_comparison.ps05x.mule_recall ?? "—"}`], ["Mule precision", `${reveal.baseline_comparison.graph_only_baseline.mule_precision ?? "—"} vs ${reveal.baseline_comparison.ps05x_paths?.mule_precision ?? "—"} vs ${reveal.baseline_comparison.ps05x.mule_precision ?? "—"}`], ["Innocent or victim accounts flagged", `${reveal.baseline_comparison.graph_only_baseline.innocent_or_victim_accounts_flagged} vs ${reveal.baseline_comparison.ps05x_paths?.innocent_or_victim_accounts_flagged ?? "—"} vs ${reveal.baseline_comparison.ps05x.innocent_or_victim_accounts_flagged}`], ["Common-operator pairs asserted", `${reveal.baseline_comparison.graph_only_baseline.common_operator_pairs_asserted} (decoys: ${reveal.baseline_comparison.graph_only_baseline.decoy_pairs_asserted}) vs ${reveal.baseline_comparison.ps05x.common_operator_pairs_asserted}`]]} />
                      <p className="muted mt-1">{reveal.baseline_comparison.label}</p>
                    </div>
                  )}
                  <p className="text-xs muted">{reveal.note}</p>
                </div>
              )}
            </Section>
          )}
        </div>
      )}
    </State>
  );
}

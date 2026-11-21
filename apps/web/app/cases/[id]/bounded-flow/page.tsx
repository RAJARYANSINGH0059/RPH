"use client";

import Link from "next/link";
import { useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Money, Raw, Section, State, Table, useApi, When } from "@/components/ui";

export default function BoundedFlowPage() {
  return <CasePage title="Bounded Fund Provenance" subtitle="Feasible minimum and maximum victim-origin amounts on each onward transfer, solved as a linear programme over the account's balance history. A range is the honest answer after commingling." pageKey="bounded">{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const paths = useApi<any>(`/cases/${id}/paths`);
  const [idx, setIdx] = useState<number | null>(null);
  const [scenario, setScenario] = useState<string>("");
  const q = `/cases/${id}/bounded-flow?${idx !== null ? `path_index=${idx}&` : ""}${scenario ? `scenario=${scenario}` : ""}`;
  const { data, error, reload } = useApi<any>(q, [idx, scenario]);
  const plist = paths.data?.paths || [];
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-3 text-sm">
        <label>Path <select className="input !w-auto" value={idx ?? ""} onChange={(e) => setIdx(e.target.value === "" ? null : Number(e.target.value))} aria-label="Path"><option value="">auto (first path with a downstream statement)</option>{plist.map((p: any, i: number) => <option key={i} value={i}>#{i} {p.accounts.map((a: string) => a.slice(-4)).join(" → ")} · {p.status}</option>)}</select></label>
        <label>Assumption scenario <select className="input !w-auto" value={scenario} onChange={(e) => setScenario(e.target.value)} aria-label="Scenario"><option value="">none (bounds only)</option><option value="fifo">FIFO (assumption)</option><option value="lifo">LIFO (assumption)</option></select></label>
        <Link href={`/cases/${id}/money-trail`} className="ml-auto text-accent-deep underline">Open money-trail reconstruction</Link>
      </div>
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-4">
              <div className="card"><div className="label mb-0">Attribution status</div><div className="mt-1"><Chip v={data.attribution_status === "EXACT_UNDER_CONSTRAINTS" ? "corroborated" : data.attribution_status === "BOUNDED_UNDER_CONSTRAINTS" ? "derived" : data.attribution_status === "INFEASIBLE" ? "contradicted" : "unresolved"} /> <span className="mono text-sm">{data.attribution_status}</span></div></div>
              <div className="card"><div className="label mb-0">Origin</div><div className="num mt-1 text-xl font-bold"><Money v={data.origin?.amount_minor} /></div><div className="text-xs muted">from {data.origin?.victim_account}</div></div>
              <div className="card"><div className="label mb-0">Path</div><div className="mt-1 text-sm">{data.path ? data.path.accounts.map((a: string) => a.slice(-6)).join(" → ") : "—"}</div><div className="text-xs muted">{data.path?.status}</div></div>
              <div className="card"><div className="label mb-0">Solver</div><div className="mt-1 text-xs">{data.method} · {data.solver}</div><div className="text-xs muted">{data.variables} variables · {data.constraints?.inequalities} ≤ · {data.constraints?.equalities} =</div></div>
            </div>
            <Section title="Per-hop attribution bounds" hint="Band = feasible victim-origin amount within the observed transfer. Exact only when min = max.">
              {data.hops.length === 0 && <p className="text-sm muted">{data.warnings?.join(" ") || "No onward transfer could be bounded."}</p>}
              <div className="space-y-3">
                {data.hops.map((h: any) => {
                  const amt = h.observed_transfer_minor || 1;
                  const lo = (h.minimum_attributable_minor ?? 0) / amt * 100, hi = (h.maximum_attributable_minor ?? 0) / amt * 100;
                  return (
                    <div key={h.transaction_id} className="inset p-3 text-sm">
                      <div className="flex flex-wrap items-center justify-between gap-2"><div><span className="font-semibold">{h.account?.slice(-6)} → {h.to_account?.slice(-6) || "?"}</span> <span className="muted">· <When v={h.event_time} /></span></div><div>observed <Money v={h.observed_transfer_minor} /></div></div>
                      <div className="range-bar mt-2" aria-label={`attributable between ${h.minimum_attributable_minor} and ${h.maximum_attributable_minor} paise`}>{h.minimum_attributable_minor !== null && <span style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.5)}%` }} />}{h.exact && <i style={{ left: `${lo}%` }} />}</div>
                      <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs"><span>min <Money v={h.minimum_attributable_minor} /> · max <Money v={h.maximum_attributable_minor} />{h.exact && <span className="badge lvl-corroborated ml-2">exact under constraints</span>}</span><span className="muted">not attributable from evidence: <Money v={h.not_attributable_from_evidence_minor} /></span></div>
                      <details className="mt-1 text-xs"><summary className="cursor-pointer muted">Why is this uncertain?</summary><p className="mt-1">{h.explanation}</p><p className="mt-1 muted">Witness allocations (illustrative, not a trace of rupees): min {JSON.stringify(h.witness_allocation_min)} · max {JSON.stringify(h.witness_allocation_max)}</p></details>
                    </div>
                  );
                })}
              </div>
            </Section>
            <div className="grid gap-3 lg:grid-cols-2">
              <Section title="Invariant facts" hint="True under every feasible allocation."><ul className="list-disc pl-5 text-sm">{data.invariant_facts?.length ? data.invariant_facts.map((x: string) => <li key={x}>{x}</li>) : <li className="muted">None established.</li>}</ul></Section>
              <Section title="Possible, not invariant"><ul className="list-disc pl-5 text-sm">{data.possible_not_invariant?.length ? data.possible_not_invariant.map((x: string) => <li key={x}>{x}</li>) : <li className="muted">—</li>}</ul></Section>
              {data.gross_net && (
                <Section title="Gross vs net onward transfers" hint="Reversals and refunds are shown, never netted silently.">
                  <KV rows={[["Gross onward (this path)", <Money key="g" v={data.gross_net.gross_onward_minor} />], ["Reversed onward", <Money key="r" v={data.gross_net.reversed_onward_minor} />], ["Net onward", <Money key="n" v={data.gross_net.net_onward_minor} />], ["Reversal pairs detected in the account", String(data.gross_net.reversals_detected)]]} />
                  <p className="mt-1 text-xs muted">{data.gross_net.definitions}</p>
                  {(data.reversals || []).length > 0 && <Table dense cols={["Account", "Debit ref", "Credit ref", "Amount", "Handling"]} rows={data.reversals.map((r: any) => [<span key="a" className="mono">{r.account?.slice(-6)}</span>, <span key="d" className="mono">{r.debit_reference || "—"}</span>, <span key="c" className="mono">{r.credit_reference || "—"}</span>, <Money key="m" v={r.amount_minor} />, <span key="h" className="text-xs">{r.handling}</span>])} />}
                </Section>
              )}
              <Section title="Missing evidence that would narrow the interval"><Table dense cols={["Account", "Needed", "Effect"]} rows={(data.missing_evidence || []).map((m: any) => [m.account, m.needed, m.effect])} empty="Nothing missing on this path." /></Section>
              <Section title="Assumptions and inconsistencies">
                <ul className="list-disc pl-5 text-sm">{(data.assumptions || []).map((a: any, i: number) => <li key={i}><span className="font-medium">{a.account?.slice(-6)}:</span> {a.assumption}</li>)}{(data.inconsistencies || []).map((a: any, i: number) => <li key={"i" + i} className="danger">{a.account?.slice(-6)}: {a.issue}{a.handling ? ` — ${a.handling}` : ""}</li>)}{!data.assumptions?.length && !data.inconsistencies?.length && <li className="muted">None.</li>}</ul>
              </Section>
            </div>
            {scenario && data.scenarios?.[scenario] && <Section title={data.scenarios[scenario].label} hint="Assumption-based comparison, never a fact."><Table dense cols={["From", "Transaction", "To", `Victim-origin under ${scenario.toUpperCase()}`, "Transfer"]} rows={data.scenarios[scenario].hops.map((h: any) => [h.account?.slice(-6), h.transaction_id.slice(0, 8), h.to_account?.slice(-6), <Money key="v" v={h[`victim_origin_under_${scenario}`]} />, <Money key="t" v={h.transfer_minor} />])} /></Section>}
            <MotionScene scene="financial_flow" height={120} />
            <Limitations items={data.limitations} />
            <Raw data={data} />
          </div>
        )}
      </State>
    </div>
  );
}

"use client";

import { useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Money, Section, State, Table, useApi } from "@/components/ui";

export default function InterventionPage() {
  return <CasePage title="Intervention Impact" subtitle="Hypothetical comparison of account-level scenarios for an authorised decision-maker. Whole-account balance, investigated inflows, other activity and unknown exposure are kept apart. Nothing here freezes, liens or notifies anything." pageKey="intervention" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const ck = useApi<any>(`/cases/${id}/chokepoints`);
  const accounts: string[] = (ck.data?.rows || []).map((r: any) => r.account);
  const [acct, setAcct] = useState("");
  const [ack, setAck] = useState(false);
  const current = acct || accounts[0] || "";
  const { data, error, reload, loading } = useApi<any>(current ? `/cases/${id}/intervention/${encodeURIComponent(current)}?acknowledged=${ack}` : null, [current, ack]);
  return (
    <div className="space-y-4">
      <div className="card flex flex-wrap items-center gap-3 text-sm"><label>Account <select className="input !w-auto" value={current} onChange={(e) => setAcct(e.target.value)} aria-label="Account">{accounts.map((a: any) => <option key={a} value={a}>{a}</option>)}</select></label>
        <label className="ml-auto flex items-center gap-2"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand this is a simulation, not a recommendation or an action</label></div>
      <State loading={loading} error={error} onRetry={reload} empty={!current ? "No account on a reconstructed path yet." : undefined}>
        {data && (
          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-5">
              {[["Observed balance", data.ledger.observed_balance_minor, "whole account; not the proceeds"], ["Investigated inflows", data.ledger.investigated_inflows_minor, "credits on victim-origin paths"], ["Other inflows", data.ledger.other_inflows_minor_not_labelled, "not labelled legitimate or illegitimate"], ["Onward on paths", data.ledger.onward_transfers_on_paths_minor, "debits on reconstructed hops"], ["Cash withdrawals", data.ledger.cash_withdrawals_minor, "observed"]].map(([l, v, h]) => <div key={l as string} className="card"><div className="label mb-0">{l as string}</div><div className="metric-value mt-2"><Money v={v as number} /></div><div className="text-xs muted">{h as string}</div></div>)}
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              <Section title="Attributable to investigated funds" hint="Bounds come from Bounded Fund Provenance per path landing on this account.">
                <KV rows={[["Definitely attributable (lower bound)", <Money key="a" v={data.ledger.definitely_attributable_minor_lower_bound} />], ["Potentially attributable (upper bound)", <Money key="b" v={data.ledger.potentially_attributable_minor_upper_bound} />], ["Reversals / refunds", <Money key="c" v={data.ledger.reversals_refunds_minor} />], ["Account type", data.account_type], ["Unknown", data.ledger.unknown.join("; ") || "statement supplied"]]} />
                <p className="mt-2 text-xs muted">Derivation: {Object.entries(data.ledger.derivation).map(([k, v]: [any, any]) => `${k}: ${v}`).join(" · ")}</p>
              </Section>
              <Section title="Unrelated or not-yet-linked activity" hint={data.unrelated_activity.labelling}>
                <KV rows={[["Observed counterparties", String(data.unrelated_activity.counterparties_observed.length)], ["Transactions", String(data.unrelated_activity.transactions)], ["Amount", <Money key="m" v={data.unrelated_activity.amount_minor} />], ["Unknown population", data.unrelated_activity.unknown_population]]} />
              </Section>
            </div>
            {ack ? (
              <Section title="Hypothetical scenarios" hint="Legal availability must be validated by an authorised officer; nothing is asserted here.">
                <Table cols={["Scenario", "Investigated amount covered", "Unrelated activity potentially affected", "Counterparties affected", "Missing evidence", "Assumption"]} rows={data.scenarios.map((s: any) => [<span key="s"><Chip v="candidate" title="hypothetical" /> <span className="font-medium">{s.scenario.replace(/_/g, " ")}</span></span>, <Money key="a" v={s.investigated_amount_covered_minor} />, <Money key="b" v={s.unrelated_activity_potentially_affected_minor} />, s.unrelated_counterparties_potentially_affected, <span key="m" className="text-xs">{s.missing_evidence.join("; ") || "—"}</span>, <span key="n" className="text-xs">{s.assumptions}</span>])} />
                <p className="mt-2 text-xs muted">Uncertainty: attribution bounds {JSON.stringify(data.scenarios[0]?.uncertainty.attribution_bounds)} · balance known: {String(data.scenarios[0]?.uncertainty.balance_known)} · statement supplied: {String(data.scenarios[0]?.uncertainty.statement_supplied)}</p>
              </Section>
            ) : <div className="callout-warn text-sm">{data.acknowledgement_required} Tick the box above to view scenarios.</div>}
            <Section title="Blast radius (observed relationships only)"><Table dense cols={["From", "To", "Kind", "Amount"]} rows={data.blast_radius.edges.slice(0, 60).map((e: any, i: number) => [<span key="f" className="mono">{e.from}</span>, <span key="t" className="mono">{e.to}</span>, <Chip key="k" v={e.kind.includes("investigated") || e.kind.includes("onward") ? "observed" : "derived"} title={e.kind} />, <Money key="a" v={e.amount_minor} />])} /></Section>
            <MotionScene scene="recovery_reconciliation" height={110} />
            <Limitations items={data.limitations} />
          </div>
        )}
      </State>
    </div>
  );
}

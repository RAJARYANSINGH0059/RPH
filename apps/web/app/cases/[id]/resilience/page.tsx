"use client";

import { useState } from "react";
import CasePage from "@/components/CasePage";
import { Chip, Limitations, Money, Section, State, Table, Toast, useApi, When } from "@/components/ui";
import { api } from "@/lib/api";

export default function ResiliencePage() {
  return <CasePage title="Network Adaptation Simulator" subtitle="What-if removal of accounts or functions on a copy of the observed money network. Alternative routes are counted only among observed transfers; hypothetical replacements are labelled and never evidence. Centrality is not culpability." pageKey="resilience" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const ck = useApi<any>(`/cases/${id}/chokepoints`);
  const scen = useApi<any>(`/cases/${id}/resilience/scenarios`);
  const [remove, setRemove] = useState<string[]>([]);
  const [fn, setFn] = useState<string>("");
  const [subOld, setSubOld] = useState(""); const [subNew, setSubNew] = useState("");
  const [res, setRes] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function simulate() {
    setMsg(null);
    try { setRes(await api(`/cases/${id}/resilience/simulate`, { method: "POST", body: JSON.stringify({ remove_accounts: remove, remove_function: fn || null, substitutions: subOld && subNew ? { [subOld]: subNew } : {} }) })); scen.reload(); }
    catch (e: any) { setMsg(e.message); }
  }
  const rows = ck.data?.rows || [];
  return (
    <State loading={ck.loading} error={ck.error} onRetry={ck.reload}>
      {ck.data && (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
            <Section title="Baseline: structural chokepoints" hint="Observed/corroborated money edges only. Tick accounts to remove them in the simulation.">
              <Table dense cols={["", "Account", "Role", "Paths through", "Amount through", "Betweenness", "Paths cut if missing"]} rows={rows.map((r: any) => [<input key="c" type="checkbox" aria-label={`remove ${r.account}`} checked={remove.includes(r.account)} onChange={(e) => setRemove((cur) => e.target.checked ? [...cur, r.account] : cur.filter((x: any) => x !== r.account))} />, <span key="a" className="mono">{r.account}</span>, r.role, r.supported_paths_through, <Money key="m" v={r.distinct_amount_through_minor} />, r.betweenness, r.paths_disconnected_if_records_missing])} empty="No money edges yet." />
              <p className="mt-2 text-xs muted">Excluded: {ck.data.excluded_edges.join("; ")}.</p>
            </Section>
            <Section title="Scenario" hint="Assumptions are shown beside the output and saved with the run.">
              <div className="space-y-2 text-sm">
                <label className="block">Remove a whole function <select className="input" value={fn} onChange={(e) => setFn(e.target.value)}><option value="">none</option><option value="collection">collection accounts</option><option value="layering">layering accounts</option><option value="exit">exit accounts</option></select></label>
                <div className="grid grid-cols-2 gap-2"><input className="input" placeholder="Substitute this account…" value={subOld} onChange={(e) => setSubOld(e.target.value)} aria-label="Account to substitute" /><input className="input" placeholder="…with hypothetical account" value={subNew} onChange={(e) => setSubNew(e.target.value)} aria-label="Hypothetical replacement" /></div>
                <p className="text-xs muted">Selected for removal: {remove.length ? remove.map((a: any) => a.slice(-6)).join(", ") : "none"}.</p>
                <button className="btn w-full justify-center" onClick={simulate} disabled={!remove.length && !fn}>Run simulation on a copy</button>
                <Toast msg={msg} onClose={() => setMsg(null)} />
              </div>
            </Section>
          </div>
          {res && (
            <Section title="Before / after" hint={res.findings[0]?.statement}>
              <div className="grid gap-3 md:grid-cols-5 text-sm">
                {[["paths total", res.diff.paths_total], ["affected", res.diff.paths_affected], ["disconnected", res.diff.paths_disconnected], ["observed alternative", res.diff.paths_with_alternative_observed_route], ["hypothetical-only route", res.diff.paths_with_hypothetical_route_only]].map(([l, v]) => <div key={l as string} className="inset p-2"><div className="label mb-0">{l as string}</div><div className="num text-xl font-bold">{String(v)}</div></div>)}
              </div>
              <div className="mt-3 grid gap-3 lg:grid-cols-2 text-xs">
                <div><div className="label">Assumptions</div><ul className="list-disc pl-4">{res.assumptions.map((a: string) => <li key={a} className={a.startsWith("ASSUMPTION") ? "warn" : ""}>{a}</li>)}</ul>{res.diff.sensitive_to_uncertain_edges && <p className="mt-2 warn">Result depends on edges with uncertain times.</p>}{res.dependencies_without_observed_substitute.length > 0 && <p className="mt-2">No observed substitute for: {res.dependencies_without_observed_substitute.join(", ")} (absence of an observed alternative is not proof none exists).</p>}</div>
                <div><div className="label">Affected paths</div><ul className="space-y-1">{res.after.filter((a: any) => a.affected).map((a: any) => <li key={a.path_index} className="inset p-1.5"><span className="mono">{a.route.map((x: string) => x.slice(-5)).join(" → ")}</span> · {a.still_reachable_in_observed_records ? (a.alternative_uses_hypothetical_node ? <Chip v="candidate" title="hypothetical" /> : <Chip v="observed" title="observed alternative" />) : <Chip v="contradicted" title="disconnected" />}{a.alternative_observed_routes[0] && <span className="muted"> alt: {a.alternative_observed_routes[0].map((x: string) => x.slice(-5)).join(" → ")}</span>}</li>)}</ul></div>
              </div>
              <Limitations items={res.limitations} />
            </Section>
          )}
          <Section title="Saved scenarios"><Table dense cols={["When", "Removed", "Function", "Substitutions", "Disconnected", "Alt routes"]} rows={(scen.data || []).map((s: any) => [<When key="w" v={s.created_at} />, (s.inputs.remove_accounts || []).map((a: string) => a.slice(-6)).join(", ") || "—", s.inputs.remove_function || "—", Object.keys(s.inputs.substitutions || {}).length, s.diff?.paths_disconnected, s.diff?.paths_with_alternative_observed_route])} empty="No saved scenarios." /></Section>
          <Limitations items={ck.data.limitations} />
        </div>
      )}
    </State>
  );
}

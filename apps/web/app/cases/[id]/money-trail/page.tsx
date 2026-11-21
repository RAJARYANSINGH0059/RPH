"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { MotionScene } from "@/components/motion";
import { Chip, Limitations, Money, Section, State, useApi, When } from "@/components/ui";

export default function Page() {
  return <ListPage title="Money-Trail Reconstruction" subtitle="Reconstructed multi-hop paths (algorithm v2). Each hop is observed, corroborated or uncertain in time; splits and merged inflows are flagged; a path ends unresolved when the last account's statement is not in the case, and the system names the statement that would resolve it." pageKey="money-trail">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/paths`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-4"><div className="card"><div className="label mb-0">Paths</div><div className="num text-2xl font-bold">{data.paths.length}</div></div><div className="card"><div className="label mb-0">Unresolved ends</div><div className="num text-2xl font-bold">{data.paths.filter((p: any) => p.status === "unresolved").length}</div></div><div className="card"><div className="label mb-0">Time-uncertain</div><div className="num text-2xl font-bold">{data.paths.filter((p: any) => p.time_uncertain).length}</div></div><div className="card"><div className="label mb-0">Statements reconciled</div><div className="num text-2xl font-bold">{data.reconciliation.length}</div></div></div>
          {data.paths.map((p: any, i: number) => (
            <Section key={i} title={<span className="flex flex-wrap items-center gap-2">Path #{i} <Chip v={p.path_class === "uncertain_time" ? "candidate" : p.path_class} /> <Chip v={p.status === "complete" ? "corroborated" : "unresolved"} title={p.status} />{p.flags.map((f: string) => <span key={f} className="badge lvl-candidate">{f.replace(/_/g, " ")}</span>)}</span>}
              actions={<div className="flex gap-2"><Link className="btn-secondary !py-1" href={`/cases/${id}/bounded-flow`}>Bound attribution</Link><Link className="btn-secondary !py-1" href={`/cases/${id}/paths`}>Proof certificate</Link></div>}>
              <ol className="flex flex-wrap items-center gap-2 text-sm">{p.accounts.map((a: string, k: number) => <li key={k} className="flex items-center gap-2"><span className="rounded-lg border border-line bg-canvas px-2 py-1 mono text-xs">{a}</span>{k < p.hops.length && <span className="flex flex-col items-center text-[10px] muted"><span>→ <Money v={p.hops[k].amount_minor} /></span><span>{p.hops[k].hop_class.replace("_", " ")}{p.hops[k].flags.length ? ` · ${p.hops[k].flags.join(",")}` : ""}</span><When v={p.hops[k].time} /></span>}</li>)}</ol>
              <div className="mt-2 text-xs muted">entry <Money v={p.total_in_minor} /> · exit <Money v={p.exit_amount_minor} /> · conservation {p.conservation_ratio ?? "—"} · temporal consistency {p.temporal_consistent ? "yes" : "no"} · alternatives {p.alternatives}</div>
              {p.status === "unresolved" && <div className="callout-warn mt-2 text-xs"><div><div className="font-semibold">{p.unresolved_reason}</div><div>{p.resolution_hint}</div></div></div>}
            </Section>
          ))}
          {data.paths.length === 0 && <div className="card text-sm muted">No reconstructed path yet: upload a statement with at least one transfer.</div>}
          <MotionScene scene="financial_flow" height={110} />
          <Limitations items={["Amounts are never invented: a hop larger than the running amount is flagged merged_inflow; smaller is split.", "An unresolved end means a statement is missing, not that the money stopped."]} />
        </div>
      )}
    </State>
  );
}

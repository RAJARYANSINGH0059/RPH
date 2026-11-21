"use client";

import Shell from "@/components/Shell";
import { Limitations, Section, State, Table, useApi } from "@/components/ui";

function Metric({ m }: { m: Record<string, any> }) {
  const keys = Object.keys(m.D_ps05x_full || m);
  const cfgs = ["A_transaction_rules", "B_financial_graph_only", "C_combined_no_safeguards", "D_ps05x_full"].filter((c: any) => m[c]);
  return <Table dense cols={["Metric", ...cfgs.map((c: any) => c.replace(/_/g, " "))]} rows={keys.filter((k: any) => typeof (m.D_ps05x_full || m)[k] !== "object").map((k: any) => [k.replace(/_/g, " "), ...cfgs.map((c: any) => { const v = m[c]?.[k]; return typeof v === "number" ? v.toFixed(3) : String(v ?? "—"); })])} />;
}
export default function Page() {
  const { data, error, reload } = useApi<any>("/benchmark/results");
  return (
    <Shell title="Evaluation Results" subtitle="Measured on synthetic, sealed-truth cases. Smoke (development seeds) and frozen held-out runs are reported separately. Sample sizes and intervals are in the raw JSON." pageKey="benchmark">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <div className="space-y-3">
          {["smoke", "heldout"].map((k: any) => data[k] && <Section key={k} title={k === "smoke" ? "Smoke run" : "Frozen held-out run"} hint={`${data[k].summary?.cases_per_config ?? "?"} cases per configuration · seeds ${JSON.stringify(data[k].summary?.seeds ?? "")}`}>{data[k].summary?.by_config ? <Metric m={data[k].summary.by_config} /> : <pre className="mono max-h-96 overflow-auto rounded-lg bg-panel p-3 text-[11px]">{JSON.stringify(data[k].summary, null, 1).slice(0, 6000)}</pre>}</Section>)}
          {data.v2 && <Section title="Next-wave metrics (v2)" hint={data.v2.note}><pre className="mono max-h-96 overflow-auto rounded-lg bg-panel p-3 text-[11px]">{JSON.stringify(data.v2, null, 1).slice(0, 8000)}</pre></Section>}
          {!data.smoke && !data.heldout && <div className="card text-sm muted">No benchmark results shipped with this deployment. Run the benchmark locally; results are written to tests/benchmark/results.</div>}
          <Limitations items={["Synthetic benchmark; not real-world accuracy.", "A single best seed is never the headline: means and intervals are reported."]} /></div>}
      </State>
    </Shell>
  );
}

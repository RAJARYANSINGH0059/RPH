"use client";

import Shell from "@/components/Shell";
import { KV, Limitations, Section, State, Table, useApi } from "@/components/ui";

export default function Page() {
  const { data, error, reload } = useApi<any>("/benchmark/results");
  return (
    <Shell title="Benchmark Centre" subtitle="How PS05-X is measured: four configurations on identical synthetic cases scored against sealed truth, with seeds, held-out families and confidence intervals. F1 is not accuracy and no real-world transfer is claimed." pageKey="benchmark">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <div className="space-y-3">
          <Section title="Methodology"><KV rows={[["Configurations", "A rules only · B financial graph · C combined without safeguards · D PS05-X full"], ["Scoring", "every case is generated, sealed, ingested through the public upload pipeline, then scored"], ["Seeds", `smoke ${data.smoke?.summary?.seeds ?? "—"} · held-out ${data.heldout?.summary?.seeds ?? "—"}`], ["Generator / path algorithm", `${data.smoke?.summary?.generator_version ?? "—"} / ${data.smoke?.summary?.path_algorithm_version ?? "—"}`], ["Reproduce", "python tests/benchmark/run_benchmark.py --seeds 4 --size small"], ["Commit", data.commit || "—"]]} /></Section>
          {data.v2 && (
            <Section title="Benchmark v2 — next-wave metrics" hint={`${data.v2.sample_size?.cases ?? data.v2.cases} cases · ${data.v2.seeds?.length ?? "—"} seeds × ${data.v2.scenarios?.length ?? "—"} families · generator ${data.v2.generator_version} · ${data.v2.generated_at}`}>
              <p className="mb-2 text-xs muted">{data.v2.note} Bootstrap 95% CIs and min/max are shown; perfect synthetic scores show internal consistency, not field accuracy.</p>
              <Table dense cols={["Metric", "Mean", "95% CI", "Min", "Max", "n"]} rows={Object.entries(data.v2.metrics || {}).filter(([k]) => k !== "runtime_s").map(([k, v]: [string, any]) => [<span key="k" className="mono text-xs">{k}</span>, v.mean ?? "—", v.ci95 ? `${v.ci95[0]} – ${v.ci95[1]}` : "—", v.min ?? "—", v.max ?? "—", v.n ?? "—"])} />
              {data.v2.metrics?.baseline_mule_recall && (
                <div className="mt-3">
                  <div className="label">Graph-only baseline vs PS05-X (same cases, same sealed truth)</div>
                  <p className="text-xs muted">{data.v2.baseline_definition}</p>
                  <Table dense cols={["", "Graph-only baseline (naive traversal)", "PS05-X fund paths (safeguarded)", "PS05-X rule triage (cue only)"]} rows={[["Mule recall (mean)", data.v2.metrics.baseline_mule_recall?.mean ?? "—", data.v2.metrics.ps05x_path_mule_recall?.mean ?? "—", data.v2.metrics.ps05x_mule_recall?.mean ?? "—"], ["Mule precision (mean)", data.v2.metrics.baseline_mule_precision?.mean ?? "—", data.v2.metrics.ps05x_path_mule_precision?.mean ?? "—", data.v2.metrics.ps05x_mule_precision?.mean ?? "—"], ["Innocent/victim accounts flagged per case (mean)", data.v2.metrics.baseline_innocent_flagged?.mean ?? "—", data.v2.metrics.ps05x_path_innocent_flagged?.mean ?? "—", data.v2.metrics.ps05x_innocent_flagged?.mean ?? "—"], ["Common-operator pairs asserted per case (mean)", data.v2.metrics.baseline_common_operator_pairs?.mean ?? "—", data.v2.metrics.ps05x_path_common_operator_pairs?.mean ?? "—", data.v2.metrics.ps05x_common_operator_pairs?.mean ?? "—"]]} />
                </div>
              )}
              {data.v2.campaign && <div className="mt-3"><div className="label">Campaign DNA</div><KV rows={Object.entries(data.v2.campaign).map(([k, v]: [string, any]) => [k.replace(/_/g, " "), `${v.mean ?? "—"} (n=${v.n ?? "—"})`] as [string, React.ReactNode])} /></div>}
              {(data.v2.errors || []).length > 0 && <p className="warn mt-2 text-xs">{data.v2.errors.length} case(s) failed to score and are listed as errors in the results file.</p>}
            </Section>
          )}
          <Limitations items={["Synthetic benchmark only; metrics describe behaviour on generated cases with planted decoys.", "Held-out seeds (700+) and the held-out typology were never used while developing the algorithm."]} /></div>}
      </State>
    </Shell>
  );
}

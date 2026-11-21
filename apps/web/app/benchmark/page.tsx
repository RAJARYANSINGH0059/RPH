"use client";

import Shell from "@/components/Shell";
import { KV, Limitations, Section, State, useApi } from "@/components/ui";

export default function Page() {
  const { data, error, reload } = useApi<any>("/benchmark/results");
  return (
    <Shell title="Benchmark Centre" subtitle="How PS05-X is measured: four configurations on identical synthetic cases scored against sealed truth, with seeds, held-out families and confidence intervals. F1 is not accuracy and no real-world transfer is claimed." pageKey="benchmark">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <div className="space-y-3">
          <Section title="Methodology"><KV rows={[["Configurations", "A rules only · B financial graph · C combined without safeguards · D PS05-X full"], ["Scoring", "every case is generated, sealed, ingested through the public upload pipeline, then scored"], ["Seeds", `smoke ${data.smoke?.summary?.seeds ?? "—"} · held-out ${data.heldout?.summary?.seeds ?? "—"}`], ["Generator / path algorithm", `${data.smoke?.summary?.generator_version ?? "—"} / ${data.smoke?.summary?.path_algorithm_version ?? "—"}`], ["Reproduce", "python tests/benchmark/run_benchmark.py --seeds 4 --size small"], ["Commit", data.commit || "—"]]} /></Section>
          <Limitations items={["Synthetic benchmark only; metrics describe behaviour on generated cases with planted decoys.", "Held-out seeds (700+) and the held-out typology were never used while developing the algorithm."]} /></div>}
      </State>
    </Shell>
  );
}

"use client";

import Link from "next/link";
import Shell from "@/components/Shell";
import { Section, State, Table, useApi } from "@/components/ui";

const DIFF: Record<string, string> = { clean: "complete fields, one layout, no decoys", messy: "missing names, ambiguous dates, a duplicate row, a balance mismatch, a decoy domain on a shared CDN", high_noise: "more of everything plus OCR substitutions and similar names", adversarial: "stale conflicting DNS, more decoys designed to look connected", incomplete_evidence: "messy + a statement without a balance column and a missing statement period", identifier_rotation: "messy + a second campaign domain and rotated payment identifiers", temporal_conflict: "adversarial + planted stale/conflicting observations and ambiguous dates" };
const SC: Record<string, string> = { desert_mirage: "three complaints, QR + UPI link, rotated domains, commingled intermediary with a missing month, shared-CDN decoy, stale DNS, OCR-corrupted VPA, message export, simulated hold and preservation response", identifier_rotation_campaign: "same pattern, new domain and VPAs", commingled_funds: "salary credit lands before the onward transfer", benign_lookalike: "a legitimate shop with many small credits on shared hosting — no fraud", compromised_account: "holder reports the account as operated without knowledge" };
export default function Page() {
  const { data, error, reload } = useApi<any>("/synthetic/options");
  return (
    <Shell title="Adversarial Case Simulator" subtitle="Difficulty profiles and decoy families available in the Synthetic Case Factory. Each profile plants specific chaos the verification layer must survive; the planted events are recorded in the sealed truth for scoring." pageKey="factory">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <div className="space-y-3"><Section title="Difficulty profiles"><Table cols={["Profile", "What it plants"]} rows={data.difficulties.map((d: string) => [<span key="d" className="mono">{d}</span>, DIFF[d] || ""])} /></Section>
          <Section title="Next-wave scenario families"><Table cols={["Scenario", "Design"]} rows={data.scenario_types.filter((s: string) => SC[s]).map((s: string) => [<span key="s" className="mono">{s}</span>, SC[s]])} /></Section>
          <div className="card flex items-center justify-between text-sm"><span>Generator v{data.generator_version}. Same seed ⇒ byte-identical files.</span><Link href="/factory" className="btn">Open the factory</Link></div></div>}
      </State>
    </Shell>
  );
}

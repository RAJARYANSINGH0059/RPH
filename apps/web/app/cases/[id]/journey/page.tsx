"use client";

import ListPage from "@/components/ListPage";
import { Chip, Limitations, Locator, Section, State, Table, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Victim Journey Reconstruction" subtitle="The complainant's reported experience, checked against recorded transactions. Everything in a complaint is reported; checks show where supplied statements corroborate or conflict. Reported dates are never silently replaced." pageKey="journey">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/twin/journey`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          {data.journeys.map((j: any) => (
            <Section key={j.complaint_evidence_id} title={<span className="flex items-center gap-2"><Chip v="reported" /> {j.file}</span>} hint={j.note}>
              <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr]">
                <div><div className="label">Excerpt</div><p className="whitespace-pre-wrap rounded-lg bg-panel p-3 text-xs">{j.excerpt}</p><div className="mt-1"><Locator caseId={id} file={j.file} sha256={j.sha256} locator={j.locator} evidenceId={j.complaint_evidence_id} /> · extraction {j.extraction}</div></div>
                <div><div className="label">Consistency checks</div><Table dense cols={["Claim", "Status", "Transactions"]} rows={j.consistency_checks.map((c: any) => [c.claim, <Chip key="s" v={c.status === "corroborated_by_statement" ? "corroborated" : c.status === "conflicting_amount" ? "contradicted" : "unresolved"} title={c.status} />, <span key="t" className="text-xs">{c.transaction_ids.length}{c.note ? ` · ${c.note}` : ""}</span>])} empty="No checkable amounts, UTRs or payees in the text." /></div>
              </div>
            </Section>
          ))}
          {data.journeys.length === 0 && <div className="card text-sm muted">No complaint document in this case. Upload a complaint PDF/TXT to reconstruct the reported journey.</div>}
          <Section title={`Journey events (${data.events.length})`}><Table dense cols={["When", "Type", "Label", "Class", "Reported by"]} rows={data.events.slice(0, 200).map((e: any) => [<span key="w" className="text-xs">{e.event_time?.slice(0, 16) || "unknown"}</span>, <span key="t" className="mono text-xs">{e.event_type}</span>, e.label, <Chip key="c" v={e.evidence_class} />, e.reported_by || "—"])} /></Section>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

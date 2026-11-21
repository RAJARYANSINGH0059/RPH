"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { Chip, KV, Limitations, Section, State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  return <ListPage title="Evidence Preservation Priority" subtitle="Event clock and preservation queue. A deadline appears only when the request carries a verified retention policy source; otherwise RETENTION NOT VERIFIED. No universal 24/72-hour deadline is asserted and nothing is dispatched by the system." pageKey="preservation">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/preservation`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <Section title="Event clock" hint={data.clock.note}><KV rows={[["First transaction", <When key="a" v={data.clock.first_transaction} />], ["First report ingested", <When key="b" v={data.clock.first_report_ingested} />], ["First evidence ingested", <When key="c" v={data.clock.first_evidence_ingested} />], ["Elapsed since first transaction", data.clock.elapsed_since_first_transaction_hours !== null ? `${data.clock.elapsed_since_first_transaction_hours} h` : "—"]]} /></Section>
          <Section title={`Preservation queue (${data.queue.length})`} hint="Sorted: verified deadlines first, then by volatility of the record class.">
            <Table dense cols={["Request", "Custodian", "Volatility", "Retention", "Urgency", "Status", "Explanation"]} rows={data.queue.map((q: any) => [<span key="t" className="font-medium">{q.title}{q.is_simulated && <span className="badge simulated ml-1">simulated</span>}</span>, q.organisation_type, q.volatility, <span key="r" className="mono text-xs">{q.retention.display}</span>, <Chip key="u" v={q.urgency === "verified_deadline" ? "contradicted" : "unresolved"} title={q.urgency} />, q.status, <span key="e" className="text-xs muted">{q.explanation}</span>])} empty={<span>No requests yet. <Link href={`/cases/${id}/ivoi`} className="underline">Create drafts from the ranked suggestions</Link>.</span>} />
          </Section>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

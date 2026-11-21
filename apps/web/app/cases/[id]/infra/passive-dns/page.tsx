"use client";

import ListPage from "@/components/ListPage";
import { Chip, Limitations, Section, State, Table, useApi } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title="Historical DNS / Passive DNS" subtitle="What is historical (dated observation supplied in a report), what is current-only (a lookup made now), and what is unknown for the event period. Current DNS never becomes historical evidence." pageKey="pdns">
      {(id) => <Body id={id} />}
    </ListPage>
  );
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/coverage`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <Section title={`Domains (${data.infrastructure.length})`} hint="State per domain relative to the transaction window (±30 days).">
            <Table dense cols={["Domain", "State", "Observations", "Window", "Note"]} rows={data.infrastructure.map((i: any) => [<span key="d" className="mono">{i.subject}</span>, <Chip key="s" v={i.state} />, <ul key="o" className="text-xs">{i.observations.map((o: any, k: number) => <li key={k}>{o.kind === "CURRENT_ONLY" ? "current lookup" : "dated observation"} · {o.observed_at?.slice(0, 10) || "undated"} → {o.ip} <Chip v={o.evidence_level} /></li>)}</ul>, <span key="w" className="text-xs">{i.transaction_window ? `${i.transaction_window[0]?.slice(0, 10)} → ${i.transaction_window[1]?.slice(0, 10)}` : "—"}</span>, <span key="n" className="text-xs muted">{i.note || ""}</span>])} empty="No infrastructure observations." />
          </Section>
          <Limitations items={["No passive-DNS provider is configured: historical observations come only from supplied reports.", "A current lookup cannot support a claim about an earlier period."]} />
        </div>
      )}
    </State>
  );
}

"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Operation Timeline' subtitle='Chronological twin events across all layers. Order is chronology only; it is never treated as causation. Undated events are listed last.' pageKey='op-timeline'>
      {(id) => <ApiTable title='Operation Timeline' hint='' path={`/cases/${id}/twin`} pick={(d) => d.events} empty='No events.' raw={false} limitations={(d) => d.limitations} cols={[
        { h: "Event time", cell: (e) => <span className="text-xs">{e.event_time ? e.event_time.slice(0, 19).replace("T", " ") : "unknown"}</span> },
        { h: "Precision", cell: (e) => e.time_precision },
        { h: "Layer", cell: (e) => e.layer.replace(/_/g, " ") },
        { h: "Type", cell: (e) => <span className="mono text-xs">{e.event_type}</span> },
        { h: "Label", cell: (e) => e.label },
        { h: "Class", cell: (e) => <Chip v={e.evidence_class} /> },
        { h: "Observed / ingested", cell: (e) => <span className="text-xs"><When v={e.observed_at} /> / <When v={e.ingested_at} /></span> },
      ]} />}
    </ListPage>
  );
}

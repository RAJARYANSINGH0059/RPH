"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Money } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Investigative Chokepoint Map' subtitle='Which observed intermediaries connect the largest number of independently evidenced victim-origin paths. A structural aid over observed/corroborated edges only: centrality is not culpability and no action is recommended.' pageKey='chokepoints'>
      {(id) => <ApiTable title='Investigative Chokepoint Map' hint='' path={`/cases/${id}/chokepoints`} pick={(d) => d.rows} empty='No money edges yet.' raw={false} limitations={(d) => d.limitations} cols={[
        { h: "Account", cell: (r) => <span className="mono">{r.account}</span> },
        { h: "Role", cell: (r) => r.role },
        { h: "Paths through", cell: (r) => r.supported_paths_through },
        { h: "Distinct amount through", cell: (r) => <Money v={r.distinct_amount_through_minor} /> },
        { h: "Betweenness", cell: (r) => r.betweenness },
        { h: "Paths cut if records missing", cell: (r) => r.paths_disconnected_if_records_missing },
        { h: "Uncertain-time edges in", cell: (r) => r.uncertain_time_edges_in },
        { h: "Explanation", cell: (r) => <span className="text-xs muted">{r.explanation}</span> },
      ]} />}
    </ListPage>
  );
}

"use client";

import ListPage, { ApiTable } from "@/components/ListPage";

export default function Page() {
  return (
    <ListPage title='Investigation Completeness' subtitle='An interpretable checklist with component contributions. It describes evidence completeness; it is not a probability of guilt, conviction or a solved case.' pageKey='completeness'>
      {(id) => <ApiTable title='Investigation Completeness' hint='Score = sum of satisfied component weights.' path={`/cases/${id}/completeness`} pick={(d) => d.items} empty='Nothing here yet.' raw={true} limitations={(d) => d.limitations} cols={[
        { h: "Component", cell: (i) => i.label },
        { h: "Open items", cell: (i) => i.open },
        { h: "Weight", cell: (i) => i.weight },
        { h: "Contribution", cell: (i) => <span className={i.contribution ? "ok" : "warn"}>{i.contribution}</span> },
        { h: "Detail", cell: (i) => <span className="text-xs muted">{Array.isArray(i.detail) ? i.detail.join(", ") : ""}</span> },
      ]} />}
    </ListPage>
  );
}

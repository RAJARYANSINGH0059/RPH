"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Entity and Identifier Resolution' subtitle='Aliases and bridges: SAME_ACCOUNT_IDENTIFIER (reference+amount in two statements), SAME_IDENTIFIER (document ↔ statement), SIMILAR_NAME (never merged). Entities are kept separate; aliasing is a derived edge with its evidence.' pageKey='entities'>
      {(id) => <ApiTable title='Entity and Identifier Resolution' hint='' path={`/cases/${id}/graph`} pick={(d) => { const n = Object.fromEntries(d.nodes.map((x: any) => [x.id, x])); return d.edges.filter((e: any) => ["SAME_ACCOUNT_IDENTIFIER", "SAME_IDENTIFIER", "SIMILAR_NAME", "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION"].includes(e.type)).map((e: any) => ({ ...e, attributes: { ...e.attributes, src_label: n[e.source]?.label, dst_label: n[e.target]?.label } })); }} empty='No alias or bridge edges yet.' raw={false} limitations={undefined} cols={[
        { h: "Relationship", cell: (e) => <span className="mono">{e.type}</span> },
        { h: "A ↔ B", cell: (e) => <span className="mono">{e.attributes.src_label} ↔ {e.attributes.dst_label}</span> },
        { h: "Level", cell: (e) => <Chip v={e.evidence_level} /> },
        { h: "Method", cell: (e) => <span className="text-xs">{e.attributes.matching_method || "—"}{e.attributes.similarity ? ` (${e.attributes.similarity})` : ""}</span> },
        { h: "Review", cell: (e) => e.review_status.replace(/_/g, " ") },
        { h: "Limitations", cell: (e) => <span className="text-xs warn">{e.limitations.join(", ")}</span> },
      ]} />}
    </ListPage>
  );
}

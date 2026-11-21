"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='DNS Observations' subtitle='Each resolution carries its observation time and validity window. A mapping is valid only at its observation time; stale ones are flagged.' pageKey='dns'>
      {(id) => <ApiTable title='DNS Observations' hint='' path={`/cases/${id}/graph`} pick={(d) => { const n = Object.fromEntries(d.nodes.map((x: any) => [x.id, x])); return d.edges.filter((e: any) => e.type === "RESOLVES_TO").map((e: any) => ({ ...e, attributes: { ...e.attributes, domain_label: n[e.source]?.label, ip_label: n[e.target]?.label } })); }} empty='No DNS observations.' raw={false} limitations={undefined} cols={[
        { h: "Domain → IP", cell: (e) => <span className="mono">{e.attributes.domain_label} → {e.attributes.ip_label}</span> },
        { h: "Level", cell: (e) => <Chip v={e.evidence_level} /> },
        { h: "Observed", cell: (e) => <When v={e.observed_at} /> },
        { h: "Valid from → to", cell: (e) => <span className="text-xs"><When v={e.valid_from} /> → <When v={e.valid_to} /></span> },
        { h: "TTL / resolver", cell: (e) => `${e.attributes.ttl ?? "—"} / ${e.attributes.resolver ?? "—"}` },
        { h: "Limitations", cell: (e) => <span className="text-xs warn">{e.limitations.join(", ")}</span> },
      ]} />}
    </ListPage>
  );
}

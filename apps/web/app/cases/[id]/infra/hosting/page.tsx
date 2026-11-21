"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Hosting and Registrar Intelligence' subtitle='Providers observed hosting case IPs, and registration observations. Use of a provider is not control of it.' pageKey='hosting'>
      {(id) => <ApiTable title='Hosting and Registrar Intelligence' hint='' path={`/cases/${id}/graph`} pick={(d) => { const n = Object.fromEntries(d.nodes.map((x: any) => [x.id, x])); return d.edges.filter((e: any) => ["HOSTED_ON", "REGISTRATION_OBSERVED", "SHARED_INFRASTRUCTURE"].includes(e.type)).map((e: any) => ({ ...e, attributes: { ...e.attributes, src_label: n[e.source]?.label, dst_label: n[e.target]?.label } })); }} empty='No hosting or registrar observations.' raw={false} limitations={undefined} cols={[
        { h: "Relationship", cell: (e) => <span className="mono">{e.type}</span> },
        { h: "From → To", cell: (e) => <span className="mono">{e.attributes.src_label} → {e.attributes.dst_label}</span> },
        { h: "Level", cell: (e) => <Chip v={e.evidence_level} /> },
        { h: "Observed", cell: (e) => <When v={e.observed_at} /> },
        { h: "Provider / registrar", cell: (e) => e.attributes.provider || e.attributes.registrar || "—" },
        { h: "Limitations", cell: (e) => <span className="text-xs warn">{e.limitations.slice(0, 3).join(", ")}</span> },
      ]} />}
    </ListPage>
  );
}

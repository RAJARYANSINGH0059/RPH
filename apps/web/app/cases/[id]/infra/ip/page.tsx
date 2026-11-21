"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='IP and ASN Intelligence' subtitle="Addresses with their classification (documentation / private / public), hosting ASN and multi-tenancy. An IP alone does not identify a subscriber or a person's location." pageKey='ip'>
      {(id) => <ApiTable title='IP and ASN Intelligence' hint='' path={`/cases/${id}/graph`} pick={(d) => d.nodes.filter((n: any) => ["ip", "asn"].includes(n.type))} empty='No IP or ASN entities.' raw={false} limitations={undefined} cols={[
        { h: "Type", cell: (n) => <Chip v="observed" title={n.type} /> },
        { h: "Value", cell: (n) => <span className="mono">{n.label}</span> },
        { h: "Classification", cell: (n) => n.attributes.classification || (n.type === "asn" ? `ASN ${n.attributes.asn ?? ""}` : "—") },
        { h: "Provider", cell: (n) => n.attributes.provider || "—" },
        { h: "Multi-tenant / CDN", cell: (n) => n.attributes.is_cdn === undefined ? "—" : n.attributes.is_cdn ? "yes" : "no" },
      ]} />}
    </ListPage>
  );
}

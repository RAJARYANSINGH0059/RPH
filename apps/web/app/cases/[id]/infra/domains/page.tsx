"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Domain Intelligence' subtitle='Domains and URLs named in documents or observed in technical reports. Mention is not involvement; registration data is current-only unless dated.' pageKey='domains'>
      {(id) => <ApiTable title='Domain Intelligence' hint='Click a value in the Graph Explorer for its relationships and counter-evidence.' path={`/cases/${id}/graph`} pick={(d) => d.nodes.filter((n: any) => ["domain", "url"].includes(n.type))} empty='No domains or URLs in this case.' raw={false} limitations={undefined} cols={[
        { h: "Type", cell: (n) => <Chip v={n.type === "domain" ? "observed" : "extracted"} title={n.type} /> },
        { h: "Value", cell: (n) => <span className="mono">{n.label}</span> },
        { h: "Registrar", cell: (n) => n.attributes.registrar || "—" },
        { h: "Created (RDAP)", cell: (n) => n.attributes.created || "—" },
        { h: "Mentioned in", cell: (n) => n.attributes.mentioned_in || "—" },
      ]} />}
    </ListPage>
  );
}

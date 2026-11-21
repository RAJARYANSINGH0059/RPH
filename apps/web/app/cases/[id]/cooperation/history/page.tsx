"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Cooperation Package History' subtitle='Packs created for this case, their endorsement status and exports. A pack is a manual handoff bundle; nothing is transmitted to another agency.' pageKey='pack-history'>
      {(id) => <ApiTable title='Cooperation Package History' hint='' path={`/cases/${id}/cooperation`} pick={(d) => Array.isArray(d) ? d : d.packs || []} empty='No cooperation packs yet.' raw={false} limitations={undefined} cols={[
        { h: "Created", cell: (p) => <When v={p.created_at} /> },
        { h: "Status", cell: (p) => <Chip v={p.status === "export_ready" ? "verified" : p.status === "supervisor_endorsed" ? "corroborated" : "candidate"} title={p.status} /> },
        { h: "Requesting officer / agency", cell: (p) => `${p.fields?.requesting_officer || "—"} / ${p.fields?.requesting_agency || "—"}` },
        { h: "Attachments", cell: (p) => (p.attachment_file_ids || []).length },
        { h: "Endorsed by", cell: (p) => p.endorsed_by?.slice(0, 8) || "—" },
        { h: "Exported", cell: (p) => <When v={p.exported_at} /> },
      ]} />}
    </ListPage>
  );
}

"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Audit and Activity History' subtitle='Append-only case audit log: uploads, parsing, reviews, hypotheses, exports, requests and simulations, with actor and time.' pageKey='audit'>
      {(id) => <ApiTable title='Audit and Activity History' hint='' path={`/cases/${id}/audit`} pick={(d) => d} empty='No audit events.' raw={false} limitations={undefined} cols={[
        { h: "When", cell: (a) => <When v={a.created_at} /> },
        { h: "Action", cell: (a) => <span className="mono">{a.action}</span> },
        { h: "Actor", cell: (a) => <span className="mono text-xs">{a.actor_id?.slice(0, 8) || "system"}</span> },
        { h: "Target", cell: (a) => <span className="text-xs">{a.target_type || ""} {a.target_id?.slice(0, 8) || ""}</span> },
        { h: "Detail", cell: (a) => <span className="text-xs muted">{JSON.stringify(a.detail).slice(0, 160)}</span> },
      ]} />}
    </ListPage>
  );
}

"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Evidence-Linked Findings' subtitle='Every relationship in the report with its level, review status, validity window, method and cited sources.' pageKey='findings'>
      {(id) => <ApiTable title='Evidence-Linked Findings' hint='' path={`/cases/${id}/report.json`} pick={(d) => d.relationships || []} empty='No findings yet.' raw={false} limitations={undefined} cols={[
        { h: "Type", cell: (r) => <span className="mono">{r.type}</span> },
        { h: "Source → Target", cell: (r) => <span className="text-xs">{r.source} <span className="muted">({r.source_type})</span> → {r.target} <span className="muted">({r.target_type})</span></span> },
        { h: "Level", cell: (r) => <Chip v={r.evidence_level} /> },
        { h: "Review", cell: (r) => r.review_status.replace(/_/g, " ") },
        { h: "Valid / observed", cell: (r) => <span className="text-xs">{r.valid_from?.slice(0, 10) || "—"} → {r.valid_to?.slice(0, 10) || "—"} · obs {r.observed_at?.slice(0, 10) || "—"}</span> },
        { h: "Method", cell: (r) => <span className="mono text-xs">{r.method}</span> },
        { h: "Sources", cell: (r) => <span className="text-xs">{r.sources.length}</span> },
      ]} />}
    </ListPage>
  );
}

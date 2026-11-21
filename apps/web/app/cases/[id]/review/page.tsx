"use client";

import { useState } from "react";
import ListPage from "@/components/ListPage";
import EdgePanel from "@/components/EdgePanel";
import { Chip, Section, State, Table, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Relationship Review" subtitle="Candidate, stale and contradicted links awaiting a human decision. Analysts can reject or ask for more evidence; promoting a weak link to supported needs a supervisor." pageKey="review">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/graph`);
  const [edge, setEdge] = useState<string | null>(null);
  const n = data ? Object.fromEntries(data.nodes.map((x: any) => [x.id, x])) : {};
  const rows = data ? data.edges.filter((e: any) => ["candidate", "stale", "contradicted", "insufficient"].includes(e.evidence_level) && e.review_status === "unreviewed") : [];
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && <div className="wb-grid"><Section title={`Awaiting review (${rows.length})`}><Table dense cols={["Type", "From → To", "Level", "Limitations", ""]} rows={rows.map((e: any) => [<span key="t" className="mono">{e.type}</span>, <span key="f">{n[e.source]?.label} → {n[e.target]?.label}</span>, <Chip key="l" v={e.evidence_level} />, <span key="x" className="text-xs warn">{e.limitations.slice(0, 2).join(", ")}</span>, <button key="b" className="btn-secondary !py-1" onClick={() => setEdge(e.id)}>Review</button>])} empty="Nothing awaiting review." /></Section>
        <div>{edge ? <EdgePanel caseId={id} edgeId={edge} onClose={() => setEdge(null)} onReviewed={reload} /> : <div className="card text-sm muted">Pick a relationship to see its evidence, counter-evidence and record a decision.</div>}</div></div>}
    </State>
  );
}

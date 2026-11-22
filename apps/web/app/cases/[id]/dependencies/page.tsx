"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { Chip, Limitations, Section, State, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Missing Evidence Dependency Map" subtitle="Investigative questions → required records → what is available or missing → the findings they affect. A requested record could establish the listed points; it is never guaranteed to resolve a hypothesis." pageKey="dependencies">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/dependencies`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3"><div className="metric"><div className="label mb-0">Open questions</div><div className="metric-value mt-2">{data.questions.length}</div></div><div className="metric"><div className="label mb-0">Missing records</div><div className="metric-value mt-2">{data.missing.length}</div></div><div className="metric"><div className="label mb-0">Available</div><div className="metric-value mt-2">{data.available.length}</div></div></div>
          {data.questions.map((q: any) => { const reqs = data.requirements.filter((r: any) => r.question_id === q.id); return (
            <Section key={q.id} title={<span className="flex items-center gap-2"><Chip v={q.priority} /> {q.question}</span>} hint={`Related: ${q.related_entities.join(", ") || "—"} · impact: ${Object.entries(q.impact).map(([k, v]: [any, any]) => `${k} ${Array.isArray(v) ? v.join(",") : v}`).join("; ")}`}>
              <div className="grid gap-3 lg:grid-cols-2 text-xs"><div><div className="label">Competing hypotheses</div><ul className="list-disc pl-4">{q.competing_hypotheses.map((h: string) => <li key={h}>{h}</li>)}</ul></div>
              <div><div className="label">Required evidence</div><ul className="space-y-1">{reqs.map((r: any) => <li key={r.id} className="inset p-2"><div className="flex items-center justify-between gap-2"><span className="font-medium">{r.evidence}</span><Chip v={r.status === "identified" ? "unresolved" : r.status === "received" || r.status === "reviewed" ? "corroborated" : "derived"} title={r.status} /></div><div className="muted">{r.organisation_type} · {r.target_entity} · {r.window ? `${r.window[0]?.slice(0, 10)} → ${r.window[1]?.slice(0, 10)}` : "no period"}</div><div>Could resolve: {r.could_resolve.join("; ")}</div><div className="muted">Would not establish: {r.would_not_establish.join("; ")}</div></li>)}</ul></div></div>
            </Section>); })}
          {data.questions.length === 0 && <div className="card text-sm muted">No open questions: every path ends at a statement in the case and no candidate relationship awaits review.</div>}
          <div className="card flex items-center justify-between text-sm"><span>What remains unproven: {data.what_remains_unproven.length} question(s).</span><Link href={`/cases/${id}/ivoi`} className="btn">Rank the records to request</Link></div>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

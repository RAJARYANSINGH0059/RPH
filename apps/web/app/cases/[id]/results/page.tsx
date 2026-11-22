"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { Chip, KV, Limitations, Section, State, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Investigation Results" subtitle="Findings, paths, counter-evidence, reconciliation and open questions on one page, each pointing to the module that produced it. Results are content, not another menu." pageKey="case-results">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const rep = useApi<any>(`/cases/${id}/report.json`);
  const comp = useApi<any>(`/cases/${id}/completeness`);
  const cov = useApi<any>(`/cases/${id}/coverage`);
  const adv = useApi<any>(`/cases/${id}/adversary?limit=200`);
  // Canonical counts, so this page cannot disagree with the overview, the graph or the exports.
  const cnt = useApi<any>(`/cases/${id}/counts`);
  return (
    <State loading={rep.loading} error={rep.error} onRetry={rep.reload}>
      {rep.data && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="metric" title={cnt.data?.definitions?.["paths.total"]}><div className="label mb-0">Paths</div><div className="metric-value mt-2">{cnt.data ? cnt.data.paths.total : "…"}</div><div className="mt-1 text-xs muted">{cnt.data ? `${cnt.data.paths.unresolved} unresolved` : ""}</div><Link href={`/cases/${id}/money-trail`} className="text-xs text-accent-deep underline">money trail</Link></div>
            <div className="metric" title={cnt.data?.definitions?.["relationships.total"]}><div className="label mb-0">Relationships</div><div className="metric-value mt-2">{cnt.data ? cnt.data.relationships.total : "…"}</div><div className="mt-1 text-xs muted">{cnt.data ? `${cnt.data.relationships.awaiting_review} awaiting review` : ""}</div><Link href={`/cases/${id}/findings`} className="text-xs text-accent-deep underline">evidence-linked findings</Link></div>
            <div className="metric"><div className="label mb-0">Completeness</div><div className="metric-value mt-2">{comp.data ? `${comp.data.score.percent}%` : "…"}</div><Link href={`/cases/${id}/completeness`} className="text-xs text-accent-deep underline">checklist</Link></div>
            <div className="card"><div className="label mb-0">Challenge states</div><div className="text-xs mt-1">{adv.data ? Object.entries(adv.data.by_state).map(([k, v]: [any, any]) => <span key={k} className="mr-2"><Chip v={k} /> {String(v)}</span>) : "…"}</div><Link href={`/cases/${id}/counterproof`} className="text-xs text-accent-deep underline">CounterProof</Link></div>
          </div>
          <Section title="Case" hint={rep.data.disclaimer}><KV rows={[["Title", rep.data.case.title], ["Data status", rep.data.case.data_status], ["Live connections", rep.data.case.live_connections], ["Generated", rep.data.generated_at], ["Report version", rep.data.report_version]]} /></Section>
          <div className="grid gap-3 lg:grid-cols-2">
            <Section title="Counter-evidence on file"><ul className="list-disc pl-5 text-xs">{(rep.data.counter_evidence || []).slice(0, 12).map((c: any, i: number) => <li key={i}><span className="mono">{c.kind}</span> ({c.severity}) — {c.description}</li>)}{!(rep.data.counter_evidence || []).length && <li className="muted">None.</li>}</ul></Section>
            <Section title="Coverage warnings (never zero activity)"><ul className="list-disc pl-5 text-xs">{(cov.data?.negative_claim_warnings || []).map((w: any) => <li key={w.path_index}>{w.warning} {w.needed}</li>)}{cov.data && !cov.data.negative_claim_warnings.length && <li className="muted">All paths end at a statement in the case.</li>}</ul></Section>
          </div>
          <Section title="Open questions and gaps"><ul className="list-disc pl-5 text-xs">{(rep.data.gaps || []).slice(0, 20).map((g: any, i: number) => <li key={i}>{g.file}: {g.warning}</li>)}</ul></Section>
          <Limitations items={[rep.data.disclaimer]} />
        </div>
      )}
    </State>
  );
}

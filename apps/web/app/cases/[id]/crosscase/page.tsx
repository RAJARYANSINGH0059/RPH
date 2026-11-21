"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CorrelationView } from "@/components/CrossCase";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

export default function RelatedCasesPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [rel, setRel] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/crosscase/cases/${id}/related`)]).then(([cc, r]: [any, any]) => { setC(cc); setRel(r.related); }).catch((e) => setError(e.message)); }, [id]);
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Related authorised cases" subtitle="Other cases you can access that share an exact identifier with this one. Pick some and correlate for full provenance." pageKey="crosscase" step="graph">
      <State loading={!rel && !error} error={error}>
        {rel && rel.length === 0 && <div className="card border-dashed text-sm muted">No accessible case shares an account, VPA, phone, email, reference, URL or domain with this case. <Link className="text-accent-deep underline" href="/crosscase">Open the cross-case workspace</Link> to correlate any set of cases.</div>}
        {rel && rel.length > 0 && (
          <div className="space-y-4">
            <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {rel.map((r: any) => (
                <li key={r.case_id} className={`card ${picked.includes(r.case_id) ? "ring-2 ring-accent" : ""}`}>
                  <div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="truncate font-semibold">{r.title}</div><div className="text-[11px] muted">{r.is_synthetic ? "synthetic" : "uploaded"} · {r.shared_count} shared identifier{r.shared_count > 1 ? "s" : ""} · {r.strong_identity_matches} strong</div></div><label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={picked.includes(r.case_id)} onChange={() => setPicked(picked.includes(r.case_id) ? picked.filter((x: any) => x !== r.case_id) : [...picked, r.case_id])} /> compare</label></div>
                  <ul className="mt-2 flex flex-wrap gap-1">{r.shared_identifiers.map((s: any) => <li key={s.type + s.value} className="rounded-full bg-panel px-2 py-0.5 text-[11px]"><span className="muted">{s.type}</span> <span className="mono">{s.value}</span></li>)}</ul>
                  <Link href={`/cases/${r.case_id}`} className="mt-2 inline-flex items-center gap-1 text-sm text-accent-deep hover:underline">Open case <I.arrow width={14} height={14} /></Link>
                </li>
              ))}
            </ul>
            {picked.length > 0 ? <CorrelationView caseIds={[id, ...picked]} /> : <div className="callout"><I.link className="shrink-0 text-accent-deep" /><div>Tick “compare” on one or more related cases to run the full correlation with evidence provenance and counter-evidence.</div></div>}
          </div>
        )}
      </State>
    </Shell>
  );
}

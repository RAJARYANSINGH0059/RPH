"use client";

import Link from "next/link";
import { useState } from "react";
import CasePage from "@/components/CasePage";
import { Chip, Limitations, State, Toast, useApi } from "@/components/ui";
import { api } from "@/lib/api";

export default function IvoiPage() {
  return <CasePage title="Next-Best-Evidence / IVOI" subtitle="Which records to request next, ranked by how many open questions they could resolve. The score is a transparent sum of weighted components; it is not a probability of success, an expected recovery amount or a prediction of cooperation." pageKey="ivoi">{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/ivoi`);
  const [msg, setMsg] = useState<string | null>(null);
  async function draft(r: any) {
    setMsg(null);
    try { await api(`/cases/${id}/requests`, { method: "POST", body: JSON.stringify({ title: r.draft.title, catalogue_key: r.catalogue_key, organisation_type: r.organisation_type, target_entity: r.target_entity || "", window_from: r.window?.[0] || null, window_to: r.window?.[1] || null, required_fields: r.required_fields, rationale: r.draft.rationale, could_resolve: r.could_resolve, would_not_establish: r.would_not_establish, ranking: { ...r.components, catalogue_key: r.catalogue_key } }) }); setMsg("Draft request created (not sent). Open Outstanding Evidence Requests to review it."); reload(); }
    catch (e: any) { setMsg(e.message); }
  }
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <Toast msg={msg} onClose={() => setMsg(null)} />
          <div className="card text-xs"><span className="label mb-0">Weights</span> {Object.entries(data.weights).map(([k, v]: [any, any]) => <span key={k} className="mr-3 mono">{k} {String(v)}</span>)}</div>
          {data.ranked.length === 0 && <div className="card text-sm muted">No open questions: nothing to request.</div>}
          <ol className="space-y-3">
            {data.ranked.map((r: any, i: number) => (
              <li key={r.id} className="card">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0"><div className="flex items-center gap-2"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-rail text-xs font-bold text-white">{i + 1}</span><h3 className="font-semibold">{r.evidence}</h3><Chip v={r.priority_label} /></div><div className="mt-1 text-xs muted">{r.organisation_type} custodian · target <span className="mono">{r.target_entity}</span>{r.window?.[0] ? ` · ${r.window[0].slice(0, 10)} → ${r.window[1]?.slice(0, 10)}` : ""} · <span className="mono">{r.catalogue_key}</span></div><p className="mt-1 text-xs"><span className="font-medium">Answers:</span> {r.draft.rationale}</p></div>
                  <div className="flex flex-col items-end gap-1"><div className="num text-2xl font-bold" title="transparent score, not a probability">{r.score_not_probability}</div>{r.status === "identified" ? <button className="btn !py-1" onClick={() => draft(r)}>Create draft request</button> : <Link href={`/cases/${id}/requests`} className="btn-secondary !py-1">Request {r.status}</Link>}</div>
                </div>
                <div className="mt-3 grid gap-3 text-xs md:grid-cols-3">
                  <div><div className="label">Score components</div><ul>{Object.entries(r.components).map(([k, v]: [any, any]) => <li key={k} className="flex justify-between"><span className="muted">{k.replace(/_/g, " ")}</span><span className="num">{String(v)}</span></li>)}</ul></div>
                  <div><div className="label">Could resolve</div><ul className="list-disc pl-4">{r.could_resolve.map((x: string) => <li key={x}>{x}</li>)}</ul><div className="label mt-2">Would not establish</div><ul className="list-disc pl-4">{r.would_not_establish.map((x: string) => <li key={x}>{x}</li>)}</ul></div>
                  <div><div className="label">Scope and authorisation</div><div>{r.data_minimisation}</div><div className="mt-1">Fields: {r.required_fields.join(", ")}</div><div className="mt-1 warn">{r.authorisation_caution}</div><div className="mt-1">Retention: <span className="mono">{r.retention.display || (r.retention.verified ? "verified" : "RETENTION NOT VERIFIED")}</span></div><div className="mt-1 muted">Source: {r.source_ref}</div></div>
                </div>
              </li>
            ))}
          </ol>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

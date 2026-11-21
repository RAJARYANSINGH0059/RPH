"use client";

import { useState } from "react";
import CasePage from "@/components/CasePage";
import { Chip, KV, Limitations, Locator, Section, State, Table, useApi } from "@/components/ui";

export default function LifecyclePage() {
  return <CasePage title="Operation Lifecycle and Dependencies" subtitle="FATF's seven-stage scam-operation lifecycle applied to this case's evidence, with the functions and services that appear to sustain the operation. NOT SUPPLIED means no evidence was supplied, never that a stage did not happen." pageKey="lifecycle" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/lifecycle`);
  const [stage, setStage] = useState<string | null>(null);
  const [show, setShow] = useState<string[]>(["DIRECTLY_OBSERVED", "CORROBORATED", "DERIVED", "CANDIDATE", "CONTRADICTED", "NOT_SUPPLIED", "PARTIAL"]);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="callout text-xs"><span className="font-semibold">Attribution.</span> {data.attribution.framework} — {data.attribution.source}. <a className="underline" href={data.attribution.url} target="_blank" rel="noreferrer">Report</a>. {data.attribution.note}</div>
          <div className="flex flex-wrap gap-1.5 text-xs">{data.states.map((s: string) => <button key={s} className={`chip ${show.includes(s) ? "chip-on" : ""}`} aria-pressed={show.includes(s)} onClick={() => setShow((cur) => cur.includes(s) ? cur.filter((x: any) => x !== s) : [...cur, s])}><Chip v={s} /></button>)}</div>
          <div className="stage-grid">
            {data.stages.map((s: any) => (
              <button key={s.key} onClick={() => setStage(stage === s.key ? null : s.key)} aria-pressed={stage === s.key} className={`card text-left transition hover:-translate-y-0.5 ${stage === s.key ? "ring-2 ring-accent" : ""} ${!show.includes(s.state) ? "opacity-40" : ""}`}>
                <div className="lane-label">{s.group.replace("_", " ")} · {s.key}</div>
                <div className="mt-1 font-semibold leading-tight">{s.label}</div>
                <div className="mt-2"><Chip v={s.state} /></div>
                <div className="mt-2 text-xs muted">{s.evidence_count} evidence item(s){s.missing_evidence.length ? ` · ${s.missing_evidence.length} missing` : ""}</div>
              </button>
            ))}
          </div>
          {stage && (() => { const s = data.stages.find((x: any) => x.key === stage); return (
            <Section title={`${s.key} · ${s.label}`} hint={s.hint}>
              <div className="grid gap-4 lg:grid-cols-3">
                <div className="lg:col-span-2"><div className="label">Supporting events ({s.events.length})</div><ul className="max-h-72 space-y-1 overflow-auto text-xs">{s.events.map((e: any) => <li key={e.evidence_id} className="flex flex-wrap items-center gap-2"><Chip v={e.class} /><span>{e.label}</span><Locator caseId={id} file={e.file} sha256={e.sha256} locator={e.locator} evidenceId={e.evidence_id} /></li>)}{s.events.length === 0 && <li className="muted">No evidence supplied for this stage.</li>}</ul></div>
                <div><div className="label">Missing evidence</div><ul className="list-disc pl-4 text-xs">{s.missing_evidence.map((m: string) => <li key={m}>{m}</li>)}{!s.missing_evidence.length && <li className="muted">—</li>}</ul><div className="label mt-3">Unresolved hypotheses</div><ul className="list-disc pl-4 text-xs">{s.unresolved_hypotheses.map((m: string) => <li key={m}>{m}</li>)}{!s.unresolved_hypotheses.length && <li className="muted">—</li>}</ul></div>
              </div>
            </Section>); })()}
          <Section title={`Functional dependencies (${data.dependencies.length})`} hint="Use of a service is not control of it. 'Potentially high leverage' is a review hypothesis with its evidence stated.">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {data.dependencies.map((d: any, i: number) => (
                <div key={i} className="inset p-3 text-sm">
                  <div className="flex items-start justify-between gap-2"><div className="font-semibold">{d.role}</div><Chip v={d.leverage === "POTENTIALLY_HIGH_LEVERAGE_REQUIRES_REVIEW" ? "candidate" : "unresolved"} title={d.leverage} /></div>
                  <div className="mt-1 text-xs muted"><span className="mono">{d.dependency_class}</span> · stages {d.stages.join(", ")} · {d.status.replace(/_/g, " ").toLowerCase()}</div>
                  <KV className="mt-2 text-xs" rows={[["Provider / account", <span key="p" className="mono">{d.provider}</span>], ["Repeat use", String(d.repeat_use)], ["Leverage", d.leverage.replace(/_/g, " ").toLowerCase()], ["Benign alternative", d.benign_alternative], ["Replaceability", d.replaceability], ["Known unknowns", (d.known_unknowns || []).join("; ") || "—"], ["Authorised next step", d.authorised_next_step]]} />
                  {d.leverage_reason && <p className="mt-2 text-xs warn">{d.leverage_reason}</p>}
                </div>
              ))}
            </div>
          </Section>
          <Section title="Evidence gaps by stage"><Table dense cols={["Stage", "State", "Missing"]} rows={data.evidence_gaps.map((g: any) => [`${g.stage} ${g.label}`, <Chip key="s" v={g.state} />, g.missing.join("; ")])} empty="No gaps." /></Section>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

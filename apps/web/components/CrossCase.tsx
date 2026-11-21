"use client";

import Link from "next/link";
import { useState } from "react";
import { Copyable, LevelBadge } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, paise } from "@/lib/api";

const CLASS_HELP: Record<string, string> = {
  corroborated: "Same account/VPA/phone/email in both cases and a transaction with the same reference and amount.",
  exact: "The same normalised identifier appears in both cases.",
  derived: "A transfer with the same reference and amount appears in both cases within 72 hours.",
  candidate: "Only a shared IP/host or a time-inconsistent bridge; needs an independent identifier bridge.",
  stale: "The supporting infrastructure observation is outside the event window in at least one case.",
};

export function CorrelationView({ caseIds, onResult }: { caseIds: string[]; onResult?: (r: any) => void }) {
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  async function run() {
    setBusy(true); setError(null);
    try { const r = await api("/crosscase/correlate", { method: "POST", body: JSON.stringify({ case_ids: caseIds }) }); setRes(r); onResult?.(r); }
    catch (e: any) { setError(e.status === 404 ? "One or more selected cases are not accessible to you." : e.message); } finally { setBusy(false); }
  }
  const title = (id: string) => res?.cases.find((c: any) => c.id === id)?.title || id.slice(0, 8);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button className="btn" onClick={run} disabled={busy || caseIds.length < 2}>{busy ? "Correlating…" : <><I.link /> Correlate {caseIds.length} cases</>}</button>
        {res && <span className="text-xs muted">algorithm v{res.algorithm_version} · fingerprint <span className="mono">{res.fingerprint}</span> · {fmtTime(res.generated_at)}</span>}
      </div>
      {error && <div className="card border-danger/30 bg-danger-soft text-sm text-danger" role="alert">{error}</div>}
      {res && (
        <>
          <div className="grid gap-2 sm:grid-cols-5">{["corroborated", "exact", "derived", "candidate", "stale"].map((k) => <div key={k} className="card p-3"><LevelBadge level={k} /><div className="num mt-1 text-2xl font-bold">{res.summary[k] || 0}</div><div className="text-[11px] muted">{CLASS_HELP[k]}</div></div>)}</div>
          <div className="callout"><I.shield className="shrink-0 text-accent-deep" /><div>{res.notes.join(" ")}</div></div>
          <div className="card p-0">
            <div className="px-4 py-3"><h2 className="section-title">Links across cases ({res.links.length})</h2><p className="text-xs muted">Click a row for provenance: source case, file hash, locator, method and counter-evidence.</p></div>
            {res.links.length === 0 ? <div className="px-4 pb-4 text-sm muted">No exact identifier, reference bridge or shared infrastructure found between these cases.</div> : (
              <div className="max-h-[520px] overflow-auto"><table className="data"><thead><tr><th>Class</th><th>Kind</th><th>Value</th><th>Cases</th><th>Why</th></tr></thead>
                <tbody>{res.links.map((l: any, i: number) => {
                  const key = `${l.kind}-${i}`;
                  const value = l.value || l.reference || l.ip;
                  return (
                    <>
                      <tr key={key} className="cursor-pointer" tabIndex={0} onClick={() => setOpen(open === key ? null : key)} onKeyDown={(k) => k.key === "Enter" && setOpen(open === key ? null : key)} aria-expanded={open === key}>
                        <td><LevelBadge level={l.match_class} /></td>
                        <td className="text-xs">{l.kind.replace(/_/g, " ")}{l.entity_type ? ` · ${l.entity_type}` : ""}</td>
                        <td className="mono text-xs">{value}{l.amount_minor !== undefined && <span className="muted"> · {paise(l.amount_minor)}</span>}</td>
                        <td className="text-xs">{l.cases.map((c: string) => <div key={c}><Link className="text-accent-deep hover:underline" href={`/cases/${c}`} onClick={(e) => e.stopPropagation()}>{title(c)}</Link></div>)}</td>
                        <td className="text-xs muted">{l.kind === "shared_infrastructure" ? (l.same_domain_in_both ? "same domain observed on this IP in both cases" : "different domains share one IP") : l.kind === "transaction_bridge" ? `same reference + amount${l.time_consistent === false ? ", times inconsistent" : ""}` : CLASS_HELP[l.match_class]}</td>
                      </tr>
                      {open === key && (
                        <tr key={key + "-d"}><td colSpan={5} className="bg-canvas">
                          <div className="grid gap-3 p-2 md:grid-cols-2">
                            <div><div className="label">Method</div><div className="text-xs">{l.method.name.replace(/_/g, " ")} v{l.method.version}</div>
                              <div className="label mt-2">Limitations</div><ul className="list-disc pl-4 text-xs">{(l.limitations || []).map((x: string) => <li key={x}>{x.replace(/_/g, " ")}</li>)}</ul>
                              {(l.counter_evidence || []).length > 0 && <><div className="label mt-2">Counter-evidence</div><ul className="list-disc pl-4 text-xs danger">{l.counter_evidence.map((x: string) => <li key={x}>{x}</li>)}</ul></>}
                              {(l.alternatives || []).length > 0 && <><div className="label mt-2">Alternative explanations (hypotheses, not facts){l.challenge_state ? ` · state: ${l.challenge_state}` : ""}</div><ul className="list-disc pl-4 text-xs">{l.alternatives.map((a: any) => <li key={a.hypothesis}><span className="font-medium">{a.hypothesis}</span> — {a.why_relevant} <span className="muted">Discriminating evidence: {a.discriminating_evidence}</span></li>)}</ul></>}
                              {l.domains && <><div className="label mt-2">Domains per case</div><ul className="text-xs">{Object.entries(l.domains).map(([c, ds]: any) => <li key={c}><span className="font-medium">{title(c)}:</span> <span className="mono">{ds.join(", ")}</span></li>)}</ul></>}
                              {l.event_times && <><div className="label mt-2">Event times</div><ul className="text-xs">{Object.entries(l.event_times).map(([c, ts]: any) => <li key={c}><span className="font-medium">{title(c)}:</span> {ts.map((t: string) => fmtTime(t)).join("; ")}</li>)}</ul></>}
                            </div>
                            <div><div className="label">Source evidence</div>
                              {l.evidence ? Object.entries(l.evidence).map(([c, evs]: any) => <div key={c} className="mb-2"><div className="text-xs font-semibold">{title(c)}</div>{evs.length === 0 && <div className="text-xs muted">entity present; no linked evidence row</div>}{evs.map((e: any) => <div key={e.evidence_item_id} className="mt-1 rounded border border-line bg-card p-1.5 text-[11px]"><div>{e.file} · <span className="mono">{Object.entries(e.locator).map(([k, v]) => `${k} ${v}`).join(", ")}</span> · {e.method.replace(/_/g, " ")}</div><div className="muted">sha256 <Copyable value={e.sha256 || ""} /></div><div className="muted">event {fmtTime(e.event_time)} [{e.time_precision}] · observed {fmtTime(e.observed_at)} · via {e.relationship_type.toLowerCase().replace(/_/g, " ")} ({e.relationship_level.replace("_", " ")})</div></div>)}</div>)
                                : l.evidence_item_ids ? Object.entries(l.evidence_item_ids).map(([c, ids]: any) => <div key={c} className="text-xs"><span className="font-semibold">{title(c)}</span>: evidence items <span className="mono">{ids.map((x: string) => x.slice(0, 8)).join(", ")}</span> · accounts <span className="mono">{(l.accounts?.[c] || []).join(", ")}</span></div>)
                                : <div className="text-xs muted">Infrastructure observations are listed per case above.</div>}
                            </div>
                          </div>
                        </td></tr>
                      )}
                    </>
                  );
                })}</tbody></table></div>
            )}
          </div>
          {res.rejected.length > 0 && (
            <div className="card p-0"><div className="px-4 py-3"><h2 className="section-title">Not asserted ({res.rejected.length})</h2><p className="text-xs muted">Similar names across cases are shown so you can see what the system refused to link.</p></div>
              <table className="data"><thead><tr><th>Name A</th><th>Name B</th><th>Identifiers</th><th>Similarity</th><th>Reason</th></tr></thead>
                <tbody>{res.rejected.map((r: any, i: number) => <tr key={i}><td>{r.name_a}</td><td>{r.name_b}</td><td className="mono text-xs">{r.identifier_a} ≠ {r.identifier_b}</td><td className="num text-xs">{r.similarity}</td><td className="text-xs muted">{r.reason}</td></tr>)}</tbody></table></div>
          )}
        </>
      )}
    </div>
  );
}

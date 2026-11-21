"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Locator, Section, State, Toast, useApi, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

const LAYERS: Record<string, string> = { victim_journey: "Victim journey", artefact: "Deception artefacts", payment: "Payment instructions", financial: "Financial movement", infrastructure: "Infrastructure", investigation: "Investigation activity", account_control: "Account control" };

export default function TwinPage() {
  const [layers, setLayers] = useState<string[]>(Object.keys(LAYERS));
  const [classes, setClasses] = useState<string[] | null>(null);
  const [cursor, setCursor] = useState<number>(100);
  const [sel, setSel] = useState<any>(null);
  const [form, setForm] = useState({ event_type: "VICTIM_CONTACT_REPORTED", description: "", event_time: "", reported_by: "complainant (interview)" });
  const [msg, setMsg] = useState<string | null>(null);
  return (
    <CasePage title="Fraud Operation Digital Twin" subtitle="A time-aware reconstruction of the suspected operation from persisted evidence. Unknown elements stay unknown; chronology is never turned into causation." pageKey="twin" wide>
      {(c, id) => <TwinBody id={id} layers={layers} setLayers={setLayers} classes={classes} setClasses={setClasses} cursor={cursor} setCursor={setCursor} sel={sel} setSel={setSel} form={form} setForm={setForm} msg={msg} setMsg={setMsg} />}
    </CasePage>
  );
}

function TwinBody({ id, layers, setLayers, classes, setClasses, cursor, setCursor, sel, setSel, form, setForm, msg, setMsg }: any) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/twin`);
  const events = useMemo(() => {
    if (!data) return [];
    let ev = data.events.filter((e: any) => layers.includes(e.layer));
    if (classes) ev = ev.filter((e: any) => classes.includes(e.evidence_class));
    const timed = ev.filter((e: any) => e.event_time);
    const n = Math.round((timed.length * cursor) / 100);
    const cut = timed[Math.max(0, Math.min(n, timed.length) - 1)]?.event_time;
    return cursor >= 100 ? ev : ev.filter((e: any) => !e.event_time || (cut && e.event_time <= cut));
  }, [data, layers, classes, cursor]);
  const linksFor = (eid: string) => (data?.links || []).filter((l: any) => l.from === eid || l.to === eid);
  async function addEvent(e: React.FormEvent) {
    e.preventDefault(); setMsg(null);
    try { await api(`/cases/${id}/twin/events`, { method: "POST", body: JSON.stringify({ ...form, event_time: form.event_time || null, time_precision: form.event_time ? "minute" : "unknown", layer: "victim_journey" }) }); setMsg("Reported event added (class: reported)."); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_1fr]">
            {Object.entries(data.supported_facts).map(([k, v]: [any, any]) => <div key={k} className="card"><div className="label mb-0">{k.replace(/_/g, " ")}</div><div className="num mt-1 text-2xl font-bold">{String(v)}</div></div>)}
          </div>
          <div className="card flex flex-wrap items-center gap-3 text-xs">
            <span className="label mb-0">Layers</span>
            {Object.entries(LAYERS).map(([k, l]: [any, any]) => <button key={k} className={`chip ${layers.includes(k) ? "chip-on" : ""}`} aria-pressed={layers.includes(k)} onClick={() => setLayers((cur: string[]) => cur.includes(k) ? cur.filter((x: any) => x !== k) : [...cur, k])}>{l}</button>)}
            <span className="label mb-0 ml-3">Evidence class</span>
            <select className="input !w-auto !py-1" aria-label="Filter by evidence class" value={classes ? classes[0] : ""} onChange={(e) => setClasses(e.target.value ? [e.target.value] : null)}><option value="">all</option>{Object.keys(data.legend).map((k: any) => <option key={k} value={k}>{k.replace(/_/g, " ")}</option>)}</select>
            <label className="ml-auto flex items-center gap-2"><I.timeline width={14} height={14} /><span>Time cursor</span><input type="range" min={0} max={100} value={cursor} onChange={(e) => setCursor(Number(e.target.value))} aria-label="Replay cursor" /><span className="num w-10">{cursor}%</span></label>
          </div>
          <div className="wb-grid">
            <div className="space-y-3">
              <Section title={`Operation timeline (${events.length} events)`} hint="Sorted by event time; undated events (document mentions) are listed last.">
                <ol className="max-h-[60vh] space-y-1 overflow-y-auto pr-1">
                  {events.map((e: any) => (
                    <li key={e.id}>
                      <button className={`flex w-full items-start gap-3 rounded-lg border p-2 text-left text-sm transition hover:bg-panel ${sel?.id === e.id ? "border-accent bg-accent-soft/40" : "border-line"}`} onClick={() => setSel(e)} aria-pressed={sel?.id === e.id}>
                        <span className="w-32 shrink-0 text-[11px] muted"><When v={e.event_time} />{!e.event_time && <span className="block">time unknown</span>}</span>
                        <span className="min-w-0 flex-1"><span className="block truncate font-medium">{e.label}</span><span className="text-[11px] muted">{LAYERS[e.layer]} · {e.event_type.replace(/_/g, " ").toLowerCase()}</span></span>
                        <Chip v={e.evidence_class} />
                      </button>
                    </li>
                  ))}
                  {events.length === 0 && <li className="p-4 text-center text-sm muted">No events in the selected layers.</li>}
                </ol>
              </Section>
              <Section title="Uncertainties and unresolved questions" hint="What the evidence does not establish.">
                <ul className="list-disc space-y-1 pl-5 text-sm">{data.uncertainties.length ? data.uncertainties.map((u: string, i: number) => <li key={i}>{u}</li>) : <li className="muted">None recorded.</li>}</ul>
              </Section>
            </div>
            <div className="space-y-3">
              {sel ? (
                <Section title="Event inspector" actions={<button className="btn-icon" onClick={() => setSel(null)} aria-label="Close inspector"><I.close /></button>}>
                  <KV rows={[["Type", sel.event_type.replace(/_/g, " ")], ["Class", <Chip key="c" v={sel.evidence_class} title={data.legend[sel.evidence_class]} />], ["Event time", <When key="t" v={sel.event_time} />], ["Precision", sel.time_precision], ["Observed at", <When key="o" v={sel.observed_at} />], ["Ingested", <When key="i" v={sel.ingested_at} />], ["Reported by", sel.reported_by || "—"], ["Layer", LAYERS[sel.layer]],
                    ["Source", <Locator key="l" caseId={id} fileId={sel.source_file_id} file={sel.attributes?.file} locator={sel.source_locator} evidenceId={sel.evidence_ids?.[0]} />]]} />
                  {sel.attributes?.note && <p className="mt-2 text-xs muted">{sel.attributes.note}</p>}
                  {sel.attributes?.warnings?.length > 0 && <p className="mt-2 text-xs warn">Warnings: {sel.attributes.warnings.join(", ")}</p>}
                  {sel.attributes?.limitations?.length > 0 && <p className="mt-2 text-xs warn">Limitations: {sel.attributes.limitations.join(", ")}</p>}
                  <div className="mt-3"><div className="label">Links ({linksFor(sel.id).length})</div><ul className="space-y-1 text-xs">{linksFor(sel.id).slice(0, 12).map((l: any, i: number) => <li key={i} className="flex items-center gap-2"><Chip v={l.evidence_class} /><span className="mono">{l.type}</span>{l.match_status && <span className="muted">{l.match_status}</span>}{l.note && <span className="muted">· {l.note}</span>}</li>)}</ul></div>
                  {sel.attributes?.instruction_id && <Link href={`/cases/${id}/payment-bridge`} className="mt-3 inline-flex items-center gap-1 text-sm text-accent-deep underline"><I.qr width={14} height={14} /> Open in Payment Instruction Bridge</Link>}
                  {sel.attributes?.relationship_id && <Link href={`/cases/${id}/counterproof?edge=${sel.attributes.relationship_id}`} className="mt-3 block text-sm text-accent-deep underline">Challenge this relationship</Link>}
                </Section>
              ) : <div className="card text-sm muted">Select an event to see its provenance, time semantics and links.</div>}
              <Section title="Legend">
                <ul className="space-y-1 text-xs">{Object.entries(data.legend).map(([k, v]: [any, any]) => <li key={k} className="flex items-start gap-2"><Chip v={k} /><span className="muted">{String(v)}</span></li>)}</ul>
              </Section>
              <Section title="Add a reported event" hint="Analyst-entered events are always `reported`; they never become directly observed.">
                <form onSubmit={addEvent} className="space-y-2 text-sm">
                  <select className="input" value={form.event_type} onChange={(e) => setForm({ ...form, event_type: e.target.value })} aria-label="Event type">{data.event_types.map((t: string) => <option key={t} value={t}>{t.replace(/_/g, " ").toLowerCase()}</option>)}</select>
                  <input className="input" placeholder="What was reported (min 3 chars)" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required minLength={3} aria-label="Description" />
                  <div className="grid grid-cols-2 gap-2"><input className="input" type="datetime-local" value={form.event_time} onChange={(e) => setForm({ ...form, event_time: e.target.value })} aria-label="Event time (optional)" /><input className="input" value={form.reported_by} onChange={(e) => setForm({ ...form, reported_by: e.target.value })} aria-label="Reported by" /></div>
                  <button className="btn-secondary w-full justify-center">Add reported event</button>
                </form>
                <Toast msg={msg} onClose={() => setMsg(null)} />
              </Section>
              <MotionScene scene="investigation_timeline" height={120} />
            </div>
          </div>
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

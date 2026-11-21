"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import CasePage from "@/components/CasePage";
import { Chip, KV, Section, State, Table, Toast, useApi, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api, getUser, isReviewer, saveAs } from "@/lib/api";

const STEPS = ["identified", "draft", "under_review", "authorised", "sent_manual", "received", "reviewed", "closed"];

export default function RequestsPage() {
  return <CasePage title="Evidence Acquisition — Outstanding Requests" subtitle="Draft, review, authorise and track evidence requests. PS05-X never transmits anything: 'sent' is recorded by an officer after a manual dispatch. Legal basis, recipient and wording must be validated by an authorised investigator." pageKey="requests" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/requests`);
  const files = useApi<any[]>(`/cases/${id}/files`);
  const [sel, setSel] = useState<any>(null);
  const [resp, setResp] = useState({ source_file_id: "", covers: "", remaining: "", note: "" });
  async function attachResponse(e: FormEvent) {
    e.preventDefault(); if (!sel) return; setMsg(null);
    try { const r = await api(`/cases/${id}/requests/${sel.id}/response`, { method: "POST", body: JSON.stringify({ source_file_id: resp.source_file_id, covers: resp.covers.split(/[;,]+/).map((x) => x.trim()).filter(Boolean), remaining: resp.remaining || null, note: resp.note }) }); setSel(r); setMsg(r.unresolved_remainder ? "Partial response recorded; the remainder stays open." : "Response recorded; request is received."); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  const [msg, setMsg] = useState<string | null>(null);
  const [status, setStatus] = useState({ status: "under_review", note: "", actual_dispatch_details: "", legal_authority: "", requesting_officer: "" });
  const [form, setForm] = useState({ title: "", catalogue_key: "account_statement", target_entity: "", organisation_type: "bank", rationale: "", window_from: "", window_to: "" });
  const reviewer = isReviewer(getUser());
  async function create(e: FormEvent) { e.preventDefault(); setMsg(null); try { await api(`/cases/${id}/requests`, { method: "POST", body: JSON.stringify({ ...form, window_from: form.window_from || null, window_to: form.window_to || null }) }); setMsg("Draft created (not sent)."); reload(); } catch (err: any) { setMsg(err.message); } }
  async function advance(e: FormEvent) {
    e.preventDefault(); if (!sel) return; setMsg(null);
    try { const r = await api(`/cases/${id}/requests/${sel.id}/status`, { method: "POST", body: JSON.stringify({ status: status.status, note: status.note, actual_dispatch_details: status.actual_dispatch_details || null, legal_authority: status.legal_authority || null, requesting_officer: status.requesting_officer || null }) }); setSel(r); setMsg(`Status is now ${r.status}.`); reload(); }
    catch (err: any) { setMsg(err.message); }
  }
  const reqs = data?.requests || [];
  const allowed: string[] = sel ? data.transitions[sel.status] || [] : [];
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="card"><div className="flex flex-wrap gap-1 text-xs">{STEPS.map((s: any, i: any) => <span key={s} className="flex items-center gap-1"><span className="badge lvl-derived">{s.replace(/_/g, " ")}</span>{i < STEPS.length - 1 && <I.chevron width={12} height={12} className="muted" />}</span>)}<span className="muted ml-2">plus rejected · unavailable · expired</span></div></div>
          <Toast msg={msg} onClose={() => setMsg(null)} />
          <div className="wb-grid">
            <div className="space-y-3">
              <Section title={`Requests (${reqs.length})`} hint="Suggestions come from Next-Best-Evidence; you can also draft one here.">
                <Table dense cols={["Title", "Custodian", "Target", "Status", "Created", ""]} empty={<span>No requests yet. <Link href={`/cases/${id}/ivoi`} className="underline">See ranked suggestions</Link>.</span>}
                  rows={reqs.map((r: any) => [<span key="t" className="font-medium">{r.title}{r.is_simulated && <span className="badge simulated ml-1">simulated</span>}</span>, r.organisation_type, <span key="e" className="mono">{r.target_entity}</span>, <Chip key="s" v={r.status === "sent_manual" ? "supported" : r.status === "received" || r.status === "reviewed" ? "corroborated" : r.status === "rejected" || r.status === "expired" || r.status === "unavailable" ? "contradicted" : "derived"} title={r.status} />, <When key="c" v={r.created_at} />, <button key="b" className="btn-secondary !py-1" onClick={() => { setSel(r); setStatus({ ...status, status: (data.transitions[r.status] || [])[0] || "closed" }); }}>Open</button>])} />
              </Section>
              <Section title="Draft a request manually" hint="Record types come from the controlled catalogue; procedural fields are marked for authorised validation.">
                <form onSubmit={create} className="grid gap-2 text-sm md:grid-cols-3">
                  <input className="input md:col-span-2" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} />
                  <select className="input" value={form.catalogue_key} onChange={(e) => { const k = e.target.value; setForm({ ...form, catalogue_key: k, organisation_type: data.catalogue[k]?.custodian_type || form.organisation_type }); }} aria-label="Record type">{Object.entries(data.catalogue).map(([k, v]: [string, any]) => <option key={k} value={k}>{v.label.slice(0, 60)}</option>)}</select>
                  <input className="input" placeholder="Target (account / VPA / IP / domain)" value={form.target_entity} onChange={(e) => setForm({ ...form, target_entity: e.target.value })} />
                  <input className="input" type="date" value={form.window_from} onChange={(e) => setForm({ ...form, window_from: e.target.value })} aria-label="Window from" /><input className="input" type="date" value={form.window_to} onChange={(e) => setForm({ ...form, window_to: e.target.value })} aria-label="Window to" />
                  <textarea className="input md:col-span-3" placeholder="Purpose / unresolved question this answers" value={form.rationale} onChange={(e) => setForm({ ...form, rationale: e.target.value })} />
                  <button className="btn md:col-span-3 justify-center">Create draft (nothing is sent)</button>
                </form>
              </Section>
            </div>
            <div className="space-y-3">
              {sel ? (
                <Section title="Request" actions={<button className="btn-icon" onClick={() => setSel(null)} aria-label="Close"><I.close /></button>}>
                  <KV rows={[["Title", sel.title], ["Status", <Chip key="s" v={sel.status} title={sel.status} />], ["Custodian type", `${sel.organisation_type} (suggested; possession not confirmed)`], ["Target", <span key="t" className="mono">{sel.target_entity}</span>], ["Window", `${sel.window_from?.slice(0, 10) || "—"} → ${sel.window_to?.slice(0, 10) || "—"}`], ["Fields", sel.required_fields.join(", ") || "—"], ["Could resolve", sel.could_resolve.join("; ") || "—"], ["Would not establish", sel.would_not_establish.join("; ") || "—"], ["Retention", sel.retention?.display || (sel.retention?.verified ? `verified: ${sel.retention.source_url}` : "RETENTION NOT VERIFIED")], ["Legal authority", sel.legal_authority || <span key="la" className="warn">requires authorised completion</span>], ["Requesting officer", sel.requesting_officer || <span key="ro" className="warn">requires authorised completion</span>]]} />
                  <p className="mt-2 text-xs muted">{sel.transmission}</p>
                  <button className="btn-secondary mt-2 !py-1" onClick={() => saveAs(`/cases/${id}/requests/${sel.id}/draft.pdf`, `request_draft_${sel.id.slice(0, 8)}.pdf`)}><I.download /> Draft PDF</button>
                  <form onSubmit={advance} className="mt-4 space-y-2 border-t border-line pt-3 text-sm">
                    <div className="label">Move status</div>
                    <select className="input" value={status.status} onChange={(e) => setStatus({ ...status, status: e.target.value })} aria-label="Next status">{allowed.map((s: any) => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}</select>
                    {status.status === "authorised" && <><input className="input" placeholder="Legal authority / section (validated by supervisor)" value={status.legal_authority} onChange={(e) => setStatus({ ...status, legal_authority: e.target.value })} /><input className="input" placeholder="Requesting officer" value={status.requesting_officer} onChange={(e) => setStatus({ ...status, requesting_officer: e.target.value })} /></>}
                    {status.status === "sent_manual" && <input className="input" placeholder="Actual dispatch details: channel, date, reference (required)" value={status.actual_dispatch_details} onChange={(e) => setStatus({ ...status, actual_dispatch_details: e.target.value })} required />}
                    <input className="input" placeholder="Note" value={status.note} onChange={(e) => setStatus({ ...status, note: e.target.value })} />
                    <button className="btn-secondary" disabled={!allowed.length || (["authorised", "sent_manual"].includes(status.status) && !reviewer)} title={["authorised", "sent_manual"].includes(status.status) && !reviewer ? "Requires supervisor/admin" : undefined}>Record</button>
                  </form>
                  {["sent_manual", "externally_confirmed", "partial_response"].includes(sel.status) && (
                    <form onSubmit={attachResponse} className="mt-4 space-y-2 border-t border-line pt-3 text-sm">
                      <div className="label">Attach a received record</div>
                      <p className="text-xs muted">Upload the returned record to this case first (Upload Evidence), then link it here. A partial response keeps what is still outstanding visible; nothing is transmitted.</p>
                      <select className="input" value={resp.source_file_id} onChange={(e) => setResp({ ...resp, source_file_id: e.target.value })} aria-label="Returned record (case file)" required>
                        <option value="">Select the returned record…</option>
                        {(files.data || []).map((f: any) => <option key={f.id} value={f.id}>{f.original_name} · {f.sha256.slice(0, 12)}…</option>)}
                      </select>
                      <input className="input" placeholder="What this response covers (semicolon separated)" value={resp.covers} onChange={(e) => setResp({ ...resp, covers: e.target.value })} />
                      <input className="input" placeholder="What remains outstanding (leave empty if the response is complete)" value={resp.remaining} onChange={(e) => setResp({ ...resp, remaining: e.target.value })} />
                      <input className="input" placeholder="Note" value={resp.note} onChange={(e) => setResp({ ...resp, note: e.target.value })} />
                      <button className="btn-secondary" disabled={!resp.source_file_id}>{resp.remaining ? "Record partial response" : "Record full response"}</button>
                    </form>
                  )}
                  {(sel.responses || []).length > 0 && (
                    <div className="mt-3"><div className="label">Responses received</div>
                      <ul className="text-xs">{sel.responses.map((r: any, i: number) => <li key={i} className="inset mt-1 p-2"><span className="font-medium">{r.name}</span> <span className="mono muted">{r.sha256?.slice(0, 16)}…</span><div>Covers: {(r.covers || []).join("; ") || "—"}</div><div className={r.remaining ? "warn" : "muted"}>{r.remaining ? `Still outstanding: ${r.remaining}` : "Complete response"}</div></li>)}</ul>
                      {sel.unresolved_remainder && <p className="warn mt-1 text-xs">Unresolved remainder: {sel.unresolved_remainder}</p>}
                    </div>
                  )}
                  <div className="mt-3"><div className="label">History</div><ul className="text-xs">{(sel.status_history || []).map((h: any, i: number) => <li key={i}>{h.from} → <span className="font-medium">{h.to}</span> · <When v={h.at} />{h.note ? ` · ${h.note}` : ""}{h.dispatch_details ? ` · dispatch: ${h.dispatch_details}` : ""}</li>)}</ul></div>
                </Section>
              ) : <div className="card text-sm muted">Open a request to review its scope, download the draft or move its status.</div>}
            </div>
          </div>
        </div>
      )}
    </State>
  );
}

"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, getUser } from "@/lib/api";

const FIELDS: [string, string, string][] = [
  ["officer_name", "Requesting officer name", "Section 1 · Requesting officer"], ["officer_rank", "Rank", ""], ["department", "Department / unit", ""], ["officer_contact", "Contact (phone / email)", ""],
  ["state", "State", "Section 2 · Jurisdiction"], ["district", "District", ""], ["police_station", "Police station", ""],
  ["fir_number", "FIR number", "Section 3 · Case"], ["fir_year", "FIR year", ""],
  ["supervising_officer_name", "Supervising SP / officer name", "Section 4 · Supervision"], ["supervising_officer_designation", "Designation", ""], ["supervising_officer_contact", "Contact", ""],
];

export default function CooperationPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [packs, setPacks] = useState<any[] | null>(null);
  const [files, setFiles] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [cur, setCur] = useState<any>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [fir, setFir] = useState("");
  const [endorse, setEndorse] = useState("");
  const [atts, setAtts] = useState<string[]>([]);
  const role = getUser()?.role;
  const load = useCallback(() => Promise.all([api(`/cases/${id}`), api(`/cases/${id}/cooperation`), api(`/cases/${id}/files`)]).then(([cc, p, f]) => { setC(cc); setPacks(p); setFiles(f); if (p.length && !cur) pick(p[p.length - 1]); }).catch((e) => setError(e.message)), [id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [load]);
  function pick(p: any) { setCur(p); setFields(p.fields || {}); setFir(p.fir_file_id || ""); setEndorse(p.endorsement_file_id || ""); setAtts(p.attachment_file_ids || []); }
  async function save() {
    setMsg(null);
    try { const p = await api(`/cases/${id}/cooperation${cur ? `?pack_id=${cur.id}` : ""}`, { method: "POST", body: JSON.stringify({ fields, fir_file_id: fir || null, endorsement_file_id: endorse || null, attachment_file_ids: atts }) }); setCur(p); setMsg("Saved as draft. Any edit withdraws endorsement."); await load(); }
    catch (e: any) { setMsg(e.message); }
  }
  async function doEndorse() { setMsg(null); try { const p = await api(`/cases/${id}/cooperation/${cur.id}/endorse`, { method: "POST" }); setCur(p); setMsg("Endorsed: export ready."); await load(); } catch (e: any) { setMsg(e.message); } }
  async function exportZip() { try { const blob: Blob = await api(`/cases/${id}/cooperation/${cur.id}/export.zip`, { raw: true }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `cooperation_pack_${id.slice(0, 8)}.zip`; a.click(); await load(); } catch (e: any) { setMsg(e.message); } }
  const v = cur?.validation;
  const missing = new Set<string>(v?.missing_fields || []);
  const bounds = v?.out_of_bounds || {};
  const len = (k: string) => (fields[k] || "").trim().length;
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Cross-state cooperation pack" subtitle="A manual handoff bundle aligned to the cooperation request fields. Nothing is submitted by this tool." pageKey="cooperation" step="report"
      actions={cur && <><button className="btn-secondary" onClick={save}><I.check /> Save draft</button>{role !== "analyst" && <button className="btn-secondary" onClick={doEndorse} disabled={!v?.complete}><I.shield /> Endorse</button>}<button className="btn" onClick={exportZip} disabled={cur.status !== "export_ready"}><I.download /> Export ZIP</button></>}>
      <State loading={!packs && !error} error={error} onRetry={load}>
        <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
          <div className="space-y-4">
            {!cur && <div className="callout"><I.file className="shrink-0 text-accent-deep" /><div>Fill the fields, attach the authorised FIR PDF and the supervisor-signed endorsement, save, then a supervisor endorses. The export contains a JSON manifest, a summary PDF, the attachments and the case&apos;s money/infrastructure trace with SHA-256 hashes.</div></div>}
            {msg && <div className="card text-sm" role="status">{msg}</div>}
            <div className="card">
              {FIELDS.map(([k, label, section]) => (
                <div key={k}>
                  {section && <div className="eyebrow mb-2 mt-4 first:mt-0">{section}</div>}
                  <label className="mb-2 block"><span className="label">{label}{missing.has(k) && <span className="danger"> · missing</span>}{bounds[k] && <span className="danger"> · {bounds[k]}</span>}</span><input className={`input ${missing.has(k) || bounds[k] ? "border-danger" : ""}`} value={fields[k] || ""} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} /></label>
                </div>
              ))}
              <div className="eyebrow mb-2 mt-4">Section 5 · Narrative (10–500 characters each)</div>
              {(["fir_gist", "assistance_details"] as const).map((k) => <label key={k} className="mb-2 block"><span className="label">{k === "fir_gist" ? "FIR gist" : "Assistance required"} · <span className={`num ${len(k) < 10 || len(k) > 500 ? "danger" : "ok"}`}>{len(k)}/500</span>{missing.has(k) && <span className="danger"> · missing</span>}</span><textarea className={`input ${bounds[k] || missing.has(k) ? "border-danger" : ""}`} rows={3} maxLength={600} value={fields[k] || ""} onChange={(e) => setFields({ ...fields, [k]: e.target.value })} /></label>)}
              <div className="eyebrow mb-2 mt-4">Section 6 · Attachments</div>
              <div className="grid gap-2 md:grid-cols-2">
                <label className="block"><span className="label">FIR PDF (required){!fir && <span className="danger"> · missing</span>}</span><select className="input" value={fir} onChange={(e) => setFir(e.target.value)}><option value="">—</option>{files.map((f) => <option key={f.id} value={f.id}>{f.original_name}</option>)}</select></label>
                <label className="block"><span className="label">Supervisor-signed endorsement (required){!endorse && <span className="danger"> · missing</span>}</span><select className="input" value={endorse} onChange={(e) => setEndorse(e.target.value)}><option value="">—</option>{files.map((f) => <option key={f.id} value={f.id}>{f.original_name}</option>)}</select></label>
              </div>
              <div className="label mt-3">Other evidence to include</div>
              <ul className="grid gap-1 md:grid-cols-2">{files.map((f) => <li key={f.id}><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={atts.includes(f.id)} onChange={() => setAtts(atts.includes(f.id) ? atts.filter((x) => x !== f.id) : [...atts, f.id])} /><span className="truncate">{f.original_name}</span><span className="mono text-[10px] muted">{f.sha256.slice(0, 12)}…</span></label></li>)}</ul>
              {!cur && <button className="btn mt-4" onClick={save}><I.check /> Save draft</button>}
            </div>
          </div>
          <div className="space-y-3 xl:sticky xl:top-20 xl:self-start">
            <div className="card">
              <h3 className="font-semibold">Checklist</h3>
              {v ? <ul className="mt-2 space-y-1 text-sm">
                <li className={v.missing_fields.length ? "danger" : "ok"}>{v.missing_fields.length ? `${v.missing_fields.length} required field(s) missing` : "All required fields present"}</li>
                <li className={Object.keys(v.out_of_bounds).length ? "danger" : "ok"}>{Object.keys(v.out_of_bounds).length ? "Narrative lengths out of bounds" : "Narrative lengths within 10–500"}</li>
                <li className={v.missing_attachments.length ? "danger" : "ok"}>{v.missing_attachments.length ? `Missing: ${v.missing_attachments.join(", ").replace(/_/g, " ")}` : "FIR and endorsement attached"}</li>
                <li className={cur.status === "export_ready" ? "ok" : "warn"}>Status: {cur.status.replace(/_/g, " ")}{cur.endorsed_by ? " (endorsed)" : " — supervisor endorsement pending"}</li>
                {cur.exported_at && <li className="muted">Last exported {fmtTime(cur.exported_at)}</li>}
              </ul> : <p className="mt-1 text-sm muted">Save a draft to see validation.</p>}
            </div>
            <div className="card text-xs muted"><div className="label">Boundaries</div>No portal login, CAPTCHA or automated submission. Verify the current official cooperation-request process before relying on this pack. Every save, endorsement and export is written to the audit log.</div>
            {packs && packs.length > 1 && <div className="card"><div className="label">Packs in this case</div><ul className="text-sm">{packs.map((p) => <li key={p.id}><button className="text-accent-deep hover:underline" onClick={() => pick(p)}>{p.id.slice(0, 8)} · {p.status.replace(/_/g, " ")}</button></li>)}</ul></div>}
          </div>
        </div>
      </State>
    </Shell>
  );
}

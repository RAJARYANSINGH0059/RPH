"use client";

import { FormEvent, useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Money, Section, State, Table, Toast, useApi, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api, saveAs, upload } from "@/lib/api";

const LEVEL_TEXT: Record<string, string> = {
  EXACT_REFERENCE_AND_IDENTIFIER: "Payee identifier and transaction reference both match a recorded transaction.", EXACT_IDENTIFIER_AMOUNT: "Payee identifier and amount match; no reference available to confirm further.",
  CORROBORATED_MULTI_FIELD: "Two or more fields agree without conflicts, but not the strongest pair.", CANDIDATE_PARTIAL_MATCH: "Only one weak field agrees. Not evidence of payment.",
  CONFLICTED_MATCH: "An identifying field matches but amount, currency or reference conflicts.", NO_MATCH: "No recorded transaction shares the payee or reference.", UNRESOLVED: "The instruction has neither a payee nor a reference to compare.",
};

export default function BridgePage() {
  return <CasePage title="Payment Instruction Bridge" subtitle="Decode a QR image or upi:// link, then compare it field by field with recorded transactions. A match links an artefact to a payment record; it never identifies who controls the payee account." pageKey="bridge" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/payment-instructions`);
  const [sel, setSel] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [payload, setPayload] = useState("");
  const [tol, setTol] = useState(72);
  async function match(pid: string) { setBusy(true); try { setSel(await api(`/cases/${id}/payment-instructions/${pid}/match?tolerance_hours=${tol}`, { method: "POST" })); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); } }
  async function register(e: FormEvent) { e.preventDefault(); setBusy(true); setMsg(null); try { setSel(await api(`/cases/${id}/payment-instructions`, { method: "POST", body: JSON.stringify({ raw_payload: payload }) })); setPayload(""); reload(); } catch (err: any) { setMsg(err.message); } finally { setBusy(false); } }
  async function decode(file: File) {
    setBusy(true); setMsg(null);
    try { const fd = new FormData(); fd.append("file", file); const r = await upload(`/cases/${id}/payment-instructions/decode-image`, fd); setMsg(r.decoded ? `Decoded ${r.decoded} QR code(s).` : r.warnings.join("; ")); if (r.results[0]) setSel(r.results[0]); reload(); }
    catch (err: any) { setMsg(err.message); } finally { setBusy(false); }
  }
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-3">
            <Section title="1 · Decode a QR image" hint={`Decoder: ${data.decoder.available ? `OpenCV ${data.decoder.version}` : "unavailable"}. Nothing is opened or paid; the payload is stored as evidence.`}>
              <label className="btn-secondary w-full justify-center cursor-pointer"><I.qr /> Choose PNG/JPEG<input type="file" accept="image/png,image/jpeg" className="sr-only" onChange={(e) => e.target.files?.[0] && decode(e.target.files[0])} disabled={busy} /></label>
              <MotionScene scene="evidence_scan" height={110} className="mt-3" />
            </Section>
            <Section title="2 · Or paste the payment text" hint="upi://pay?… link, payment URL, or pa=…&am=… text copied from a page.">
              <form onSubmit={register} className="space-y-2"><textarea className="input min-h-[88px] mono text-xs" value={payload} onChange={(e) => setPayload(e.target.value)} placeholder="upi://pay?pa=payee@bank&am=4500.00&cu=INR&tr=REF…" aria-label="Payment payload" required /><button className="btn w-full justify-center" disabled={busy}>Register and match</button></form>
            </Section>
            <Section title="3 · Matching rule" hint="Fields compared: payee VPA (exact, alias-aware), reference/UTR, amount, currency, note, name (weak), time.">
              <label className="text-sm">Time tolerance (hours) <input type="number" className="input mt-1" min={1} max={720} value={tol} onChange={(e) => setTol(Number(e.target.value))} /></label>
              <ul className="mt-2 space-y-1 text-xs">{data.levels.map((l: string) => <li key={l} className="flex items-start gap-2"><Chip v={l.startsWith("EXACT") ? "corroborated" : l.startsWith("CORR") ? "derived" : l.startsWith("CAND") ? "candidate" : l.startsWith("CONF") ? "contradicted" : "unresolved"} /><span><span className="mono">{l}</span> — {LEVEL_TEXT[l]}</span></li>)}</ul>
            </Section>
          </div>
          <Toast msg={msg} onClose={() => setMsg(null)} />
          <div className="wb-grid">
            <Section title={`Instructions in this case (${data.instructions.length})`} actions={data.instructions.length > 0 && <button className="btn-secondary" onClick={() => saveAs(`/cases/${id}/payment-instructions/report.pdf`, `payment_bridge_${id.slice(0, 8)}.pdf`)}><I.download /> Report PDF</button>}>
              <Table cols={["Source", "Payee (raw → normalised)", "Amount", "Reference", "Note", "Warnings", ""]} empty="No payment instruction yet. Decode a QR image or paste a link above; Desert Mirage bundles include both."
                rows={data.instructions.map((p: any) => [<span key="s"><Chip v={p.extraction_method === "qr_decoder" ? "extracted" : p.extraction_method === "ocr_text" ? "candidate" : "extracted"} /> <span className="text-xs muted">{p.extraction_method}</span></span>,
                  <span key="p" className="mono text-xs">{p.fields?.pa_raw || "—"}{p.payee_vpa && p.fields?.pa_raw !== p.payee_vpa ? ` → ${p.payee_vpa}` : ""}</span>, <Money key="a" v={p.amount_minor} />, <span key="r" className="mono text-xs">{p.reference || "—"}</span>, <span key="n" className="text-xs">{p.note_raw || "—"}</span>,
                  <span key="w" className="text-xs warn">{(p.warnings || []).slice(0, 3).join(", ")}</span>, <button key="b" className="btn-secondary !py-1" onClick={() => match(p.id)} disabled={busy}>Compare</button>])} />
            </Section>
            <div className="space-y-3">
              {sel ? (
                <Section title="Comparison result" actions={<button className="btn-icon" onClick={() => setSel(null)} aria-label="Close"><I.close /></button>}>
                  <div className="mb-2 flex items-center gap-2"><Chip v={sel.match_status.startsWith("EXACT") ? "corroborated" : sel.match_status.startsWith("CORR") ? "derived" : sel.match_status.startsWith("CAND") ? "candidate" : sel.match_status.startsWith("CONF") ? "contradicted" : "unresolved"} /><span className="mono text-sm font-semibold">{sel.match_status}</span></div>
                  <p className="text-xs muted">{LEVEL_TEXT[sel.match_status]}</p>
                  <KV className="mt-3" rows={[["Raw payload", <span key="r" className="mono break-all text-xs">{sel.instruction.raw_payload}</span>], ["Payee", sel.instruction.payee_vpa || "—"], ["Amount", <Money key="a" v={sel.instruction.amount_minor} />], ["Currency", sel.instruction.currency || "not stated"], ["Reference", sel.instruction.reference || "—"], ["Decoder", `${sel.instruction.extraction_method} v${sel.instruction.decoder_version}`], ["Observed at", sel.instruction.observed_at ? <When key="o" v={sel.instruction.observed_at} /> : "unknown (when the victim saw it is not recorded)"]]} />
                  <div className="mt-3"><div className="label">Candidate transactions ({sel.candidates.length})</div>
                    <ul className="space-y-2 text-xs">{sel.candidates.slice(0, 6).map((cnd: any) => <li key={cnd.transaction_id} className="inset p-2"><div className="flex items-center justify-between gap-2"><span className="mono">{cnd.status}</span><Money v={cnd.transaction.amount_minor} /></div><div className="muted">{cnd.transaction.account} → {cnd.transaction.counterparty_raw} · ref {cnd.transaction.reference || "—"} · <When v={cnd.transaction.event_time} /></div><div className="mt-1 flex flex-wrap gap-1">{cnd.matched_fields.map((f: string) => <span key={f} className="badge bg-ok-soft text-ok">✓ {f}</span>)}{cnd.conflicting_fields.map((f: string) => <span key={f} className="badge bg-danger-soft text-danger">✗ {f}</span>)}{cnd.missing_fields.map((f: string) => <span key={f} className="badge lvl-insufficient">? {f}</span>)}</div></li>)}{sel.candidates.length === 0 && <li className="muted">No candidate transaction shares the payee or reference.</li>}</ul></div>
                  {sel.warnings?.length > 0 && <p className="mt-2 text-xs warn">{sel.warnings.join("; ")}</p>}
                  <Limitations items={sel.limitations} />
                </Section>
              ) : <div className="card text-sm muted">Pick an instruction and press Compare, or decode/paste a new one.</div>}
            </div>
          </div>
        </div>
      )}
    </State>
  );
}

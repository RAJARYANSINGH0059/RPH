"use client";

import { useParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import Shell, { Stat, State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, getUser, paise } from "@/lib/api";

const STATUS_NEXT: Record<string, string> = { draft: "Mark investigator-checked", investigator_checked: "Supervisor check", supervisor_checked: "Mark export-ready", export_ready: "Export ready" };

export default function ClaimsPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [rec, setRec] = useState<any>(null);
  const [txs, setTxs] = useState<any[]>([]);
  const [cands, setCands] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [form, setForm] = useState({ victim_label: "", complaint_ack_no: "", fir_reference: "", claimed_loss: "" });
  const [link, setLink] = useState<{ claim: string; tx: string; amount: string }>({ claim: "", tx: "", amount: "" });
  const [funds, setFunds] = useState({ kind: "held", account_ref: "", amount: "", source_evidence_item_id: "", source_kind: "bank_notice", reference: "" });
  const role = getUser()?.role;
  const load = useCallback(() => Promise.all([api(`/cases/${id}`), api(`/cases/${id}/claims`), api(`/cases/${id}/transactions`), api(`/cases/${id}/claims/evidence-candidates`)])
    .then(([cc, r, t, ev]) => { setC(cc); setRec(r); setTxs(t); setCands(ev); }).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);
  const toMinor = (s: string) => Math.round(parseFloat(s || "0") * 100);
  async function act(fn: () => Promise<any>, ok: string) { setMsg(null); try { await fn(); setMsg(ok); await load(); } catch (e: any) { setMsg(e.message); } }
  async function createClaim(e: FormEvent) { e.preventDefault(); await act(() => api(`/cases/${id}/claims`, { method: "POST", body: JSON.stringify({ victim_label: form.victim_label, complaint_ack_no: form.complaint_ack_no, fir_reference: form.fir_reference, claimed_loss_minor: toMinor(form.claimed_loss) }) }), "Claim recorded."); setForm({ victim_label: "", complaint_ack_no: "", fir_reference: "", claimed_loss: "" }); }
  async function addLink(e: FormEvent) { e.preventDefault(); await act(() => api(`/cases/${id}/claims/${link.claim}/links`, { method: "POST", body: JSON.stringify({ transaction_id: link.tx, amount_minor: link.amount ? toMinor(link.amount) : null }) }), "Transaction linked."); }
  async function addFunds(e: FormEvent) { e.preventDefault(); await act(() => api(`/cases/${id}/claims/funds`, { method: "POST", body: JSON.stringify({ ...funds, amount_minor: toMinor(funds.amount) }) }), "Funds record saved."); }
  const download = async (path: string, name: string) => { const blob: Blob = await api(path, { raw: true }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); };
  const debits = txs.filter((t) => t.amount_minor !== null);
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Victim claims & restitution readiness" subtitle="Claimed, traced, documented-held, restored and unresolved amounts are kept apart. The tool never allocates." pageKey="claims" step="review"
      actions={rec && <><button className="btn-secondary" onClick={() => download(`/cases/${id}/claims/pack.pdf`, `restitution_pack_${id.slice(0, 8)}.pdf`)}><I.download /> Readiness pack PDF</button><button className="btn-secondary" onClick={() => download(`/cases/${id}/claims/pack.json`, `restitution_pack_${id.slice(0, 8)}.json`)}>JSON</button></>}>
      <State loading={!rec && !error} error={error} onRetry={load}>
        {rec && (
          <div className="space-y-4">
            <div className="callout-warn"><I.shield className="shrink-0" /><div>{rec.disclaimer}</div></div>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Stat label="Claimed" value={paise(rec.totals.claimed_minor)} hint="entered from complaints" />
              <Stat label="Traced (distinct)" value={paise(rec.totals.traced_distinct_minor)} hint="each transaction once" tone="info" />
              <Stat label="Documented held" value={paise(rec.totals.documented_held_minor)} hint="needs a source document" tone="ok" />
              <Stat label="Restored" value={paise(rec.totals.documented_restored_minor)} hint="documented only" />
              <Stat label="Unresolved" value={paise(rec.totals.unresolved_minor)} hint="claimed − traced" tone={rec.totals.unresolved_minor ? "warn" : "ok"} />
            </div>
            {msg && <div className="card text-sm" role="status">{msg}</div>}
            <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
              <div className="space-y-4">
                <div className="card p-0"><div className="px-4 py-3"><h2 className="section-title">Claims ({rec.claims.length})</h2></div>
                  {rec.claims.length === 0 ? <div className="px-4 pb-4 text-sm muted">No claims yet. Record one from the complaint acknowledgement.</div> : (
                    <table className="data"><thead><tr><th>Victim</th><th>Ack / FIR</th><th>Claimed</th><th>Traced</th><th>Unresolved</th><th>Status</th><th></th></tr></thead>
                      <tbody>{rec.claims.map((cl: any) => (
                        <tr key={cl.claim_id} className={cl.competing ? "bg-saffron-soft/40" : ""}>
                          <td className="font-medium">{cl.victim_label}{cl.competing && <div className="text-[11px] warn">competing claim on a shared transaction</div>}{rec.duplicate_claims.some((d: any) => d.claim_id === cl.claim_id) && <div className="text-[11px] danger">possible duplicate claim</div>}</td>
                          <td className="mono text-xs">{cl.complaint_ack_no || "—"}<br />{cl.fir_reference || "—"}</td>
                          <td className="num">{paise(cl.claimed_minor)}</td><td className="num">{paise(cl.traced_minor)}{cl.over_traced && <div className="text-[11px] warn">traced exceeds claimed</div>}</td><td className="num">{paise(cl.unresolved_minor)}</td>
                          <td><span className="badge bg-panel text-ink">{cl.status.replace(/_/g, " ")}</span><div className="mt-1 text-[11px] muted">{cl.transactions.length} linked tx</div></td>
                          <td>{cl.status !== "export_ready" && <button className="btn-secondary" onClick={() => act(() => api(`/cases/${id}/claims/${cl.claim_id}/advance`, { method: "POST" }), "Status advanced.")} disabled={(cl.status !== "draft" && role === "analyst") || cl.transactions.length === 0} title={cl.status !== "draft" && role === "analyst" ? "Supervisor required" : ""}>{STATUS_NEXT[cl.status]}</button>}</td>
                        </tr>))}</tbody></table>
                  )}
                </div>
                <div className="card p-0"><div className="px-4 py-3"><h2 className="section-title">Accounts: traced inflow vs documented hold</h2><p className="text-xs muted">Oversubscribed means claims exceed what is documented as held. Allocation is a human/legal decision.</p></div>
                  <table className="data"><thead><tr><th>Account</th><th>Traced inflow</th><th>Documented held</th><th>Restored</th><th>Claims</th><th>Flag</th></tr></thead>
                    <tbody>{rec.accounts.map((a: any) => <tr key={a.account}><td className="mono text-xs">{a.account}</td><td className="num">{paise(a.traced_inflow_minor)}</td><td className="num">{paise(a.documented_held_minor)}{a.held_is_simulated && <span className="badge ml-1 bg-terracotta text-white">simulated</span>}</td><td className="num">{paise(a.documented_restored_minor)}</td><td className="num">{a.claims.length}</td><td className="text-xs">{a.oversubscribed ? <span className="warn">oversubscribed by {paise(a.shortfall_minor)}</span> : a.claims.length > 1 ? <span className="muted">multiple claims · review</span> : "—"}</td></tr>)}
                      {rec.accounts.length === 0 && <tr><td colSpan={6} className="text-sm muted">Link transactions to claims to see receiving accounts.</td></tr>}</tbody></table>
                </div>
                {rec.funds_records.length > 0 && <div className="card p-0"><div className="px-4 py-3"><h2 className="section-title">Documented funds records</h2></div><table className="data"><thead><tr><th>Kind</th><th>Account</th><th>Amount</th><th>Source</th><th>Reference</th></tr></thead><tbody>{rec.funds_records.map((f: any) => <tr key={f.id}><td>{f.kind}</td><td className="mono text-xs">{f.account}</td><td className="num">{paise(f.amount_minor)}</td><td className="text-xs">{f.source_kind.replace(/_/g, " ")}{f.is_simulated && <span className="badge ml-1 bg-terracotta text-white">simulated</span>}<div className="mono muted">{JSON.stringify(f.source_locator)}</div></td><td className="mono text-xs">{f.reference || "—"}</td></tr>)}</tbody></table></div>}
              </div>
              <div className="space-y-3">
                <form onSubmit={createClaim} className="card space-y-2"><h3 className="font-semibold">Record a claim</h3>
                  <div><label className="label">Victim label (pseudonymous)</label><input className="input" required value={form.victim_label} onChange={(e) => setForm({ ...form, victim_label: e.target.value })} placeholder="Victim 1" /></div>
                  <div className="grid grid-cols-2 gap-2"><div><label className="label">Complaint ack no.</label><input className="input" value={form.complaint_ack_no} onChange={(e) => setForm({ ...form, complaint_ack_no: e.target.value })} /></div><div><label className="label">FIR reference</label><input className="input" value={form.fir_reference} onChange={(e) => setForm({ ...form, fir_reference: e.target.value })} /></div></div>
                  <div><label className="label">Claimed loss (₹)</label><input className="input" type="number" min="0.01" step="0.01" required value={form.claimed_loss} onChange={(e) => setForm({ ...form, claimed_loss: e.target.value })} /></div>
                  <button className="btn">Save claim</button></form>
                <form onSubmit={addLink} className="card space-y-2"><h3 className="font-semibold">Link a source transaction</h3>
                  <div><label className="label">Claim</label><select className="input" required value={link.claim} onChange={(e) => setLink({ ...link, claim: e.target.value })}><option value="">—</option>{rec.claims.map((cl: any) => <option key={cl.claim_id} value={cl.claim_id}>{cl.victim_label}</option>)}</select></div>
                  <div><label className="label">Transaction</label><select className="input" required value={link.tx} onChange={(e) => setLink({ ...link, tx: e.target.value })}><option value="">—</option>{debits.slice(0, 300).map((t) => <option key={t.id} value={t.id}>{fmtTime(t.datetime_utc).slice(0, 10)} · {t.direction} {paise(t.amount_minor)} · {t.account_ref} → {t.counterparty_ref || "?"} · {t.external_reference || ""}</option>)}</select></div>
                  <div><label className="label">Attributed amount (₹, optional)</label><input className="input" type="number" min="0.01" step="0.01" value={link.amount} onChange={(e) => setLink({ ...link, amount: e.target.value })} /></div>
                  <button className="btn-secondary">Link</button></form>
                <form onSubmit={addFunds} className="card space-y-2"><h3 className="font-semibold">Record a documented hold / restoration</h3><p className="text-xs muted">Requires a source document already in the case (bank notice, police record). Statement rows are refused.</p>
                  <div className="grid grid-cols-2 gap-2"><div><label className="label">Kind</label><select className="input" value={funds.kind} onChange={(e) => setFunds({ ...funds, kind: e.target.value })}><option value="held">held</option><option value="restored">restored</option></select></div><div><label className="label">Source kind</label><select className="input" value={funds.source_kind} onChange={(e) => setFunds({ ...funds, source_kind: e.target.value })}><option value="bank_notice">bank notice</option><option value="police_record">police record</option><option value="synthetic_simulated">synthetic (simulated)</option></select></div></div>
                  <div><label className="label">Account</label><input className="input" required value={funds.account_ref} onChange={(e) => setFunds({ ...funds, account_ref: e.target.value })} list="acct-list" /><datalist id="acct-list">{rec.accounts.map((a: any) => <option key={a.account} value={a.account} />)}</datalist></div>
                  <div><label className="label">Amount (₹)</label><input className="input" type="number" min="0.01" step="0.01" required value={funds.amount} onChange={(e) => setFunds({ ...funds, amount: e.target.value })} /></div>
                  <div><label className="label">Source evidence</label><select className="input" required value={funds.source_evidence_item_id} onChange={(e) => setFunds({ ...funds, source_evidence_item_id: e.target.value })}><option value="">—</option>{cands.map((x) => <option key={x.evidence_item_id} value={x.evidence_item_id}>{x.file} · {Object.entries(x.locator).map(([k, v]) => `${k} ${v}`).join(" ")} · {x.snippet.slice(0, 50)}</option>)}</select></div>
                  <div><label className="label">Reference</label><input className="input" value={funds.reference} onChange={(e) => setFunds({ ...funds, reference: e.target.value })} /></div>
                  <button className="btn-secondary">Save record</button></form>
              </div>
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

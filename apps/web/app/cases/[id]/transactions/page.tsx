"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Shell, { Stat, State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, paise } from "@/lib/api";

export default function TransactionsPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [txs, setTxs] = useState<any[] | null>(null);
  const [paths, setPaths] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [only, setOnly] = useState<"all" | "flagged" | "dupes" | "ambiguous">("all");
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/transactions`), api(`/cases/${id}/paths`)]).then(([cc, tt, pp]) => { setC(cc); setTxs(tt); setPaths(pp); }).catch((e) => setError(e.message)); }, [id]);
  const shown = useMemo(() => (txs || []).filter((t: any) => (!filter || JSON.stringify(t).toLowerCase().includes(filter.toLowerCase())) && (only === "all" || (only === "flagged" && t.warnings.length) || (only === "dupes" && t.duplicate_of) || (only === "ambiguous" && t.time_precision === "ambiguous"))), [txs, filter, only]);
  const feats = Object.entries(paths?.features || {}) as [string, any][];
  const chart = feats.map(([a, f]: [any, any]) => ({ account: a.length > 10 ? "…" + a.slice(-8) : a, inflow: f.total_in_minor / 100, outflow: f.total_out_minor / 100 })).sort((x, y) => y.inflow + y.outflow - x.inflow - x.outflow).slice(0, 10);
  const signals = feats.filter(([, f]) => f.triage.reasons.length).sort((x, y) => y[1].triage.heuristic_score - x[1].triage.heuristic_score);
  const stats = txs ? { total: txs.length, amount: txs.filter((t: any) => t.amount_minor !== null).length, amb: txs.filter((t: any) => t.time_precision === "ambiguous").length, dup: txs.filter((t: any) => t.duplicate_of).length } : null;
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Transactions and fund flow" subtitle="Every parsed row with its raw text, the paths the money took, and transparent triage signals." pageKey="transactions" step="flow">
      <State loading={!txs && !error} error={error} empty={txs && txs.length === 0 ? <div><div className="font-semibold">No transactions parsed yet</div><div className="mt-1">Upload a CSV or XLSX statement on the Upload Evidence page.</div></div> : null}>
        <div className="space-y-4">
          {stats && <div className="grid grid-cols-2 gap-3 md:grid-cols-4"><Stat label="Rows parsed" value={stats.total} hint="raw text kept for each" /><Stat label="With amount" value={stats.amount} hint="integer paise, never floats" /><Stat label="Ambiguous dates" value={stats.amb} hint="dd/mm vs mm/dd kept flagged" tone={stats.amb ? "warn" : "ok"} /><Stat label="Duplicate candidates" value={stats.dup} hint="both copies kept" tone={stats.dup ? "warn" : "ok"} /></div>}
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card">
              <h2 className="flex items-center gap-2 font-semibold"><I.link className="text-accent" /> Reconstructed fund paths</h2>
              <p className="mb-2 text-xs text-ink-muted">Derived by chaining transfers in time order (each hop after the previous one, within 96 h). Sub-paths are pruned. A VPA and its account number are treated as one node when a reference match proves it.</p>
              {paths?.paths?.length ? <ol className="space-y-2 text-sm">{paths.paths.slice(0, 8).map((p: any, i: number) => (
                <li key={i} className="rounded-lg border border-line bg-card p-2.5">
                  <div className="flex flex-wrap items-center gap-1.5">{p.accounts.map((a: string, j: number) => <span key={j} className="flex items-center gap-1.5"><span className={`rounded-md px-2 py-0.5 mono text-xs ${j === 0 ? "bg-accent-light text-accent-dark" : j === p.accounts.length - 1 ? "bg-saffron-soft text-warn" : "bg-panel"}`}>{a}</span>{j < p.accounts.length - 1 && <I.arrow width={14} height={14} className="text-ink-muted" />}</span>)}</div>
                  <div className="mt-1 text-xs text-ink-muted">{p.hop_count} hop{p.hop_count > 1 ? "s" : ""} · entry {paise(p.total_in_minor)} · exit {paise(p.exit_amount_minor)}{p.time_uncertain && <span className="badge ml-1 bg-saffron-soft text-warn">time uncertain</span>}</div>
                </li>))}</ol> : <div className="text-sm text-ink-muted">No multi-hop path yet. Paths appear when one account&apos;s debit lands in another account that later pays onward.</div>}
              {paths?.reconciliation?.length > 0 && <div className="mt-3 text-xs"><div className="label">Balance reconciliation per statement</div>{paths.reconciliation.map((r: any) => <div key={r.parse_run_id} className={r.mismatch_minor ? "warn" : "text-ink-muted"}>{r.mismatch_minor ? "⚠" : "✓"} expected {paise(r.expected_last_minor)}, stated {paise(r.last_balance_minor)}{r.mismatch_minor ? `, mismatch ${paise(r.mismatch_minor)}` : ""}</div>)}</div>}
            </div>
            <div className="card">
              <h2 className="font-semibold">Inflow vs outflow by account (₹)</h2>
              <div style={{ height: 200 }}><ResponsiveContainer><BarChart data={chart} margin={{ left: 8, right: 8 }}><CartesianGrid strokeDasharray="3 3" stroke="#eef1f4" /><XAxis dataKey="account" fontSize={10} /><YAxis fontSize={10} tickFormatter={(v) => `${Math.round(v / 1000)}k`} /><Tooltip formatter={(v: any) => `₹${Number(v).toLocaleString("en-IN")}`} /><Legend wrapperStyle={{ fontSize: 11 }} /><Bar dataKey="inflow" fill="#1f5fa8" radius={[3, 3, 0, 0]} /><Bar dataKey="outflow" fill="#b7791f" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
              <h3 className="mt-3 flex items-center gap-2 text-sm font-semibold"><I.alert className="text-warn" width={16} height={16} /> Triage signals <span className="font-normal text-ink-muted">(rules; a reason to look, not a conclusion)</span></h3>
              {signals.length === 0 ? <div className="text-xs text-ink-muted">No rule fired.</div> : <ul className="mt-1 space-y-1.5 text-xs">{signals.slice(0, 8).map(([a, f]: [any, any]) => <li key={a} className="rounded-lg bg-canvas p-2"><div className="flex flex-wrap items-center gap-2"><span className="mono">{a}</span><span className={`badge ${f.triage.label.startsWith("possible") ? "bg-saffron-soft text-warn" : "bg-panel"}`}>{f.triage.label.replace(/_/g, " ")}</span>{f.ml_triage && <span className="badge bg-panel" title={f.ml_triage.semantics}>ML cue {f.ml_triage.triage_score}</span>}</div><div className="mt-0.5 text-ink-muted">{f.triage.reasons.map((r: string) => r.replace(/_/g, " ")).join(" · ")}</div></li>)}</ul>}
            </div>
          </div>
          <div className="card p-0">
            <div className="flex flex-wrap items-center gap-2 px-4 py-3">
              <h2 className="font-semibold">Transactions</h2>
              <div className="relative ml-auto"><I.search className="absolute left-2 top-2 text-ink-muted" width={15} height={15} /><input className="input w-64 py-1.5 pl-7" placeholder="Filter by account, ref, narration…" aria-label="Filter transactions" value={filter} onChange={(e) => setFilter(e.target.value)} /></div>
              {(["all", "flagged", "dupes", "ambiguous"] as const).map((k: any) => <button key={k} className={`chip ${only === k ? "chip-on" : ""}`} onClick={() => setOnly(k)}>{k === "all" ? "All" : k === "flagged" ? "With flags" : k === "dupes" ? "Duplicates" : "Ambiguous dates"}</button>)}
              <span className="text-xs text-ink-muted">{shown.length} rows</span>
            </div>
            <div className="max-h-[560px] overflow-auto"><table className="data"><thead><tr><th>When (UTC)</th><th>Account</th><th>Direction</th><th>Amount</th><th>Counterparty</th><th>Reference</th><th>Channel</th><th>Balance</th><th>Flags</th></tr></thead>
              <tbody>{shown.map((t: any) => <tr key={t.id} className={t.duplicate_of ? "bg-saffron-soft/40" : ""}>
                <td className="whitespace-nowrap text-xs">{fmtTime(t.datetime_utc).slice(0, 16)}{t.time_precision === "ambiguous" && <span className="badge ml-1 bg-saffron-soft text-warn">ambiguous</span>}<div className="mono text-[10px] text-ink-muted">raw: {t.datetime_raw}</div></td>
                <td className="mono text-xs">{t.account_ref}</td>
                <td><span className={`badge ${t.direction === "debit" ? "bg-saffron-soft text-warn" : t.direction === "credit" ? "bg-ok-soft text-ok" : "bg-panel"}`}>{t.direction}</span></td>
                <td className="whitespace-nowrap font-medium">{paise(t.amount_minor)}<div className="mono text-[10px] text-ink-muted">raw: {t.amount_raw}</div></td>
                <td className="mono text-xs">{t.counterparty_ref || <span className="text-ink-muted">missing</span>}{t.counterparty_name_raw && <div className="font-sans text-ink-muted">{t.counterparty_name_raw}</div>}</td>
                <td className="mono text-xs">{t.external_reference || "—"}</td><td className="text-xs">{t.channel}</td><td className="text-xs">{paise(t.balance_after_minor)}</td>
                <td className="text-xs warn">{t.warnings.map((w: string) => w.replace(/_/g, " ")).join(", ")}</td></tr>)}</tbody></table></div>
          </div>
        </div>
      </State>
    </Shell>
  );
}

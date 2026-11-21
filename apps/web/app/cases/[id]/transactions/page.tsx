"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime, paise } from "@/lib/api";

export default function TransactionsPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [txs, setTxs] = useState<any[] | null>(null);
  const [paths, setPaths] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  useEffect(() => {
    Promise.all([api(`/cases/${id}`), api(`/cases/${id}/transactions`), api(`/cases/${id}/paths`)]).then(([cc, tt, pp]) => { setC(cc); setTxs(tt); setPaths(pp); }).catch((e) => setError(e.message));
  }, [id]);
  const shown = (txs || []).filter((t) => !filter || JSON.stringify(t).toLowerCase().includes(filter.toLowerCase()));
  const chart = Object.entries(paths?.features || {}).map(([a, f]: any) => ({ account: a.slice(-6), inflow: f.total_in_minor / 100, outflow: f.total_out_minor / 100 })).slice(0, 12);
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Transactions and fund flow">
      <State loading={!txs && !error} error={error} empty={txs && txs.length === 0 ? "No transactions parsed yet. Upload a CSV/XLSX statement." : null}>
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <div className="card">
              <h2 className="mb-2 font-semibold">Reconstructed fund paths <span className="text-xs font-normal text-ink-muted">(derived; time-ordered; sub-paths pruned)</span></h2>
              {paths?.paths?.length ? <ol className="space-y-1 text-sm">{paths.paths.slice(0, 10).map((p: any, i: number) => <li key={i} className="rounded bg-[#f6f8fa] p-2"><span className="badge bg-[#eef1f4]">{p.hop_count} hop</span> {p.accounts.join(" → ")} <span className="text-xs text-ink-muted">entry {paise(p.total_in_minor)} · exit {paise(p.exit_amount_minor)}{p.time_uncertain && " · time uncertain"}</span></li>)}</ol> : <div className="text-sm text-ink-muted">No multi-hop path found yet.</div>}
              {paths?.reconciliation?.length > 0 && <div className="mt-3 text-xs"><div className="label">Balance reconciliation</div>{paths.reconciliation.map((r: any) => <div key={r.parse_run_id} className={r.mismatch_minor ? "text-[#8a1c1c]" : "text-ink-muted"}>run {r.parse_run_id.slice(0, 8)}: expected {paise(r.expected_last_minor)}, stated {paise(r.last_balance_minor)}, mismatch {paise(r.mismatch_minor)}</div>)}</div>}
            </div>
            <div className="card">
              <h2 className="mb-2 font-semibold">Inflow / outflow by account (₹)</h2>
              <div style={{ height: 220 }}><ResponsiveContainer><BarChart data={chart}><XAxis dataKey="account" fontSize={11} /><YAxis fontSize={11} /><Tooltip /><Bar dataKey="inflow" fill="#1f5fa8" /><Bar dataKey="outflow" fill="#b7791f" /></BarChart></ResponsiveContainer></div>
              <h3 className="mt-2 text-sm font-semibold">Triage signals (rules; requires review)</h3>
              <ul className="text-xs">{Object.entries(paths?.features || {}).filter(([, f]: any) => f.triage.reasons.length).map(([a, f]: any) => <li key={a}><span className="font-mono">{a}</span> — {f.triage.label.replace(/_/g, " ")} ({f.triage.reasons.join(", ")})</li>)}</ul>
            </div>
          </div>
          <input className="input max-w-sm" placeholder="Filter rows…" aria-label="Filter transactions" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <div className="card overflow-x-auto p-0"><table className="data"><thead><tr><th>When (UTC)</th><th>Raw date</th><th>Account</th><th>Dir</th><th>Amount</th><th>Raw amount</th><th>Counterparty</th><th>Ref</th><th>Channel</th><th>Balance</th><th>Flags</th></tr></thead>
            <tbody>{shown.map((t) => <tr key={t.id} className={t.duplicate_of ? "bg-[#fdf3e0]" : ""}><td className="whitespace-nowrap text-xs">{fmtTime(t.datetime_utc)}{t.time_precision === "ambiguous" && <span className="badge ml-1 bg-[#fdf3e0] text-[#8a5a0f]">ambiguous</span>}</td><td className="text-xs">{t.datetime_raw}</td><td className="font-mono text-xs">{t.account_ref}</td><td>{t.direction}</td><td>{paise(t.amount_minor)}</td><td className="text-xs">{t.amount_raw}</td><td className="font-mono text-xs">{t.counterparty_ref || "—"}{t.counterparty_name_raw && <div className="text-ink-muted">{t.counterparty_name_raw}</div>}</td><td className="font-mono text-xs">{t.external_reference || "—"}</td><td>{t.channel}</td><td>{paise(t.balance_after_minor)}</td><td className="text-xs text-[#8a5a0f]">{t.warnings.join(", ")}</td></tr>)}</tbody></table></div>
        </div>
      </State>
    </Shell>
  );
}

"use client";

/** Start a money trail from the victim's own transaction reference.
 *
 * An investigator starts with one complaint carrying one UTR. Where the reference matches more than one row, every
 * candidate is shown and the investigator chooses: the system never picks, because the wrong origin invents a trail.
 */
import Link from "next/link";
import { FormEvent, useState } from "react";
import CasePage from "@/components/CasePage";
import { Dir, KV, Limitations, Money, Section, State, Table, Toast, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

export default function UtrTracePage() {
  return (
    <CasePage
      title="Start a Money-Trail Investigation"
      subtitle="Begin from the victim's own transaction reference. Every candidate row is shown with the file and cell it came from; where a reference is ambiguous you choose the originating transaction."
      pageKey="utr-trace"
      wide
    >
      {(c, id) => <Body id={id} />}
    </CasePage>
  );
}

function Body({ id }: { id: string }) {
  const [form, setForm] = useState({ reference: "", amount: "", account_ref: "", on_date: "" });
  const [search, setSearch] = useState<any>(null);
  const [trace, setTrace] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function runSearch(e: FormEvent) {
    e.preventDefault();
    setMsg(null); setTrace(null); setBusy(true);
    try {
      const body: any = {
        reference: form.reference.trim() || null,
        amount_minor: form.amount.trim() ? Math.round(parseFloat(form.amount) * 100) : null,
        account_ref: form.account_ref.trim() || null,
        on_date: form.on_date || null,
      };
      setSearch(await api(`/cases/${id}/utr/search`, { method: "POST", body: JSON.stringify(body) }));
    } catch (err: any) { setMsg(err.message); }
    finally { setBusy(false); }
  }

  async function runTrace(txId: string) {
    setMsg(null); setBusy(true);
    try { setTrace(await api(`/cases/${id}/utr/trace/${txId}`)); }
    catch (err: any) { setMsg(err.message); }
    finally { setBusy(false); }
  }

  // A reference matching a row is a search outcome, not an evidence level: an exact match is not corroboration.
  const statusTone: Record<string, string> = {
    exact_single: "bg-ok-soft text-ok", ambiguous: "bg-saffron-soft text-warn",
    partial_only: "bg-saffron-soft text-warn", not_found: "bg-panel text-ink",
  };

  return (
    <div className="space-y-4">
      <Toast msg={msg} onClose={() => setMsg(null)} />

      <Section title="What the complaint says" hint="Supply whatever the victim reported. A reference alone is usually enough; an amount, account or date narrows an ambiguous one.">
        <form onSubmit={runSearch} className="grid gap-2 text-sm md:grid-cols-4">
          <label className="md:col-span-2"><span className="label">Transaction reference / UTR</span>
            <input className="input" value={form.reference} placeholder="e.g. SYNUTR000001" onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          </label>
          <label><span className="label">Amount (₹)</span>
            <input className="input" value={form.amount} inputMode="decimal" placeholder="18000.00" onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          </label>
          <label><span className="label">Date</span>
            <input className="input" type="date" value={form.on_date} onChange={(e) => setForm({ ...form, on_date: e.target.value })} />
          </label>
          <label className="md:col-span-2"><span className="label">Victim account, if known</span>
            <input className="input" value={form.account_ref} onChange={(e) => setForm({ ...form, account_ref: e.target.value })} />
          </label>
          <div className="flex items-end md:col-span-2">
            <button className="btn w-full justify-center" disabled={busy}>{busy ? "Searching…" : <>Search the supplied statements <I.search /></>}</button>
          </div>
        </form>
      </Section>

      {search && (
        <Section title="Candidates" hint={search.next_step}
          actions={<span className={`badge ${statusTone[search.status] || "bg-panel text-ink"}`}>{search.status.replace(/_/g, " ")}</span>}>
          {search.exact_matches.length === 0 && search.partial_matches.length === 0 && (
            <div className="inset p-4 text-sm muted">No row in the supplied statements carries this reference.</div>
          )}
          {search.exact_matches.length > 0 && (
            <>
              <div className="label">Exact reference matches</div>
              <Table dense cols={["Reference", "Amount", "Direction", "Account", "Counterparty", "Time", "Source", ""]}
                rows={search.exact_matches.map((m: any) => [
                  <span key="r" className="mono">{m.reference}</span>,
                  <Money key="a" v={m.amount_minor} />,
                  <Dir key="d" v={m.direction} />,
                  <span key="ac" className="mono">{m.account_ref}</span>,
                  <span key="cp" className="mono">{m.counterparty_ref || "—"}</span>,
                  <When key="t" v={m.event_time} />,
                  <span key="s" className="text-xs muted">{m.source_file?.name}{m.source_locator?.row ? ` row ${m.source_locator.row}` : ""}</span>,
                  <button key="b" className="btn-secondary !py-1" onClick={() => runTrace(m.transaction_id)}>Trace from here</button>,
                ])} />
            </>
          )}
          {search.partial_matches.length > 0 && (
            <div className="mt-3">
              <div className="label">Near matches, not the transaction</div>
              <Table dense cols={["Why it is here", "Reference", "Amount", "Account", "Time", ""]}
                rows={search.partial_matches.map((m: any) => [
                  <span key="w" className="text-xs">{m.match}</span>,
                  <span key="r" className="mono">{m.reference || "—"}</span>,
                  <Money key="a" v={m.amount_minor} />,
                  <span key="ac" className="mono">{m.account_ref}</span>,
                  <When key="t" v={m.event_time} />,
                  <button key="b" className="btn-secondary !py-1" onClick={() => runTrace(m.transaction_id)}>Trace from here</button>,
                ])} />
            </div>
          )}
          {search.mentioned_in_documents?.length > 0 && (
            <div className="mt-3">
              <div className="label">The same reference appears in a document</div>
              <p className="mb-1 text-xs muted">What the victim was told, which is not the same as a bank record.</p>
              <ul className="space-y-1 text-xs">
                {search.mentioned_in_documents.map((m: any) => (
                  <li key={m.evidence_item_id} className="inset p-2"><span className="font-medium">{m.source_type}</span> <span className="mono">{JSON.stringify(m.locator)}</span><div className="mt-0.5">{m.excerpt}</div></li>
                ))}
              </ul>
            </div>
          )}
          <Limitations items={search.limitations} />
        </Section>
      )}

      {trace && (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            <div className="metric"><div className="label mb-0">Hops followed</div><div className="metric-value mt-2">{trace.shape.hops}</div><div className="mt-1 text-xs muted">within {trace.shape.chaining_window_hours}h chaining</div></div>
            <div className="metric"><div className="label mb-0">Unresolved ends</div><div className="metric-value mt-2">{trace.unresolved.length}</div><div className="mt-1 text-xs muted">each names what would continue it</div></div>
            <div className="metric"><div className="label mb-0">Splits observed</div><div className="metric-value mt-2">{trace.shape.splits_observed}</div><div className="mt-1 text-xs muted">one credit leaving as several</div></div>
            <div className="metric"><div className="label mb-0">Merges observed</div><div className="metric-value mt-2">{trace.shape.merges_observed}</div><div className="mt-1 text-xs muted">several credits funding one</div></div>
          </div>

          <Section title="The trail" hint="Each hop carries the transaction, the file it came from and the cell inside it.">
            <Table cols={["Hop", "From", "To", "Amount", "Reference", "Time", "Evidence"]}
              rows={trace.hops.map((h: any) => [
                <span key="h" className="num font-semibold">{h.hop}</span>,
                <span key="f" className="mono text-xs">{h.from_account}</span>,
                <span key="t" className="mono text-xs">{h.to_account}</span>,
                <Money key="a" v={h.amount_minor} />,
                <span key="r" className="mono text-xs">{h.reference || "—"}</span>,
                // The vocabulary is second|minute|day|month|unknown|ambiguous. Only the coarse and unknown values are
                // worth flagging: a timestamp recorded to the second or the minute pins the hop well enough to chain it.
                <span key="tm" className="flex flex-wrap items-center gap-1 text-xs"><When v={h.event_time} />
                  {!["second", "minute"].includes(h.time_precision) && (
                    <span className="badge bg-saffron-soft text-warn" title="the statement did not give a precise time, so the position of this hop in the sequence is uncertain">{h.time_precision}</span>
                  )}</span>,
                <span key="e" className="text-xs muted">{h.source_file?.name || "—"}{h.source_locator?.row ? ` row ${h.source_locator.row}` : ""}{h.corroborated ? " · corroborated" : ""}</span>,
              ])} />
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Where the trail stops" hint="A stop is a question for the next evidence request, not a dead end.">
              {trace.unresolved.length === 0 ? <p className="text-sm muted">Nothing unresolved on this trail.</p> : (
                <ul className="space-y-2 text-sm">
                  {trace.unresolved.map((u: any, i: number) => (
                    <li key={i} className="inset p-3">
                      <div className="mono text-xs">{u.account}</div>
                      <div className="mt-1">{u.reason}</div>
                      <div className="mt-1 text-xs muted"><span className="font-medium">Needed:</span> {u.needed}</div>
                    </li>
                  ))}
                </ul>
              )}
              <Link href={`/cases/${id}/ivoi`} className="btn-secondary mt-3">Rank the next evidence <I.arrow /></Link>
            </Section>

            <Section title="Accounts on the trail">
              <Table dense cols={["Account", "Role", "Own statement?", "Patterns"]}
                rows={trace.accounts.map((a: any) => [
                  <span key="m" className="mono text-xs" title={a.account_ref}>{a.masked}</span>,
                  a.role,
                  <span key="s" className={`badge ${a.has_own_statement ? "bg-ok-soft text-ok" : "bg-panel text-ink"}`}>{a.has_own_statement ? "supplied" : "not supplied"}</span>,
                  <Link key="p" href={`/cases/${id}/accounts`} className="text-xs text-accent-deep underline">typologies</Link>,
                ])} />
            </Section>
          </div>

          <div className="card text-sm">
            <span className="font-medium">{trace.next}</span>{" "}
            <Link href={`/cases/${id}/bounded-flow`} className="text-accent-deep underline">Open bounded fund provenance</Link>.
          </div>
          <Limitations items={trace.limitations} />
          <KV rows={[["Root transaction", <span key="r" className="mono">{trace.root.reference || trace.root.transaction_id}</span>],
                     ["Victim account", <span key="v" className="mono">{trace.root.victim_account}</span>],
                     ["First receiver", <span key="f" className="mono">{trace.root.first_receiver}</span>],
                     ["Trace version", trace.version]]} />
        </>
      )}

      <State loading={false} error={null}>{null}</State>
    </div>
  );
}

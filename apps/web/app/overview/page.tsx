"use client";

/** Investigation Command Centre. Pending human decisions come first, then the counts, then the registry.
 * Every item is derived from fields the case API actually returns; nothing here is estimated or scored. */
import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { MotionScene } from "@/components/motion";
import { Chip, Section, Stat, State, Table, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api, getUser, isDemo } from "@/lib/api";

type Priority = {
  caseId: string; caseTitle: string; synthetic: boolean;
  what: string; why: string; uncertain: string; action: string; href: string; tone: "warn" | "info";
};

/** Turn the recorded counts of one case into the decisions a person still has to make. */
function prioritiesFor(c: any, h: any): Priority[] {
  const base = { caseId: c.id, caseTitle: c.title, synthetic: c.is_synthetic };
  const out: Priority[] = [];
  if (!h) return out;
  if (h.findings_awaiting_review > 0) out.push({
    ...base, tone: "warn",
    what: `${h.findings_awaiting_review} candidate or stale relationship${h.findings_awaiting_review === 1 ? "" : "s"} await a decision`,
    why: "A candidate link is an explanation that fits the records, not an established fact. It must not reach a report until a person decides.",
    uncertain: "Shared infrastructure and similar names stay candidates whatever the graph looks like.",
    action: "Review candidates", href: `/cases/${c.id}/review`,
  });
  if (h.unresolved_warnings > 0) out.push({
    ...base, tone: "warn",
    what: `${h.unresolved_warnings} parser warning${h.unresolved_warnings === 1 ? "" : "s"} to check`,
    why: "Ambiguous dates, duplicate rows and balance breaks change what a reconstructed path is able to support.",
    uncertain: "A warning is information to check, not an error and not a finding.",
    action: "Open evidence integrity", href: `/cases/${c.id}/integrity`,
  });
  if (h.files_count === 0) out.push({
    ...base, tone: "info",
    what: "No evidence has been supplied yet",
    why: "Nothing can be reconstructed until statements, complaints or technical observations are in the case.",
    uncertain: "Absent records are unknown, never zero.",
    action: "Open evidence intake", href: `/cases/${c.id}/upload`,
  });
  else if (h.transactions_count === 0) out.push({
    ...base, tone: "info",
    what: "Files are stored but no transaction rows were parsed",
    why: "Either the documents carry no ledger rows, or a column mapping needs confirming before any path exists.",
    uncertain: "Until rows parse, coverage for this case is not supplied rather than empty.",
    action: "Check parsing", href: `/cases/${c.id}/upload`,
  });
  return out;
}

export default function OverviewPage() {
  const [cases, setCases] = useState<any[] | null>(null);
  const [heads, setHeads] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);
  const user = getUser();

  useEffect(() => {
    api("/cases").then(async (cs) => {
      setCases(cs);
      const h: Record<string, any> = {};
      await Promise.all(cs.slice(0, 8).map(async (c: any) => { try { h[c.id] = await api(`/cases/${c.id}`); } catch { /* ignore */ } }));
      setHeads(h);
    }).catch((e) => setError(e.message));
  }, []);

  const totals = Object.values(heads).reduce((a: any, h: any) => ({
    files: a.files + h.files_count, tx: a.tx + h.transactions_count, rels: a.rels + h.relationships_count, review: a.review + h.findings_awaiting_review,
  }), { files: 0, tx: 0, rels: 0, review: 0 });
  const priorities = (cases || []).flatMap((c: any) => prioritiesFor(c, heads[c.id]));
  const decisions = priorities.filter((p) => p.tone === "warn");

  return (
    <Shell title="Investigation Command Centre" subtitle="An operational overview of cases, evidence gaps and the investigative decisions still waiting on a person." pageKey="overview"
      primary={<Link href="/factory" className="btn"><I.factory /> Generate Operation Desert Mirage</Link>}>
      <State loading={!cases && !error} error={error}>
        {cases && (
          <div className="space-y-4">
            {isDemo(user) && (
              <div className="callout-warn text-sm"><I.shield className="shrink-0" />
                <div><span className="font-semibold">Synthetic demo workspace.</span> Isolated to this visitor and time-limited. Generate a case in the Synthetic Case Factory, or create an empty case and upload synthetic test files.</div>
              </div>
            )}

            <Section title="What needs a decision" hint={priorities.length
              ? "Each item says what happened, why it matters, what stays uncertain, and where to look next. Nothing here is decided automatically."
              : "Nothing is waiting on a human decision in the cases you can access."}>
              {priorities.length === 0 ? (
                <div className="inset p-4 text-sm muted">
                  No pending candidate relationships, parser warnings or empty cases.{" "}
                  {cases.length === 0 ? <Link href="/factory" className="underline">Generate a synthetic case</Link> : <Link href="/cases" className="underline">Open the case registry</Link>} to continue.
                </div>
              ) : (
                <ol className="space-y-2.5">
                  {priorities.slice(0, 6).map((p, i) => (
                    <li key={`${p.caseId}-${i}`} className={`inset rise p-3.5 ${i < 3 ? `rise-${i + 1}` : ""}`}>
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className={`badge ${p.tone === "warn" ? "lvl-candidate" : "lvl-derived"}`}>{p.tone === "warn" ? "needs decision" : "evidence gap"}</span>
                            <Link href={`/cases/${p.caseId}`} className="text-xs font-medium text-accent-deep hover:underline">{p.caseTitle}</Link>
                            {p.synthetic && <Chip v="synthetic" />}
                          </div>
                          <p className="mt-1.5 text-[15px] font-semibold leading-snug">{p.what}</p>
                          <p className="mt-1 max-w-3xl text-[13px] leading-relaxed muted">{p.why}</p>
                          <p className="mt-1 max-w-3xl text-[13px] leading-relaxed muted"><span className="font-medium">Still uncertain:</span> {p.uncertain}</p>
                        </div>
                        <Link href={p.href} className="btn-secondary shrink-0">{p.action} <I.arrow /></Link>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              {priorities.length > 6 && <p className="mt-2 text-xs muted">{priorities.length - 6} further item(s) across your cases. <Link href="/queue" className="underline">Open the work queue</Link>.</p>}
            </Section>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Stat label="Cases" value={cases.length} href="/cases" hint="you can access" />
              <Stat label="Awaiting review" value={totals.review} hint="candidate or stale links needing a person" tone={totals.review ? "warn" : "ok"} href="/queue" />
              <Stat label="Evidence files" value={totals.files} hint="hashed and parsed across recent cases" />
              <Stat label="Transactions" value={totals.tx} hint="parsed rows with raw text kept" />
              <Stat label="Relationships" value={totals.rels} hint="each carrying an evidence level" />
            </div>

            <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
              <Section title="Recent cases" actions={<Link href="/cases" className="btn-secondary">Case registry</Link>}>
                <Table cols={["Case", "Data", "Files", "Transactions", "Review", "Updated"]}
                  empty={<span>No cases yet. <Link href="/factory" className="underline">Generate a synthetic case</Link> or <Link href="/cases/new" className="underline">create one</Link>.</span>}
                  rows={cases.slice(0, 8).map((c: any) => {
                    const h = heads[c.id];
                    return [
                      <Link key="t" href={`/cases/${c.id}`} className="font-medium text-accent-deep hover:underline">{c.title}</Link>,
                      <Chip key="d" v={c.is_synthetic ? "synthetic" : "verified"} title={c.is_synthetic ? "Synthetic" : "Uploaded evidence"} />,
                      <span key="f" className="num">{h?.files_count ?? "—"}</span>,
                      <span key="x" className="num">{h?.transactions_count ?? "—"}</span>,
                      h?.findings_awaiting_review ? <span key="r" className="warn num font-semibold">{h.findings_awaiting_review}</span> : <span key="r" className="num muted">0</span>,
                      <When key="u" v={c.updated_at} />,
                    ];
                  })} />
              </Section>
              <div className="space-y-3">
                <Section title="Guiding sequence" hint="Ingest → validate → reconstruct → challenge → identify missing evidence → compare scenarios → prepare authorised next steps → reproduce.">
                  <ol className="list-decimal space-y-1 pl-5 text-sm">
                    {["Evidence intake", "Integrity and coverage", "Money trail and bounded provenance", "CounterProof", "Next-best evidence", "Simulators", "Evidence acquisition drafts", "Proof certificate and report"].map((x) => <li key={x}>{x}</li>)}
                  </ol>
                  <p className="mt-2 text-xs muted">Select a case in the left panel to light up the case-scoped pages.</p>
                </Section>
                <MotionScene scene="network_correlation" height={130} />
              </div>
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

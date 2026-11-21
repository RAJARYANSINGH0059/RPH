"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { MotionScene } from "@/components/motion";
import { Chip, Section, Stat, State, Table, When } from "@/components/ui";
import { I } from "@/components/icons";
import { api, getUser, isDemo } from "@/lib/api";

export default function OverviewPage() {
  const [cases, setCases] = useState<any[] | null>(null);
  const [heads, setHeads] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);
  const user = getUser();
  useEffect(() => {
    api("/cases").then(async (cs) => { setCases(cs); const h: Record<string, any> = {}; await Promise.all(cs.slice(0, 8).map(async (c: any) => { try { h[c.id] = await api(`/cases/${c.id}`); } catch { /* ignore */ } })); setHeads(h); }).catch((e) => setError(e.message));
  }, []);
  const totals = Object.values(heads).reduce((a: any, h: any) => ({ files: a.files + h.files_count, tx: a.tx + h.transactions_count, rels: a.rels + h.relationships_count, review: a.review + h.findings_awaiting_review }), { files: 0, tx: 0, rels: 0, review: 0 });
  return (
    <Shell title="Overview" subtitle="An operational summary of your workspace. Pick a case to open its workbench; every feature lives in the left navigation." pageKey="overview"
      primary={<Link href="/factory" className="btn"><I.factory /> Generate Operation Desert Mirage</Link>}>
      <State loading={!cases && !error} error={error}>
        {cases && (
          <div className="space-y-4">
            {isDemo(user) && <div className="callout-warn text-sm"><I.shield className="shrink-0" /><div><span className="font-semibold">Synthetic demo workspace.</span> Isolated to this visitor and time-limited. Generate a case in the Synthetic Case Factory, or create an empty case and upload synthetic test files.</div></div>}
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <Stat label="Cases" value={cases.length} href="/cases" hint="you can access" />
              <Stat label="Evidence files" value={totals.files} hint="across recent cases" />
              <Stat label="Transactions" value={totals.tx} hint="parsed rows" />
              <Stat label="Relationships" value={totals.rels} hint="with evidence levels" />
              <Stat label="Awaiting review" value={totals.review} hint="candidate / stale links" tone={totals.review ? "warn" : "ok"} href="/queue" />
            </div>
            <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
              <Section title="Recent cases" actions={<Link href="/cases" className="btn-secondary">Case registry</Link>}>
                <Table cols={["Case", "Data", "Files", "Transactions", "Review", "Updated"]} empty={<span>No cases yet. <Link href="/factory" className="underline">Generate a synthetic case</Link> or <Link href="/cases/new" className="underline">create one</Link>.</span>}
                  rows={cases.slice(0, 8).map((c: any) => { const h = heads[c.id]; return [<Link key="t" href={`/cases/${c.id}`} className="font-medium text-accent-deep hover:underline">{c.title}</Link>, <Chip key="d" v={c.is_synthetic ? "synthetic" : "verified"} title={c.is_synthetic ? "synthetic" : "uploaded"} />, h?.files_count ?? "…", h?.transactions_count ?? "…", h ? (h.findings_awaiting_review ? <span className="warn">{h.findings_awaiting_review}</span> : "0") : "…", <When key="w" v={c.updated_at} />]; })} />
              </Section>
              <div className="space-y-3">
                <Section title="Guiding sequence" hint="Ingest → Validate → Reconstruct → Challenge → Identify missing evidence → Compare scenarios → Prepare authorised next steps → Reproduce.">
                  <ol className="list-decimal space-y-1 pl-5 text-sm">{[["Evidence Intake", "/cases"], ["Integrity & coverage", "/cases"], ["Money trail & bounded provenance", "/cases"], ["CounterProof", "/cases"], ["Next-best evidence", "/cases"], ["Simulators", "/cases"], ["Evidence acquisition drafts", "/cases"], ["Proof certificate & replay", "/cases"]].map(([l]) => <li key={l}>{l}</li>)}</ol>
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

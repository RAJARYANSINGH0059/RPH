"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { State, Table } from "@/components/ui";
import { api } from "@/lib/api";

export default function Page() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { api("/cases").then(async (cs) => { const out: any[] = []; for (const c of cs.slice(0, 12)) { try { const h = await api(`/cases/${c.id}`); out.push({ ...c, ...h }); } catch { /* skip */ } } setRows(out); }).catch((e) => setError(e.message)); }, []);
  return (
    <Shell title="Investigation Work Queue" subtitle="What needs a human decision next, per case: candidate links to review, parser warnings to check, missing statements to request.">
      <State loading={!rows && !error} error={error}>
        {rows && <Table cols={["Case", "Awaiting review", "Parser warnings", "Files / transactions", "Next step"]} rows={rows.map((c: any) => [<Link key="t" href={`/cases/${c.id}`} className="font-medium text-accent-deep hover:underline">{c.title}</Link>, c.findings_awaiting_review ? <span className="warn">{c.findings_awaiting_review}</span> : "0", c.unresolved_warnings, `${c.files_count} / ${c.transactions_count}`,
          c.files_count === 0 ? <Link key="n" href={`/cases/${c.id}/upload`} className="underline">Upload evidence</Link> : c.findings_awaiting_review ? <Link key="n" href={`/cases/${c.id}/review`} className="underline">Review {c.findings_awaiting_review} link(s)</Link> : <Link key="n" href={`/cases/${c.id}/ivoi`} className="underline">Check next-best evidence</Link>])} empty="No cases." />}
      </State>
    </Shell>
  );
}

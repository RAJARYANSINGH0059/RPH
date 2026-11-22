"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Chip, State, Table } from "@/components/ui";
import { api, getUser, isDemo } from "@/lib/api";

export default function Page() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Every case is fetched at once, and the two analyses per case together: serially this took about four seconds.
  useEffect(() => { (async () => {
    try {
      const cs = await api("/cases");
      const per = await Promise.all(cs.slice(0, 8).map(async (c: any) => {
        const out: any[] = [];
        try {
          const [adv, cov] = await Promise.all([api(`/cases/${c.id}/adversary?limit=200`), api(`/cases/${c.id}/coverage`)]);
          for (const [k, n] of Object.entries(adv.by_state)) if (["contested", "contradicted", "stale"].includes(k)) out.push({ case: c, kind: `${n} relationship(s) ${k}`, href: `/cases/${c.id}/counterproof`, level: k });
          for (const w of cov.negative_claim_warnings) out.push({ case: c, kind: w.warning, href: `/cases/${c.id}/coverage-ivoi`, level: "unresolved", detail: w.needed });
        } catch { /* a case that cannot be analysed is skipped, not reported as an alert */ }
        return out;
      }));
      setItems(per.flat());
    } catch (e: any) { setError(e.message); }
  })(); }, []);
  const demo = isDemo(getUser());
  return (
    <Shell title="Alerts and Notifications" subtitle="Contradictions, stale observations and unresolved path ends across your recent cases. Demo sessions expire automatically after four hours.">
      <State loading={!items && !error} error={error}>
        {items && <div className="space-y-3">{demo && <div className="callout-warn text-sm">Demo session: isolated synthetic workspace, expires automatically; expired workspaces are removed.</div>}
          <Table cols={["Case", "Alert", "Level", "Open"]} rows={items.map((a: any) => [a.case.title, <span key="k">{a.kind}{a.detail ? <span className="text-xs muted"> — {a.detail}</span> : null}</span>, <Chip key="l" v={a.level} />, <Link key="h" href={a.href.replace("/coverage-ivoi", "/ivoi")} className="underline">open</Link>])} empty="No alerts in your recent cases." /></div>}
      </State>
    </Shell>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Chip, State, Table } from "@/components/ui";
import { api, getUser, isDemo } from "@/lib/api";

export default function Page() {
  const [items, setItems] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<number | null>(null);
  // Each case contributes as soon as its own analyses return, so the page paints with what has arrived instead of
  // waiting on the slowest call. The relationship challenge is heavy on a free-plan instance and can take seconds.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const cs = await api("/cases");
        if (!alive) return;
        if (!cs.length) { setItems([]); setPending(0); return; }
        setItems([]);
        setPending(Math.min(cs.length, 8));
        for (const c of cs.slice(0, 8)) {
          void (async () => {
            const out: any[] = [];
            try {
              const [adv, cov] = await Promise.all([api(`/cases/${c.id}/adversary?limit=200`), api(`/cases/${c.id}/coverage`)]);
              for (const [k, n] of Object.entries(adv.by_state)) if (["contested", "contradicted", "stale"].includes(k)) out.push({ case: c, kind: `${n} relationship(s) ${k}`, href: `/cases/${c.id}/counterproof`, level: k });
              for (const w of cov.negative_claim_warnings) out.push({ case: c, kind: w.warning, href: `/cases/${c.id}/coverage-ivoi`, level: "unresolved", detail: w.needed });
            } catch { /* a case that cannot be analysed is skipped, not reported as an alert */ }
            if (!alive) return;
            setItems((prev) => [...(prev || []), ...out]);
            setPending((n) => (n ?? 1) - 1);
          })();
        }
      } catch (e: any) { if (alive) setError(e.message); }
    })();
    return () => { alive = false; };
  }, []);
  const demo = isDemo(getUser());
  return (
    <Shell title="Alerts and Notifications" subtitle="Contradictions, stale observations and unresolved path ends across your recent cases. Demo sessions expire automatically after four hours.">
      {pending !== null && pending > 0 && <p className="mb-2 text-xs muted" role="status">Checking {pending} more case(s). Relationship challenges are recomputed on each visit and take a few seconds on the free-plan API.</p>}
      <State loading={!items && !error} error={error}>
        {items && <div className="space-y-3">{demo && <div className="callout-warn text-sm">Demo session: isolated synthetic workspace, expires automatically; expired workspaces are removed.</div>}
          <Table cols={["Case", "Alert", "Level", "Open"]} rows={items.map((a: any) => [a.case.title, <span key="k">{a.kind}{a.detail ? <span className="text-xs muted"> — {a.detail}</span> : null}</span>, <Chip key="l" v={a.level} />, <Link key="h" href={a.href.replace("/coverage-ivoi", "/ivoi")} className="underline">open</Link>])} empty="No alerts in your recent cases." /></div>}
      </State>
    </Shell>
  );
}

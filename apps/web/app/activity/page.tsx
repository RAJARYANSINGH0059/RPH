"use client";

import Shell from "@/components/Shell";
import { State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  const { data, error, reload } = useApi<any[]>("/audit/mine?limit=150");
  return (
    <Shell title="Recent Activity" subtitle="Your latest audited actions across all cases you can access.">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <Table dense cols={["When", "Action", "Case", "Target", "Detail"]} rows={data.map((a: any) => [<When key="w" v={a.created_at} />, <span key="a" className="mono">{a.action}</span>, <span key="c" className="mono text-xs">{a.case_id?.slice(0, 8) || "—"}</span>, <span key="t" className="text-xs">{a.target_type || ""} {a.target_id?.slice(0, 8) || ""}</span>, <span key="d" className="text-xs muted">{JSON.stringify(a.detail).slice(0, 140)}</span>])} empty="No activity yet." />}
      </State>
    </Shell>
  );
}

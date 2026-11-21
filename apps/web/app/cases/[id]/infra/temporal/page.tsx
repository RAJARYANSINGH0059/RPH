"use client";

import { useState } from "react";
import ListPage from "@/components/ListPage";
import { Chip, Limitations, Section, State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  return <ListPage title="Temporal Infrastructure Intelligence" subtitle="Explicit time intervals for every record and claim: raw source time, declared timezone, normalised UTC, precision, interval. Claims are compatible only when intervals overlap under the declared tolerance. Current-only observations cannot support historical claims." pageKey="temporal">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const [from, setFrom] = useState(""); const [to, setTo] = useState("");
  const q = `/cases/${id}/temporal?${from ? `window_from=${from}T00:00:00Z&` : ""}${to ? `window_to=${to}T23:59:59Z` : ""}`;
  const { data, error, reload } = useApi<any>(q, [from, to]);
  return (
    <div className="space-y-3">
      <div className="card flex flex-wrap items-center gap-3 text-sm"><label>Window from <input type="date" className="input !w-auto" value={from} onChange={(e) => setFrom(e.target.value)} /></label><label>to <input type="date" className="input !w-auto" value={to} onChange={(e) => setTo(e.target.value)} /></label><button className="btn-secondary" onClick={() => { setFrom(""); setTo(""); }}>Clear</button>{data && <span className="ml-auto text-xs muted">included {data.window.included.length} · excluded {data.window.excluded.length} · unknown time {data.window.unknown_time.length}</span>}</div>
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && (
          <>
            <Section title={`Claims vs transaction window (${data.claims.length})`} hint={`Transaction window ${data.transaction_window.start?.slice(0, 10) || "?"} → ${data.transaction_window.end?.slice(0, 10) || "?"}; tolerance ${data.rules.transaction_vs_observation_tolerance_days} days.`}>
              <Table dense cols={["Relationship", "From → To", "Interval", "Verdict", "Current-only", "Detail"]} rows={data.claims.map((c: any) => [<span key="t" className="mono">{c.type}</span>, <span key="f" className="mono">{c.from} → {c.to}</span>, <span key="i" className="text-xs">{c.interval.start?.slice(0, 16) || "?"} → {c.interval.end?.slice(0, 16) || "?"}</span>, <Chip key="v" v={c.verdict === "temporally_compatible" ? "corroborated" : c.verdict === "temporal_contradiction" ? "contradicted" : c.verdict === "cannot_support_historical_claim" ? "stale" : "unresolved"} title={c.verdict} />, c.current_only ? "yes" : "no", <span key="d" className="text-xs muted">{c.compatibility.note || c.compatibility.reason || (c.compatibility.compatible === false ? `gap ${c.compatibility.gap_hours} h` : "")}</span>])} />
            </Section>
            <Section title={`Records (${data.records.length})`} hint="Source time text, declared timezone and normalised instant are kept side by side.">
              <Table dense cols={["Kind", "Label", "Source time", "Timezone", "Normalised UTC", "Precision", "Interval", "Freshness", "Review"]} rows={data.records.slice(0, 300).map((r: any) => [r.kind, <span key="l" className="max-w-[260px] truncate inline-block">{r.label}</span>, <span key="s" className="mono text-xs">{r.source_time_raw || "—"}</span>, <span key="z" className="text-xs">{r.source_timezone}</span>, <When key="n" v={r.normalised_utc} />, <Chip key="p" v={r.interval.precision === "ambiguous" ? "candidate" : r.interval.known ? "observed" : "unresolved"} title={r.interval.precision} />, <span key="i" className="text-xs">{r.interval.known ? `${r.interval.start?.slice(5, 16)} → ${r.interval.end?.slice(5, 16)}` : "unknown"}</span>, <span key="f" className="text-xs">{r.freshness}</span>, <span key="a" className="text-xs warn">{r.review_action || ""}</span>])} />
            </Section>
            <Limitations items={data.limitations} />
          </>
        )}
      </State>
    </div>
  );
}

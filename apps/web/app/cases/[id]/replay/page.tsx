"use client";

import { useState } from "react";
import ListPage from "@/components/ListPage";
import { MotionScene } from "@/components/motion";
import { KV, Limitations, Section, State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  return <ListPage title="Investigation Replay" subtitle="What was known at a point in time, from append-only ingestion timestamps and the audit log. Move the cursor or compare two moments; no timestamp is invented." pageKey="replay">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const base = useApi<any>(`/cases/${id}/twin/replay`);
  const events = base.data?.audit_timeline || [];
  const [i, setI] = useState<number>(-1);
  const [j, setJ] = useState<number>(-1);
  const at = i >= 0 && events[i] ? events[i].at : null;
  const cmp = j >= 0 && events[j] ? events[j].at : null;
  const snap = useApi<any>(base.data ? `/cases/${id}/twin/replay?${at ? `at=${encodeURIComponent(at)}&` : ""}${cmp ? `compare_to=${encodeURIComponent(cmp)}` : ""}` : null, [at, cmp, !!base.data]);
  return (
    <State loading={base.loading} error={base.error} onRetry={base.reload}>
      {base.data && (
        <div className="space-y-3">
          <div className="card text-sm"><div className="flex flex-wrap items-center gap-3"><label className="flex-1">Cursor (audit event {i < 0 ? "latest" : i + 1} of {events.length}) <input type="range" className="w-full" min={-1} max={events.length - 1} value={i} onChange={(e) => setI(Number(e.target.value))} aria-label="As-of cursor" /></label><div className="flex gap-1"><button className="btn-secondary !py-1" onClick={() => setI((x) => Math.max(-1, x - 1))}>◀ step</button><button className="btn-secondary !py-1" onClick={() => setI((x) => Math.min(events.length - 1, x + 1))}>step ▶</button><button className="btn-secondary !py-1" onClick={() => setI(-1)}>now</button></div></div>
            <label className="mt-2 block text-xs">Compare to (optional) <select className="input !w-auto !py-0.5" value={j} onChange={(e) => setJ(Number(e.target.value))}><option value={-1}>—</option>{events.map((e: any, k: number) => <option key={e.id} value={k}>{k + 1}. {e.at.slice(0, 19)} {e.action}</option>)}</select></label>
            <div className="mt-1 text-xs muted">As of: {at ? at.slice(0, 19) : "now"} · the cursor moves only when you scrub or step.</div></div>
          <State loading={snap.loading} error={snap.error}>
            {snap.data && (
              <div className="grid gap-3 lg:grid-cols-2">
                <Section title="Known at the cursor"><KV rows={[["Files", String(snap.data.snapshot.files)], ["Events", String(snap.data.snapshot.events)], ["Relationships", String(snap.data.snapshot.relationships)], ["By level", Object.entries(snap.data.snapshot.relationships_by_level || {}).map(([k, v]: [any, any]) => `${k} ${v}`).join(", ") || "—"], ["Open uncertainties", String(snap.data.snapshot.uncertainties.length)]]} /><ul className="mt-2 list-disc pl-5 text-xs">{snap.data.snapshot.uncertainties.slice(0, 6).map((u: string) => <li key={u}>{u}</li>)}</ul></Section>
                {snap.data.compare ? <Section title={`Compared to ${snap.data.compare.as_of?.slice(0, 19)}`}><KV rows={[["Changed", Object.entries(snap.data.compare.changed).map(([k, v]: [string, any]) => `${k}: ${v[0]} → ${v[1]}`).join("; ") || "no change"], ["Uncertainties resolved", snap.data.compare.uncertainties_resolved.join("; ") || "—"], ["New uncertainties", snap.data.compare.uncertainties_new.join("; ") || "—"]]} /></Section> : <MotionScene scene="investigation_timeline" height={150} />}
              </div>
            )}
          </State>
          <Section title={`Audit timeline (${events.length})`}><Table dense cols={["#", "When", "Action", "Target", "Detail"]} rows={events.map((e: any, k: number) => [k + 1, <When key="w" v={e.at} />, <span key="a" className="mono">{e.action}</span>, <span key="t" className="text-xs">{e.target_type || ""} {e.target_id?.slice(0, 8) || ""}</span>, <span key="d" className="text-xs muted">{JSON.stringify(e.detail).slice(0, 120)}</span>])} /></Section>
          <Limitations items={base.data.limitations} />
        </div>
      )}
    </State>
  );
}

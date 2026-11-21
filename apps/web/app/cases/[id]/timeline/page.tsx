"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime } from "@/lib/api";

const FAMILIES = ["transaction", "complaint", "url", "dns", "hosting", "registration", "technical"];
const COLORS: Record<string, string> = { transaction: "#1f5fa8", complaint: "#6c5ce7", url: "#c0392b", dns: "#8e44ad", hosting: "#5d6d7e", registration: "#d35400", technical: "#7b8794" };
const WHAT: Record<string, string> = { transaction: "money movements from statements", complaint: "indicators mentioned in documents", url: "URLs and domains mentioned", dns: "domain → IP observations", hosting: "IP → provider observations", registration: "domain registration observations", technical: "other technical notes" };

export default function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [events, setEvents] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fams, setFams] = useState<string[]>(FAMILIES);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/timeline`)]).then(([cc, ev]) => { setC(cc); setEvents(ev); }).catch((e) => setError(e.message)); }, [id]);
  const shown = useMemo(() => (events || []).filter((e) => fams.includes(e.family)), [events, fams]);
  const groups = useMemo(() => {
    const m = new Map<string, any[]>();
    shown.forEach((e) => { const k = e.time ? e.time.slice(0, 10) : "Unknown time"; m.set(k, [...(m.get(k) || []), e]); });
    return Array.from(m.entries());
  }, [shown]);
  const present = FAMILIES.filter((f) => events?.some((e) => e.family === f));
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Timeline" subtitle="All dated evidence on one axis, grouped by day. Uncertain times are marked, never guessed." pageKey="timeline" step="graph">
      <State loading={!events && !error} error={error} empty={events && events.length === 0 ? "No dated evidence yet." : null}>
        <div className="card mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="label mb-0">Show</span>
          {present.map((f) => <button key={f} className={`chip ${fams.includes(f) ? "chip-on" : ""}`} title={WHAT[f]} onClick={() => setFams(fams.includes(f) ? fams.filter((x) => x !== f) : [...fams, f])}><span style={{ color: COLORS[f] }}>●</span>{f} ({events?.filter((e) => e.family === f).length})</button>)}
          <span className="ml-auto text-ink-muted">Times in UTC; statement times were read as IST unless the source said otherwise.</span>
        </div>
        <div className="space-y-4">
          {groups.map(([day, evs]) => (
            <section key={day} className="card">
              <h2 className="mb-2 text-sm font-semibold">{day} <span className="font-normal text-ink-muted">· {evs.length} event{evs.length > 1 ? "s" : ""}</span></h2>
              <ol className="relative ml-2 border-l border-line">
                {evs.map((e: any) => (
                  <li key={e.id} className="mb-3 ml-4">
                    <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full ring-2 ring-white" style={{ background: COLORS[e.family] }} aria-hidden />
                    <div className="text-xs text-ink-muted">{e.time ? fmtTime(e.time).slice(11, 19) : "—"} {e.time_precision !== "second" && <span className="badge bg-saffron-soft text-warn">{e.time_precision.replace(/_/g, " ")}</span>} {e.time_raw && <span className="mono">raw: {e.time_raw}</span>}</div>
                    <div className="text-sm"><span className="badge mr-1" style={{ background: COLORS[e.family] + "22", color: COLORS[e.family] }}>{e.family}</span>{e.label}</div>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
      </State>
    </Shell>
  );
}

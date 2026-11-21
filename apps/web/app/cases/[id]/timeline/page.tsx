"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime } from "@/lib/api";

const FAMILIES = ["transaction", "complaint", "url", "dns", "hosting", "registration", "technical"];
const COLORS: Record<string, string> = { transaction: "#1f5fa8", complaint: "#6c5ce7", url: "#c0392b", dns: "#8e44ad", hosting: "#5d6d7e", registration: "#d35400", technical: "#7b8794" };

export default function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [events, setEvents] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fams, setFams] = useState<string[]>(FAMILIES);
  useEffect(() => { Promise.all([api(`/cases/${id}`), api(`/cases/${id}/timeline`)]).then(([cc, ev]) => { setC(cc); setEvents(ev); }).catch((e) => setError(e.message)); }, [id]);
  const shown = (events || []).filter((e) => fams.includes(e.family));
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Timeline">
      <State loading={!events && !error} error={error} empty={events && events.length === 0 ? "No dated evidence yet." : null}>
        <div className="card mb-3 flex flex-wrap gap-3 text-xs"><span className="label">Event family</span>{FAMILIES.map((f) => <label key={f} className="flex items-center gap-1"><input type="checkbox" checked={fams.includes(f)} onChange={() => setFams(fams.includes(f) ? fams.filter((x) => x !== f) : [...fams, f])} /><span style={{ color: COLORS[f] }}>●</span>{f}</label>)}<span className="ml-auto text-ink-muted">All times UTC; statement times were read as IST unless the source stated otherwise. Items without a usable time are listed last.</span></div>
        <ol className="relative ml-3 border-l border-line">
          {shown.map((e) => (
            <li key={e.id} className="mb-3 ml-4">
              <span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full" style={{ background: COLORS[e.family] }} aria-hidden />
              <div className="text-xs text-ink-muted">{fmtTime(e.time)} {e.time_precision !== "second" && <span className="badge bg-[#fdf3e0] text-[#8a5a0f]">{e.time_precision.replace(/_/g, " ")}</span>} {e.time_raw && <span className="font-mono">raw: {e.time_raw}</span>}</div>
              <div className="text-sm"><span className="badge mr-1" style={{ background: COLORS[e.family] + "22", color: COLORS[e.family] }}>{e.family}</span>{e.label}</div>
            </li>
          ))}
        </ol>
      </State>
    </Shell>
  );
}

"use client";

import cytoscape, { Core } from "cytoscape";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import EdgePanel from "@/components/EdgePanel";
import Shell, { LevelBadge, State } from "@/components/Shell";
import { api, LEVEL_COLORS, NODE_COLORS } from "@/lib/api";

const TYPES = ["account", "vpa", "domain", "url", "ip", "asn", "hosting_provider", "phone", "email", "evidence_file", "reference"];
const LEVELS = ["directly_observed", "corroborated", "derived", "candidate", "contradicted", "stale", "insufficient"];

export default function GraphPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [g, setG] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [types, setTypes] = useState<string[]>(TYPES.filter((t) => t !== "evidence_file" && t !== "reference"));
  const [levels, setLevels] = useState<string[]>(LEVELS);
  const [backedOnly, setBackedOnly] = useState(false);
  const [edge, setEdge] = useState<string | null>(null);
  const [node, setNode] = useState<any>(null);
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const load = useCallback(() => {
    const q = new URLSearchParams({ entity_types: types.join(","), levels: levels.join(","), evidence_backed_only: String(backedOnly) });
    api(`/cases/${id}/graph?${q}`).then(setG).catch((e) => setError(e.message));
  }, [id, types, levels, backedOnly]);
  useEffect(() => { api(`/cases/${id}`).then(setC).catch((e) => setError(e.message)); }, [id]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!g || !ref.current) return;
    cyRef.current?.destroy();
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...g.nodes.map((n: any) => ({ data: { id: n.id, label: n.label.length > 22 ? n.label.slice(0, 20) + "…" : n.label, type: n.type, color: NODE_COLORS[n.type] || "#7b8794" } })),
        ...g.edges.filter((e: any) => e.type !== "DOCUMENTS").map((e: any) => ({ data: { id: e.id, source: e.source, target: e.target, label: e.type, level: e.evidence_level, color: LEVEL_COLORS[e.evidence_level] || "#999", dashed: ["candidate", "stale", "contradicted", "insufficient"].includes(e.evidence_level) ? "dashed" : "solid", width: e.evidence_level === "corroborated" ? 3 : 1.5 } })),
      ],
      style: [
        { selector: "node", style: { "background-color": "data(color)", label: "data(label)", "font-size": 9, color: "#1d2733", "text-valign": "bottom", "text-margin-y": 4, width: 22, height: 22, "text-wrap": "wrap", "text-max-width": "90px" } },
        { selector: "edge", style: { width: "data(width)", "line-color": "data(color)", "line-style": "data(dashed)" as any, "target-arrow-color": "data(color)", "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": 0.8, label: "data(label)", "font-size": 7, color: "#5b6775", "text-rotation": "autorotate", "text-background-color": "#fff", "text-background-opacity": 0.8, "text-background-padding": "1px" } },
        { selector: ":selected", style: { "border-width": 3, "border-color": "#1f5fa8", "line-color": "#1f5fa8", "target-arrow-color": "#1f5fa8" } },
      ],
      layout: { name: "cose", animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 90, padding: 20 } as any,
      wheelSensitivity: 0.2,
    });
    cy.on("tap", "edge", (ev) => { setEdge(ev.target.id()); setNode(null); });
    cy.on("tap", "node", (ev) => { setEdge(null); api(`/cases/${id}/entities/${ev.target.id()}`).then(setNode).catch(() => setNode(null)); });
    cyRef.current = cy;
    return () => { cy.destroy(); };
  }, [g, id]);

  const toggle = (arr: string[], set: (v: string[]) => void, v: string) => set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Investigation graph">
      <State loading={!g && !error} error={error}>
        <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
          <div className="space-y-3">
            <div className="card flex flex-wrap items-center gap-3 text-xs">
              <fieldset className="flex flex-wrap gap-2"><legend className="label">Entity types</legend>{TYPES.map((t) => <label key={t} className="flex items-center gap-1"><input type="checkbox" checked={types.includes(t)} onChange={() => toggle(types, setTypes, t)} /><span style={{ color: NODE_COLORS[t] }}>●</span>{t}</label>)}</fieldset>
              <fieldset className="flex flex-wrap gap-2"><legend className="label">Evidence level</legend>{LEVELS.map((l) => <label key={l} className="flex items-center gap-1"><input type="checkbox" checked={levels.includes(l)} onChange={() => toggle(levels, setLevels, l)} /><LevelBadge level={l} /></label>)}</fieldset>
              <label className="flex items-center gap-1"><input type="checkbox" checked={backedOnly} onChange={(e) => setBackedOnly(e.target.checked)} />Evidence-backed path only</label>
              <button className="btn-secondary" onClick={() => cyRef.current?.fit(undefined, 20)}>Reset view</button>
              <button className="btn-secondary" onClick={() => { const png = cyRef.current?.png({ full: true, scale: 2 }); if (png) { const a = document.createElement("a"); a.href = png; a.download = `graph_${id.slice(0, 8)}.png`; a.click(); } }}>Export PNG</button>
            </div>
            <div ref={ref} className="card h-[520px] p-0" role="img" aria-label="Investigation graph; use the tables and panels for an accessible view" />
            <div className="card text-xs">
              <div className="label">Legend</div>
              <div className="flex flex-wrap gap-3">{Object.entries(g?.legend || {}).map(([k, v]: any) => <span key={k} className="flex items-center gap-1"><span style={{ background: LEVEL_COLORS[k], width: 18, height: 3, display: "inline-block", borderTop: ["candidate", "stale", "contradicted"].includes(k) ? "2px dashed " + LEVEL_COLORS[k] : undefined }} />{k.replace("_", " ")}: {v}</span>)}</div>
              <div className="mt-1 text-ink-muted">Solid = observed/derived · dashed = candidate/stale/contradicted · thick = corroborated. {g?.stats.nodes} nodes, {g?.stats.edges} edges. Click an edge for evidence and counter-evidence; click a node for its 360 view.</div>
            </div>
            <div className="card overflow-x-auto p-0"><table className="data"><thead><tr><th>Type</th><th>Source → Target</th><th>Level</th><th>Review</th><th>Valid from</th></tr></thead>
              <tbody>{(g?.edges || []).filter((e: any) => e.type !== "DOCUMENTS").slice(0, 200).map((e: any) => { const s = g.nodes.find((n: any) => n.id === e.source); const t = g.nodes.find((n: any) => n.id === e.target); return <tr key={e.id} className="cursor-pointer hover:bg-accent-light" onClick={() => setEdge(e.id)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && setEdge(e.id)}><td className="font-mono text-xs">{e.type}</td><td className="text-xs">{s?.label} → {t?.label}</td><td><LevelBadge level={e.evidence_level} /></td><td className="text-xs">{e.review_status}</td><td className="text-xs">{e.valid_from ? e.valid_from.slice(0, 10) : "—"}</td></tr>; })}</tbody></table></div>
          </div>
          <div className="space-y-3">
            <EdgePanel caseId={id} edgeId={edge} onClose={() => setEdge(null)} onReviewed={load} />
            {node && !edge && (
              <aside className="card text-sm" aria-label="Entity 360">
                <div className="flex items-start justify-between"><h2 className="font-semibold">Entity 360</h2><button className="btn-secondary" onClick={() => setNode(null)}>Close</button></div>
                <div className="mt-1"><span className="badge bg-[#eef1f4]">{node.entity.type}</span> <span className="font-mono">{node.entity.attributes.key}</span></div>
                <div className="text-xs text-ink-muted">first seen {node.first_seen?.slice(0, 10) || "?"} · last seen {node.last_seen?.slice(0, 10) || "?"} · {node.edges.length} relationships</div>
                {node.triage && <div className="mt-2 rounded bg-[#f6f8fa] p-2 text-xs"><div className="font-semibold">Triage (rules; requires review): {node.triage.label.replace(/_/g, " ")}</div><div>{node.triage.reasons.join(", ") || "no rule fired"}</div><div className="mt-1 text-ink-muted">fan-in {node.features.fan_in} · fan-out {node.features.fan_out} · median holding {node.features.median_holding_hours < 0 ? "n/a" : node.features.median_holding_hours.toFixed(1) + "h"} · out/in {node.features.out_in_ratio.toFixed(2)}</div></div>}
                <ul className="mt-2 max-h-60 overflow-y-auto text-xs">{node.edges.map((e: any) => <li key={e.id} className="cursor-pointer py-0.5 hover:underline" onClick={() => setEdge(e.id)}>{e.type} · <LevelBadge level={e.evidence_level} /></li>)}</ul>
              </aside>
            )}
            {!edge && !node && <div className="card text-sm text-ink-muted">Select an edge to inspect its source, locator, times, method, limitations and counter-evidence.</div>}
          </div>
        </div>
      </State>
    </Shell>
  );
}

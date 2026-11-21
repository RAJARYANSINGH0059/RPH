"use client";

import cytoscape, { Core } from "cytoscape";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import EdgePanel from "@/components/EdgePanel";
import Shell, { LevelBadge, State } from "@/components/Shell";
import { I } from "@/components/icons";
import { Chip, Money, When } from "@/components/ui";
import { api, LEVEL_COLORS, NODE_COLORS, paise } from "@/lib/api";

const LANES: { name: string; types: string[] }[] = [
  { name: "Sources", types: ["evidence_file"] },
  { name: "Accounts", types: ["account", "vpa"] },
  { name: "Identifiers", types: ["person", "phone", "email", "reference"] },
  { name: "Web", types: ["url", "domain"] },
  { name: "Infrastructure", types: ["ip", "asn", "hosting_provider"] },
  { name: "Instructions", types: ["payment_instruction"] },
];
const ALL_TYPES = LANES.flatMap((l: any) => l.types);
const LEVELS = ["directly_observed", "corroborated", "derived", "candidate", "contradicted", "stale", "insufficient"];
const PRESETS: Record<string, { label: string; hint: string; types: string[]; edgeTypes?: string[] }> = {
  money: { label: "Money trail", hint: "Accounts and VPAs linked by transfers", types: ["account", "vpa"], edgeTypes: ["TRANSFERRED_TO", "SAME_ACCOUNT_IDENTIFIER", "SIMILAR_NAME"] },
  infra: { label: "Infrastructure", hint: "Domains, URLs, IPs and hosting with time validity", types: ["url", "domain", "ip", "asn", "hosting_provider"] },
  bridge: { label: "Bridges", hint: "Where financial and cyber evidence connect", types: ["account", "vpa", "phone", "email", "url", "domain", "evidence_file"], edgeTypes: ["MENTIONS", "SAME_IDENTIFIER", "TRANSFERRED_TO", "BELONGS_TO_DOMAIN"] },
  control: { label: "Account control", hint: "Accounts, VPAs, phones, emails and the documents naming them", types: ["account", "vpa", "person", "phone", "email", "evidence_file"], edgeTypes: ["MENTIONS", "SAME_IDENTIFIER", "SIMILAR_NAME", "SAME_ACCOUNT_IDENTIFIER"] },
  instructions: { label: "Payment instructions", hint: "QR / UPI instructions matched to payees and transactions", types: ["payment_instruction", "vpa", "account"], edgeTypes: ["INSTRUCTS_PAYMENT_TO", "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION", "TRANSFERRED_TO"] },
  full: { label: "Full picture", hint: "Everything, including evidence files", types: ALL_TYPES },
};
const EDGE_STYLE: Record<string, { dash: string; arrow: string; width: number }> = {
  TRANSFERRED_TO: { dash: "solid", arrow: "triangle", width: 2.2 }, SAME_ACCOUNT_IDENTIFIER: { dash: "solid", arrow: "none", width: 1.6 }, SAME_IDENTIFIER: { dash: "solid", arrow: "diamond", width: 1.6 },
  SIMILAR_NAME: { dash: "dotted", arrow: "none", width: 1.4 }, MENTIONS: { dash: "dashed", arrow: "vee", width: 1.2 }, RESOLVES_TO: { dash: "solid", arrow: "chevron", width: 1.6 }, HOSTED_ON: { dash: "solid", arrow: "chevron", width: 1.4 },
  SHARED_INFRASTRUCTURE: { dash: "dotted", arrow: "none", width: 1.4 }, REGISTRATION_OBSERVED: { dash: "dashed", arrow: "vee", width: 1.2 }, BELONGS_TO_DOMAIN: { dash: "solid", arrow: "none", width: 1 },
  INSTRUCTS_PAYMENT_TO: { dash: "solid", arrow: "square", width: 1.8 }, PAYMENT_INSTRUCTION_MATCHES_TRANSACTION: { dash: "solid", arrow: "circle", width: 2 },
};
const NODE_SHAPE: Record<string, string> = { account: "ellipse", vpa: "round-rectangle", person: "hexagon", phone: "round-rectangle", email: "round-rectangle", url: "rectangle", domain: "round-diamond", ip: "diamond", asn: "octagon", hosting_provider: "octagon", evidence_file: "round-tag", reference: "ellipse", payment_instruction: "star" };
const EDGE_HELP: Record<string, string> = {
  TRANSFERRED_TO: "Money moved from source to target (one statement row).", SAME_ACCOUNT_IDENTIFIER: "A VPA and an account number refer to the same account (matched by reference + amount in two statements).",
  SAME_IDENTIFIER: "The same identifier appears in a document and in a statement.", SIMILAR_NAME: "Names look alike; identifiers differ. Not merged.", MENTIONS: "The document mentions this indicator.",
  RESOLVES_TO: "Domain pointed to this IP at the observation time.", HOSTED_ON: "IP sits on this provider/ASN at the observation time.", SHARED_INFRASTRUCTURE: "Two domains share an IP. Pivot only; not proof of common control.",
  REGISTRATION_OBSERVED: "Current registration data observed.", BELONGS_TO_DOMAIN: "URL is under this domain.", DOCUMENTS: "File documents this account.",
};

export default function GraphPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [g, setG] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [preset, setPreset] = useState<string>("money");
  const [types, setTypes] = useState<string[]>(PRESETS.money.types);
  const [levels, setLevels] = useState<string[]>(LEVELS);
  const [backedOnly, setBackedOnly] = useState(false);
  const [labels, setLabels] = useState(false);
  const [layout, setLayout] = useState<"lanes" | "force">("lanes");
  const [q, setQ] = useState("");
  const [edge, setEdge] = useState<string | null>(null);
  const [node, setNode] = useState<any>(null);
  const [advanced, setAdvanced] = useState(false);
  const [paths, setPaths] = useState<any[]>([]);
  const [txs, setTxs] = useState<any[]>([]);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [selPath, setSelPath] = useState<number | null>(null);
  const [replayStep, setReplayStep] = useState<number>(-1);
  const [playing, setPlaying] = useState(false);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [win, setWin] = useState<{ from: string; to: string }>({ from: "", to: "" });
  const [views, setViews] = useState<any[]>([]);
  const [bottom, setBottom] = useState<"timeline" | "table" | "none">("table");
  const [reduced, setReduced] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  const load = useCallback(() => { api(`/cases/${id}/graph`).then(setG).catch((e) => setError(e.message)); }, [id]);
  useEffect(() => { api(`/cases/${id}`).then(setC).catch((e) => setError(e.message)); }, [id]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api(`/cases/${id}/paths`).then((p) => setPaths(p.paths)).catch(() => undefined); api(`/cases/${id}/transactions`).then(setTxs).catch(() => undefined); api(`/cases/${id}/timeline`).then(setTimeline).catch(() => undefined); api(`/cases/${id}/views`).then(setViews).catch(() => undefined); try { setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch { /* ignore */ } }, [id]);
  useEffect(() => {
    if (!playing || selPath === null || reduced) return;
    const hops = paths[selPath]?.hops?.length || 0;
    const t = setTimeout(() => setReplayStep((s) => (s + 1 >= hops ? (setPlaying(false), hops - 1) : s + 1)), 900);
    return () => clearTimeout(t);
  }, [playing, replayStep, selPath, paths, reduced]);
  const applyPreset = (k: string) => { setPreset(k); setTypes(PRESETS[k].types); };

  const view = useMemo(() => {
    if (!g) return null;
    const p = PRESETS[preset];
    const nodes = g.nodes.filter((n: any) => types.includes(n.type));
    const ids = new Set(nodes.map((n: any) => n.id));
    let edges = g.edges.filter((e: any) => ids.has(e.source) && ids.has(e.target) && levels.includes(e.evidence_level) && e.type !== "DOCUMENTS");
    if (p.edgeTypes && preset !== "full") edges = edges.filter((e: any) => p.edgeTypes!.includes(e.type));
    if (backedOnly) edges = edges.filter((e: any) => ["directly_observed", "corroborated", "derived"].includes(e.evidence_level));
    if (win.from || win.to) edges = edges.filter((e: any) => { const t = e.valid_from || e.observed_at; if (!t) return true; return (!win.from || t >= win.from) && (!win.to || t <= win.to + "T23:59:59"); });
    const connected = new Set<string>();
    edges.forEach((e: any) => { connected.add(e.source); connected.add(e.target); });
    const shownNodes = nodes.filter((n: any) => connected.has(n.id));
    const degree: Record<string, number> = {};
    edges.forEach((e: any) => { degree[e.source] = (degree[e.source] || 0) + 1; degree[e.target] = (degree[e.target] || 0) + 1; });
    const byLevel: Record<string, number> = {};
    edges.forEach((e: any) => { byLevel[e.evidence_level] = (byLevel[e.evidence_level] || 0) + 1; });
    const byType: Record<string, number> = {};
    edges.forEach((e: any) => { byType[e.type] = (byType[e.type] || 0) + 1; });
    return { nodes: shownNodes, edges, degree, byLevel, byType, hiddenNodes: nodes.length - shownNodes.length };
  }, [g, preset, types, levels, backedOnly, win]);

  useEffect(() => {
    if (!view || !ref.current) return;
    cyRef.current?.destroy();
    const laneOf = (t: string) => Math.max(0, LANES.findIndex((l) => l.types.includes(t)));
    const activeLanes = LANES.map((l: any, i: any) => i).filter((i: any) => view.nodes.some((n: any) => laneOf(n.type) === i));
    const positions: Record<string, { x: number; y: number }> = {};
    activeLanes.forEach((li, col) => {
      const ns = view.nodes.filter((n: any) => laneOf(n.type) === li).sort((a: any, b: any) => (view.degree[b.id] || 0) - (view.degree[a.id] || 0) || a.label.localeCompare(b.label));
      const gap = Math.max(56, Math.min(110, 560 / Math.max(1, ns.length)));
      ns.forEach((n: any, row: number) => { positions[n.id] = { x: col * 280 + (ns.length > 6 ? (row % 2) * 90 - 45 : 0), y: row * gap - ((ns.length - 1) * gap) / 2 }; });
    });
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...LANES.filter((l) => collapsed.includes(l.name) && view.nodes.some((n: any) => l.types.includes(n.type))).map((l) => ({ data: { id: `cluster:${l.name}`, label: `${l.name} (${view.nodes.filter((n: any) => l.types.includes(n.type)).length}) — layout group, not common control`, type: "cluster", color: "#e9eef2", size: 40, shape: "round-rectangle" } })),
        ...view.nodes.map((n: any) => { const lane = LANES.find((l) => l.types.includes(n.type)); const parent = lane && collapsed.includes(lane.name) ? `cluster:${lane.name}` : undefined; return { data: { id: n.id, parent, label: n.label.length > 24 ? n.label.slice(0, 22) + "…" : n.label, type: n.type, color: NODE_COLORS[n.type] || "#7b8794", shape: NODE_SHAPE[n.type] || "ellipse", size: 18 + Math.min(22, (view.degree[n.id] || 1) * 3) } }; }),
        ...view.edges.map((e: any) => { const st = EDGE_STYLE[e.type] || { dash: "solid", arrow: "triangle", width: 1.6 }; const weak = ["candidate", "stale", "contradicted", "insufficient"].includes(e.evidence_level); return { data: { id: e.id, source: e.source, target: e.target, label: e.type.replace(/_/g, " ").toLowerCase(), level: e.evidence_level, color: LEVEL_COLORS[e.evidence_level] || "#999", dashed: weak ? "dashed" : st.dash, width: e.evidence_level === "corroborated" ? st.width + 1.2 : st.width, arrow: st.arrow } }; }),
      ],
      style: [
        { selector: "node", style: { "background-color": "data(color)", shape: "data(shape)" as any, "border-width": 2, "border-color": "#ffffff", label: "data(label)", "font-size": 10, "font-weight": 500, color: "#1d2733", "text-valign": "bottom", "text-margin-y": 5, width: "data(size)", height: "data(size)", "text-wrap": "ellipsis", "text-max-width": "120px", "text-background-color": "#ffffff", "text-background-opacity": 0.85, "text-background-padding": "2px", "text-background-shape": "roundrectangle" } },
        { selector: "edge", style: { width: "data(width)", "line-color": "data(color)", "line-style": "data(dashed)" as any, "target-arrow-color": "data(color)", "target-arrow-shape": "data(arrow)" as any, "curve-style": "bezier", "arrow-scale": 0.9, opacity: 0.85, label: labels ? "data(label)" : "", "font-size": 8, color: "#5b6775", "text-rotation": "autorotate", "text-background-color": "#fff", "text-background-opacity": 0.9, "text-background-padding": "1px" } },
        { selector: "edge:selected, edge.hl", style: { label: "data(label)", width: 4, opacity: 1, "z-index": 10 } },
        { selector: "node:selected, node.hl", style: { "border-color": "#1f5fa8", "border-width": 4 } },
        { selector: ".dim", style: { opacity: 0.15 } },
        { selector: ":parent", style: { "background-opacity": 0.25, "border-color": "#c9c1b2", "border-style": "dashed", "font-size": 9, "text-valign": "top", shape: "round-rectangle" } },
        { selector: ":parent.collapsed-cluster", style: { label: "data(label)" } },
        { selector: "edge.path-hl", style: { "line-color": "#147d83", "target-arrow-color": "#147d83", width: 5, opacity: 1, "z-index": 20 } },
        { selector: "node.path-hl", style: { "border-color": "#147d83", "border-width": 5 } },
        { selector: "edge.path-pending", style: { opacity: 0.25 } },
      ],
      layout: layout === "lanes" && activeLanes.length > 1 ? ({ name: "preset", positions: (n: any) => positions[n.id()], fit: true, padding: 30 } as any) : ({ name: "cose", animate: false, nodeRepulsion: () => 14000, idealEdgeLength: () => 120, padding: 30, randomize: false } as any),
      wheelSensitivity: 0.2, minZoom: 0.2, maxZoom: 3,
    });
    cy.on("tap", "edge", (ev) => { setEdge(ev.target.id()); setNode(null); });
    cy.on("tap", "node", (ev) => {
      const n = ev.target; setEdge(null);
      cy.elements().addClass("dim"); n.closedNeighborhood().removeClass("dim");
      api(`/cases/${id}/entities/${n.id()}`).then(setNode).catch(() => setNode(null));
      setSelPath(null);
    });
    cy.on("tap", (ev) => { if (ev.target === cy) { cy.elements().removeClass("dim hl"); setNode(null); } });
    cy.on("mouseover", "edge", (ev) => ev.target.addClass("hl"));
    cy.on("mouseout", "edge", (ev) => ev.target.removeClass("hl"));
    collapsed.forEach((name) => { const parent = cy.getElementById(`cluster:${name}`); if (parent.nonempty()) { parent.addClass("collapsed-cluster"); parent.children().style("display", "none"); } });
    cyRef.current = cy;
    (window as any).__ps05x_cy = cy; // debugging aid
    // the container can be measured as 0x0 on first paint; refit once the browser has laid it out
    const raf = requestAnimationFrame(() => { cy.resize(); cy.fit(undefined, 30); });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => { cy.resize(); cy.fit(undefined, 30); }) : null;
    if (ro && ref.current) ro.observe(ref.current);
    return () => { cancelAnimationFrame(raf); ro?.disconnect(); cy.destroy(); };
  }, [view, id, labels, layout, collapsed]);

  useEffect(() => {
    const cy = cyRef.current; if (!cy) return;
    cy.elements().removeClass("path-hl path-pending");
    if (selPath === null || !paths[selPath]) return;
    const p = paths[selPath];
    const keyOf = (acct: string) => g?.nodes.find((n: any) => n.attributes?.key === acct)?.id;
    const edgeIds = p.hops.map((h: any) => g?.edges.find((e: any) => e.attributes?.transaction_id === h.tx_id)?.id).filter(Boolean);
    const upto = replayStep < 0 ? edgeIds.length : replayStep + 1;
    edgeIds.forEach((eid: string, i: number) => { const el = cy.getElementById(eid); if (el.nonempty()) el.addClass(i < upto ? "path-hl" : "path-pending"); });
    p.accounts.slice(0, upto + 1).forEach((a: string) => { const nid = keyOf(a); if (nid) cy.getElementById(nid).addClass("path-hl"); });
    const eles = cy.elements(".path-hl");
    if (eles.nonempty()) cy.animate({ fit: { eles, padding: 80 }, duration: reduced ? 0 : 250 });
  }, [selPath, replayStep, paths, g, view, reduced]);

  function search(term: string) {
    setQ(term);
    const cy = cyRef.current; if (!cy) return;
    cy.elements().removeClass("hl dim");
    if (!term.trim()) return;
    const hits = cy.nodes().filter((n: any) => `${n.data("label")} ${g?.nodes.find((x: any) => x.id === n.id())?.attributes?.key || ""}`.toLowerCase().includes(term.toLowerCase()));
    if (hits.length) { cy.elements().addClass("dim"); hits.closedNeighborhood().removeClass("dim"); hits.addClass("hl"); cy.animate({ fit: { eles: hits.closedNeighborhood(), padding: 60 }, duration: 300 }); }
  }
  const toggle = (arr: string[], set: (v: string[]) => void, v: string) => set(arr.includes(v) ? arr.filter((x: any) => x !== v) : [...arr, v]);
  const nodeLabel = (nid: string) => g?.nodes.find((n: any) => n.id === nid)?.label || "?";
  const candidates = view?.edges.filter((e: any) => ["candidate", "stale", "contradicted"].includes(e.evidence_level)) || [];

  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Graph Explorer" subtitle="Linked workbench: the graph, a contextual inspector, and a synchronised transaction table / timeline. Shapes and line patterns encode node class and relationship type; dashed means candidate or stale. Clusters are layout groups only." pageKey="graph" wide>
      <State loading={!g && !error} error={error}>
        {g && g.edges.length === 0 && <div className="card border-dashed text-center text-sm text-ink-muted">No relationships yet. Upload a statement or generate a synthetic case first.</div>}
        {g && g.edges.length > 0 && view && (
          <div className="wb-grid">
            <div className="space-y-3">
              <div className="card space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="label mb-0 mr-1">Focus</span>
                  {Object.entries(PRESETS).map(([k, p]: [any, any]) => <button key={k} className={`chip ${preset === k && JSON.stringify(types) === JSON.stringify(p.types) ? "chip-on" : ""}`} title={p.hint} onClick={() => applyPreset(k)}>{p.label}</button>)}
                  <span className="mx-1 hidden h-5 w-px bg-line sm:block" />
                  <div className="relative"><I.search className="absolute left-2 top-2 text-ink-muted" width={15} height={15} /><input className="input w-56 py-1.5 pl-7" placeholder="Find account, VPA, domain…" aria-label="Find in graph" value={q} onChange={(e) => search(e.target.value)} /></div>
                  <button className="btn-secondary" onClick={() => setAdvanced((v) => !v)} aria-expanded={advanced}>{advanced ? "Hide filters" : "More filters"}</button>
                </div>
                <div className="flex flex-wrap items-center gap-3 text-xs">
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={backedOnly} onChange={(e) => setBackedOnly(e.target.checked)} />Evidence-backed only (hide hypotheses)</label>
                  <label className="flex items-center gap-1.5"><input type="checkbox" checked={labels} onChange={(e) => setLabels(e.target.checked)} />Show all edge labels</label>
                  <span className="flex items-center gap-1"><span className="text-ink-muted">Layout</span><button className={`chip ${layout === "lanes" ? "chip-on" : ""}`} onClick={() => setLayout("lanes")}>Lanes</button><button className={`chip ${layout === "force" ? "chip-on" : ""}`} onClick={() => setLayout("force")}>Force</button></span>
                  <label className="flex items-center gap-1"><span className="text-ink-muted">From</span><input type="date" className="input !w-auto !py-0.5" value={win.from} onChange={(e) => setWin({ ...win, from: e.target.value })} aria-label="Time window from" /></label>
                  <label className="flex items-center gap-1"><span className="text-ink-muted">To</span><input type="date" className="input !w-auto !py-0.5" value={win.to} onChange={(e) => setWin({ ...win, to: e.target.value })} aria-label="Time window to" /></label>
                  {(win.from || win.to || backedOnly || preset !== "money") && <button className="btn-ghost" onClick={() => { setWin({ from: "", to: "" }); setBackedOnly(false); applyPreset("money"); setCollapsed([]); }}>Clear filters</button>}
                  <button className="btn-secondary ml-auto" onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() || 1) * 1.25, renderedPosition: { x: 300, y: 250 } })} aria-label="Zoom in"><I.zoomIn /></button>
                  <button className="btn-secondary" onClick={() => cyRef.current?.zoom({ level: (cyRef.current?.zoom() || 1) / 1.25, renderedPosition: { x: 300, y: 250 } })} aria-label="Zoom out"><I.zoomOut /></button>
                  <button className="btn-secondary" onClick={() => cyRef.current?.fit(undefined, 30)}><I.fit /> Fit</button>
                  <button className="btn-secondary" onClick={() => { setLayout("lanes"); setTimeout(() => cyRef.current?.fit(undefined, 30), 50); }}>Reset</button>
                  <button className="btn-secondary" onClick={async () => { const name = window.prompt("Name this view"); if (!name) return; await api(`/cases/${id}/views`, { method: "POST", body: JSON.stringify({ name, state: { preset, types, levels, backedOnly, layout, win, collapsed } }) }); setViews(await api(`/cases/${id}/views`)); }}><I.bookmark /> Save view</button>
                  {views.length > 0 && <select className="input !w-auto !py-0.5" aria-label="Saved views" value="" onChange={(e) => { const v = views.find((x) => x.id === e.target.value); if (v) { setPreset(v.state.preset); setTypes(v.state.types); setLevels(v.state.levels); setBackedOnly(v.state.backedOnly); setLayout(v.state.layout); setWin(v.state.win || { from: "", to: "" }); setCollapsed(v.state.collapsed || []); } }}><option value="">Load view…</option>{views.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}</select>}
                  <button className="btn-secondary" onClick={() => { const png = cyRef.current?.png({ full: true, scale: 2, bg: "#ffffff" }); if (png) { const a = document.createElement("a"); a.href = png; a.download = `graph_${id.slice(0, 8)}.png`; a.click(); } }}><I.download /> PNG</button>
                </div>
                {advanced && (
                  <div className="grid gap-3 border-t border-line pt-3 md:grid-cols-3">
                    <fieldset><legend className="label">Collapse clusters (visual grouping only)</legend><div className="flex flex-wrap gap-1.5">{LANES.filter((l) => view.nodes.some((n: any) => l.types.includes(n.type))).map((l) => <button key={l.name} className={`chip ${collapsed.includes(l.name) ? "chip-on" : ""}`} aria-pressed={collapsed.includes(l.name)} onClick={() => setCollapsed((c) => c.includes(l.name) ? c.filter((x) => x !== l.name) : [...c, l.name])}>{l.name}</button>)}</div><p className="mt-1 text-[11px] text-ink-muted">A cluster boundary groups a lane for readability; it never implies common control.</p></fieldset>
                    <fieldset><legend className="label">Entity types</legend><div className="flex flex-wrap gap-1.5">{ALL_TYPES.map((t: any) => <button key={t} className={`chip ${types.includes(t) ? "chip-on" : ""}`} onClick={() => toggle(types, setTypes, t)}><span style={{ color: NODE_COLORS[t] }}>●</span>{t.replace("_", " ")}</button>)}</div></fieldset>
                    <fieldset><legend className="label">Evidence levels</legend><div className="flex flex-wrap gap-1.5">{LEVELS.map((l: any) => <button key={l} className={`chip ${levels.includes(l) ? "chip-on" : ""}`} onClick={() => toggle(levels, setLevels, l)}><span style={{ color: LEVEL_COLORS[l] }}>■</span>{l.replace("_", " ")}</button>)}</div></fieldset>
                  </div>
                )}
              </div>
              <div className="relative">
                {layout === "lanes" && LANES.filter((l: any) => view.nodes.some((n: any) => l.types.includes(n.type))).length > 1 && (
                  <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-around px-4 pt-2 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                    {LANES.filter((l: any) => view.nodes.some((n: any) => l.types.includes(n.type))).map((l: any) => <span key={l.name} className="rounded-full bg-card/90 px-2 py-0.5 shadow-sm">{l.name}</span>)}
                  </div>
                )}
                <div ref={ref} className="card h-[560px] p-0" style={{ backgroundImage: "linear-gradient(rgba(23,37,54,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(23,37,54,0.05) 1px, transparent 1px)", backgroundSize: "24px 24px" }} role="img" aria-label="Investigation graph; the same relationships are listed in the table below" />
                {view.edges.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-sm text-ink-muted">Nothing matches these filters. Try another focus or clear “Evidence-backed only”.</div>}
              </div>
              {paths.length > 0 && (
                <div className="card flex flex-wrap items-center gap-2 text-xs">
                  <span className="label mb-0">Path replay</span>
                  <select className="input !w-auto !py-0.5" aria-label="Select path" value={selPath ?? ""} onChange={(e) => { const v = e.target.value === "" ? null : Number(e.target.value); setSelPath(v); setReplayStep(-1); setPlaying(false); }}><option value="">none</option>{paths.map((p: any, i: number) => <option key={i} value={i}>#{i} {p.accounts.map((a: string) => a.slice(-4)).join(" → ")} · {paise(p.total_in_minor)} · {p.status}</option>)}</select>
                  {selPath !== null && <><button className="btn-secondary !py-0.5" onClick={() => { setReplayStep(0); setPlaying(!reduced); }} aria-label="Play"><I.play width={14} height={14} /></button><button className="btn-secondary !py-0.5" onClick={() => setPlaying(false)} aria-label="Pause"><I.pause width={14} height={14} /></button><button className="btn-secondary !py-0.5" onClick={() => { setPlaying(false); setReplayStep((s) => Math.min((paths[selPath].hops.length || 1) - 1, s + 1)); }} aria-label="Step"><I.step width={14} height={14} /></button><button className="btn-ghost !py-0.5" onClick={() => { setReplayStep(-1); setPlaying(false); }}>Show whole path</button><span className="text-ink-muted">hop {replayStep < 0 ? "all" : replayStep + 1} / {paths[selPath].hops.length}{reduced ? " · reduced motion: static steps" : ""}</span>{paths[selPath].status === "unresolved" && <span className="badge lvl-insufficient">unresolved end</span>}</>}
                </div>
              )}
              <div className="card p-0">
                <div className="tabs px-3 pt-2" role="tablist">{(["table", "timeline", "none"] as const).map((t) => <button key={t} role="tab" aria-selected={bottom === t} className="tab" onClick={() => setBottom(t)}>{t === "table" ? `Transactions (${(node ? txs.filter((t2: any) => [t2.account_ref, t2.counterparty_ref].includes(node.entity.attributes.key)) : selPath !== null ? txs.filter((t2: any) => paths[selPath].hops.some((h: any) => h.tx_id === t2.id)) : txs).length})` : t === "timeline" ? `Timeline (${timeline.length})` : "Hide"}</button>)}<span className="ml-auto self-center pb-2 text-[11px] text-ink-muted">{node ? `filtered to ${node.entity.label}` : selPath !== null ? `filtered to path #${selPath}` : win.from || win.to ? "filtered to the time window" : "all"}</span></div>
                {bottom === "table" && <div className="max-h-64 overflow-auto"><table className="data text-xs"><thead><tr><th>When</th><th>Account</th><th>Dir</th><th>Amount</th><th>Counterparty</th><th>Reference</th><th>Quality</th></tr></thead><tbody>{(node ? txs.filter((t: any) => [t.account_ref, t.counterparty_ref].includes(node.entity.attributes.key)) : selPath !== null ? txs.filter((t: any) => paths[selPath].hops.some((h: any) => h.tx_id === t.id)) : txs).filter((t: any) => { const d = t.datetime_utc || ""; return (!win.from || !d || d >= win.from) && (!win.to || !d || d <= win.to + "T23:59:59"); }).slice(0, 200).map((t: any) => <tr key={t.id} className="cursor-pointer" onClick={() => { const nid = g?.nodes.find((n: any) => n.attributes?.key === t.account_ref)?.id; if (nid && cyRef.current) { cyRef.current.getElementById(nid).select(); cyRef.current.animate({ center: { eles: cyRef.current.getElementById(nid) }, duration: reduced ? 0 : 200 }); } }}><td><When v={t.datetime_utc} />{t.time_precision === "ambiguous" && <span className="badge lvl-candidate ml-1">ambiguous</span>}</td><td className="mono">{t.account_ref}</td><td>{t.direction}</td><td><Money v={t.amount_minor} /></td><td className="mono">{t.counterparty_ref || "—"}</td><td className="mono">{t.external_reference || "—"}</td><td><Chip v={t.quality_label === "ok" ? "observed" : "candidate"} title={t.quality_label} /></td></tr>)}</tbody></table></div>}
                {bottom === "timeline" && <ol className="max-h-64 overflow-auto px-3 pb-3 text-xs">{timeline.filter((e: any) => (!node || e.label.includes(node.entity.attributes.key)) && (!win.from || !e.time || e.time >= win.from) && (!win.to || !e.time || e.time <= win.to + "T23:59:59")).slice(0, 300).map((e: any) => <li key={e.id} className="flex items-start gap-2 border-b border-line py-1"><span className="w-32 shrink-0 text-ink-muted"><When v={e.time} />{!e.time && "undated"}</span><span className="badge lvl-derived">{e.family}</span><span className="min-w-0 flex-1 truncate">{e.label}</span>{e.time_precision === "ambiguous" && <span className="badge lvl-candidate">ambiguous</span>}</li>)}</ol>}
              </div>
              <div className="grid gap-3 md:grid-cols-[1fr_auto]">
                <div className="card text-sm">
                  <div className="font-semibold">What you are looking at</div>
                  <p className="mt-1 text-ink-muted">{view.nodes.length} entities and {view.edges.length} relationships in the <strong>{PRESETS[preset].label}</strong> focus{view.hiddenNodes > 0 ? ` (${view.hiddenNodes} isolated entities hidden)` : ""}. {candidates.length > 0 ? <>{candidates.length} dashed line{candidates.length > 1 ? "s are" : " is"} a hypothesis or stale observation that needs your decision.</> : "Every visible line is observed, corroborated or derived."}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs">{Object.entries(view.byType).sort((a: any, b: any) => b[1] - a[1]).map(([t, n]: any) => <span key={t} className="rounded-full bg-panel px-2 py-0.5" title={EDGE_HELP[t]}>{t.replace(/_/g, " ").toLowerCase()} · {n}</span>)}</div>
                </div>
                <div className="card text-xs">
                  <div className="label">Legend</div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">{LEVELS.filter((l: any) => view.byLevel[l]).map((l: any) => <span key={l} className="flex items-center gap-1.5"><span style={{ width: 22, borderTop: `${l === "corroborated" ? 3 : 2}px ${["candidate", "stale", "contradicted", "insufficient"].includes(l) ? "dashed" : "solid"} ${LEVEL_COLORS[l]}` }} />{l.replace("_", " ")} ({view.byLevel[l]})</span>)}</div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1">{Array.from(new Set(view.nodes.map((n: any) => n.type))).map((t: any) => <span key={t} className="flex items-center gap-1"><span style={{ color: NODE_COLORS[t] }}>●</span>{t.replace("_", " ")}</span>)}</div>
                  <div className="mt-1 text-ink-muted">Bigger circle = more connections.</div>
                </div>
              </div>
              {candidates.length > 0 && (
                <div className="card p-0">
                  <div className="flex items-center justify-between px-4 py-3"><h2 className="font-semibold">Needs your decision ({candidates.length})</h2><span className="text-xs text-ink-muted">Click a row to open the evidence and counter-evidence</span></div>
                  <table className="data"><thead><tr><th>Relationship</th><th>Between</th><th>Level</th><th>Why it is only a candidate</th></tr></thead>
                    <tbody>{candidates.slice(0, 50).map((e: any) => <tr key={e.id} className="cursor-pointer" onClick={() => setEdge(e.id)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && setEdge(e.id)}><td className="font-medium">{e.type.replace(/_/g, " ").toLowerCase()}</td><td className="text-xs">{nodeLabel(e.source)} ↔ {nodeLabel(e.target)}</td><td><LevelBadge level={e.evidence_level} /></td><td className="text-xs text-ink-muted">{(e.limitations[0] || EDGE_HELP[e.type] || "").replace(/_/g, " ")}</td></tr>)}</tbody></table>
                </div>
              )}
              <details className="card">
                <summary className="cursor-pointer font-semibold">All visible relationships ({view.edges.length})</summary>
                <div className="mt-2 max-h-96 overflow-auto"><table className="data"><thead><tr><th>Type</th><th>Source → Target</th><th>Level</th><th>Review</th><th>Valid from</th></tr></thead>
                  <tbody>{view.edges.slice(0, 300).map((e: any) => <tr key={e.id} className="cursor-pointer" onClick={() => setEdge(e.id)} tabIndex={0} onKeyDown={(k) => k.key === "Enter" && setEdge(e.id)}><td className="text-xs">{e.type.replace(/_/g, " ").toLowerCase()}</td><td className="text-xs">{nodeLabel(e.source)} → {nodeLabel(e.target)}</td><td><LevelBadge level={e.evidence_level} /></td><td className="text-xs">{e.review_status.replace(/_/g, " ")}</td><td className="text-xs">{e.valid_from ? e.valid_from.slice(0, 10) : "—"}</td></tr>)}</tbody></table></div>
              </details>
            </div>
            <div className="space-y-3 xl:sticky xl:top-6 xl:self-start">
              <EdgePanel caseId={id} edgeId={edge} onClose={() => setEdge(null)} onReviewed={load} />
              {node && !edge && (
                <aside className="card text-sm" aria-label="Entity 360">
                  <div className="flex items-start justify-between"><h2 className="font-semibold">Entity 360</h2><button className="btn-icon" onClick={() => { setNode(null); cyRef.current?.elements().removeClass("dim"); }} aria-label="Close"><I.close /></button></div>
                  <div className="mt-1 flex items-center gap-2"><span className="badge" style={{ background: (NODE_COLORS[node.entity.type] || "#7b8794") + "22", color: NODE_COLORS[node.entity.type] }}>{node.entity.type.replace("_", " ")}</span><span className="mono text-xs">{node.entity.attributes.key}</span></div>
                  <div className="mt-1 text-xs text-ink-muted">first seen {node.first_seen?.slice(0, 10) || "?"} · last seen {node.last_seen?.slice(0, 10) || "?"} · {node.edges.length} relationships</div>
                  {node.triage && <div className="mt-2 rounded-lg bg-canvas p-2.5 text-xs"><div className="font-semibold">Triage (rules; requires review): {node.triage.label.replace(/_/g, " ")}</div><div>{node.triage.reasons.map((r: string) => r.replace(/_/g, " ")).join(", ") || "no rule fired"}</div><div className="mt-1 text-ink-muted">fan-in {node.features.fan_in} · fan-out {node.features.fan_out} · median holding {node.features.median_holding_hours < 0 ? "n/a" : node.features.median_holding_hours.toFixed(1) + " h"} · out/in {node.features.out_in_ratio.toFixed(2)}</div></div>}
                  <div className="mt-2 flex flex-wrap gap-1.5 text-xs">{node.entity.type === "account" && <><Link className="btn-secondary !py-1" href={`/cases/${id}/roles`}>Role review</Link><Link className="btn-secondary !py-1" href={`/cases/${id}/intervention`}>Intervention impact</Link></>}{node.entity.type === "payment_instruction" && <Link className="btn-secondary !py-1" href={`/cases/${id}/payment-bridge`}>Open bridge</Link>}<Link className="btn-secondary !py-1" href={`/cases/${id}/counterproof`}>CounterProof</Link></div>
                  <div className="label mt-3">Relationships</div>
                  <ul className="max-h-64 space-y-1 overflow-y-auto text-xs">{node.edges.map((e: any) => <li key={e.id}><button className="flex w-full items-center justify-between gap-2 rounded px-1.5 py-1 text-left hover:bg-accent-light" onClick={() => setEdge(e.id)}><span>{e.type.replace(/_/g, " ").toLowerCase()} · {e.source === node.entity.id ? "→ " + nodeLabel(e.target) : "← " + nodeLabel(e.source)}</span><LevelBadge level={e.evidence_level} /></button></li>)}</ul>
                </aside>
              )}
              {!edge && !node && (
                <div className="card text-sm">
                  <div className="font-semibold">Evidence panel</div>
                  <p className="mt-1 text-ink-muted">Click any line in the graph or a row in the tables. You will see the source file and exact cell or page, the time the fact was valid and observed, the method that created the link, its limitations, counter-evidence and the review buttons.</p>
                  <div className="mt-3 rounded-lg bg-canvas p-2.5 text-xs"><div className="font-semibold">Reading the lines</div><ul className="mt-1 list-disc space-y-0.5 pl-4"><li>Solid = observed or derived fact</li><li>Thick = corroborated by two sources</li><li>Dashed = candidate or stale; needs a decision</li><li>Arrow = direction of money or reference; no arrow = symmetric association</li></ul></div>
                </div>
              )}
            </div>
          </div>
        )}
      </State>
    </Shell>
  );
}

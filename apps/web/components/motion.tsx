"use client";

/** Domain-specific motion scenes: SVG + CSS keyframes, no fake progress, no fake data. Every scene respects
 * prefers-reduced-motion (static frame) and pauses when scrolled off-screen. Live-data motion (path replay) lives in the
 * graph workbench; these scenes are illustrative and say so. */
import { useEffect, useRef, useState } from "react";

export type SceneType = "financial_flow" | "network_correlation" | "evidence_scan" | "infrastructure_radar" | "counterproof" | "investigation_timeline" | "recovery_reconciliation" | "campaign_evolution" | "login" | "empty";

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

export function MotionScene({ scene, height = 160, className = "", label }: { scene: SceneType; height?: number; className?: string; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (!ref.current || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.05 });
    io.observe(ref.current);
    return () => io.disconnect();
  }, []);
  const paused = reduced || !visible;
  return (
    <div ref={ref} className={`scene ${paused ? "scene-paused" : ""} ${className}`} style={{ height }} role="img" aria-label={label || SCENE_LABELS[scene]}>
      {SCENES[scene]()}
      <span className="scene-caption">{label || SCENE_LABELS[scene]}{reduced ? " · static (reduced motion)" : ""}</span>
    </div>
  );
}

const SCENE_LABELS: Record<SceneType, string> = {
  financial_flow: "Illustration: value moving along observed transfers, splitting and merging",
  network_correlation: "Illustration: separated clusters with corroborated and candidate links",
  evidence_scan: "Illustration: document scan with extraction markers and hash motif",
  infrastructure_radar: "Illustration: domain → DNS observation → hosting with a time marker",
  counterproof: "Illustration: a hypothesis branching into supporting, contradicting and missing evidence",
  investigation_timeline: "Illustration: investigation cursor over dated events",
  recovery_reconciliation: "Illustration: a reported loss split into traced, held, restored and unresolved",
  campaign_evolution: "Illustration: identifiers rotating across time with unknown gaps",
  login: "Illustration: secure synthetic workspace",
  empty: "Nothing to show yet",
};

const C = { navy: "var(--rail)", teal: "var(--accent)", copper: "var(--terracotta)", amber: "var(--saffron)", line: "var(--line-strong)", ok: "var(--ok)", danger: "var(--danger)", ink: "var(--ink)", slate: "var(--slate)" };

const SCENES: Record<SceneType, () => React.ReactNode> = {
  financial_flow: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <defs><path id="p1" d="M60 80 C 160 80, 180 50, 280 50" /><path id="p2" d="M60 80 C 160 80, 180 110, 280 110" /><path id="p3" d="M280 50 C 380 50, 400 80, 520 80" /><path id="p4" d="M280 110 C 380 110, 400 80, 520 80" /></defs>
      {["p1", "p2", "p3", "p4"].map((id) => <use key={id} href={`#${id}`} stroke={C.line} strokeWidth="2" fill="none" />)}
      {["p1", "p2", "p3", "p4"].map((id, i) => <circle key={id} r="4" fill={C.teal}><animateMotion dur={`${3 + i * 0.4}s`} repeatCount="indefinite" begin={`${i * 0.6}s`}><mpath href={`#${id}`} /></animateMotion></circle>)}
      {[[60, 80, "victim"], [280, 50, "split"], [280, 110, "split"], [520, 80, "merge"]].map(([x, y, l]) => <g key={`${x}-${y}`}><circle cx={x as number} cy={y as number} r="12" fill="var(--card)" stroke={C.navy} strokeWidth="2" /><text x={x as number} y={(y as number) + 28} textAnchor="middle" fontSize="10" fill={C.slate}>{l}</text></g>)}
    </svg>
  ),
  network_correlation: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <g stroke={C.line} strokeWidth="1.5" fill="none"><path d="M110 60L170 100M110 60L60 110M60 110L170 100" /><path d="M430 60L490 100M430 60L540 110M490 100L540 110" /></g>
      <path d="M170 100L430 60" stroke={C.teal} strokeWidth="2.5" className="scene-pulse" />
      <path d="M60 110L540 110" stroke={C.amber} strokeWidth="1.5" strokeDasharray="5 5" />
      {[[110, 60], [170, 100], [60, 110], [430, 60], [490, 100], [540, 110]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="9" fill="var(--card)" stroke={C.navy} strokeWidth="2" />)}
      <text x="300" y="45" textAnchor="middle" fontSize="10" fill={C.teal}>corroborated bridge</text>
      <text x="300" y="130" textAnchor="middle" fontSize="10" fill={C.amber}>candidate: shared hosting</text>
    </svg>
  ),
  evidence_scan: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      {[0, 1, 2].map((i) => <rect key={i} x={200 + i * 8} y={20 - i * 4} width="200" height="120" rx="6" fill="var(--card)" stroke={C.line} />)}
      {[40, 58, 76, 94, 112].map((y) => <rect key={y} x="218" y={y} width={y % 3 ? 150 : 110} height="6" rx="3" fill="var(--panel)" />)}
      <rect x="216" y="30" width="206" height="3" fill={C.teal} className="scene-beam" />
      <rect x="300" y="74" width="60" height="10" rx="2" fill="none" stroke={C.copper} strokeWidth="1.5" />
      <text x="470" y="80" fontSize="10" fill={C.slate}>sha256 ••••</text>
      <path d="M440 100h80M440 108h60" stroke={C.line} strokeWidth="1.5" />
    </svg>
  ),
  infrastructure_radar: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <g className="scene-sweep" style={{ transformOrigin: "120px 80px" }}><path d="M120 80 L120 20 A60 60 0 0 1 172 50 Z" fill={C.teal} opacity="0.18" /></g>
      {[20, 40, 60].map((r) => <circle key={r} cx="120" cy="80" r={r} fill="none" stroke={C.line} />)}
      <circle cx="120" cy="80" r="3" fill={C.navy} />
      <g stroke={C.line} strokeWidth="1.5" fill="none"><path d="M220 80h90M340 80h90M460 80h60" /></g>
      {[["domain", 220], ["dns obs.", 340], ["IP", 460], ["host", 540]].map(([l, x]) => <g key={l}><circle cx={x as number} cy="80" r="9" fill="var(--card)" stroke={C.navy} strokeWidth="2" /><text x={x as number} y="104" fontSize="10" textAnchor="middle" fill={C.slate}>{l}</text></g>)}
      <rect x="398" y="68" width="14" height="24" rx="2" fill="none" stroke={C.copper} strokeDasharray="3 3" /><text x="405" y="60" fontSize="9" textAnchor="middle" fill={C.copper}>history unknown</text>
      <path d="M300 30v100" stroke={C.amber} strokeWidth="1.5" fill="none" /><text x="300" y="24" fontSize="9" textAnchor="middle" fill={C.amber}>observed at</text>
    </svg>
  ),
  counterproof: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <circle cx="120" cy="80" r="14" fill="var(--card)" stroke={C.navy} strokeWidth="2" /><text x="120" y="112" fontSize="10" textAnchor="middle" fill={C.slate}>hypothesis</text>
      {[[40, C.ok, "supports"], [80, C.danger, "contradicts"], [120, C.amber, "missing"]].map(([y, col, l], i) => (
        <g key={l as string} className="scene-reveal" style={{ animationDelay: `${i * 0.5}s` }}><path d={`M134 80 C 220 80, 240 ${y}, 320 ${y}`} stroke={col as string} strokeWidth="2" fill="none" /><circle cx="320" cy={y as number} r="8" fill="var(--card)" stroke={col as string} strokeWidth="2" /><text x="340" y={(y as number) + 4} fontSize="10" fill={C.slate}>{l as string}</text></g>
      ))}
    </svg>
  ),
  investigation_timeline: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <path d="M40 90h520" stroke={C.line} strokeWidth="2" fill="none" />
      {[80, 160, 260, 380, 480].map((x, i) => <g key={x}><circle cx={x} cy="90" r={i === 3 ? 7 : 5} fill={i === 3 ? C.copper : C.navy} /><text x={x} y="115" fontSize="9" textAnchor="middle" fill={C.slate}>{["report", "URL seen", "QR", "transfer", "hold"][i]}</text></g>)}
      <g className="scene-cursor"><path d="M80 50v80" stroke={C.teal} strokeWidth="2" /><rect x="68" y="38" width="24" height="12" rx="3" fill={C.teal} /></g>
      <text x="300" y="40" fontSize="10" textAnchor="middle" fill={C.slate}>cursor moves only when you play or scrub</text>
    </svg>
  ),
  recovery_reconciliation: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <rect x="60" y="60" width="480" height="24" rx="6" fill="var(--panel)" />
      {[[60, 180, C.teal, "traced"], [240, 110, C.ok, "held (documented)"], [350, 70, C.navy, "restored"], [420, 120, C.amber, "unresolved"]].map(([x, w, col, l], i) => (
        <g key={l as string} className="scene-grow" style={{ animationDelay: `${i * 0.3}s`, transformOrigin: `${x}px 72px` }}><rect x={x as number} y="60" width={w as number} height="24" rx="6" fill={col as string} /><text x={(x as number) + 6} y="104" fontSize="10" fill={C.slate}>{l as string}</text></g>
      ))}
      <text x="60" y="48" fontSize="10" fill={C.slate}>reported loss (synthetic illustration; real values come from the ledger)</text>
    </svg>
  ),
  campaign_evolution: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <path d="M40 130h520" stroke={C.line} fill="none" />
      {[[60, 220, 40, "domain A"], [260, 420, 40, "domain B"], [60, 180, 75, "vpa 1"], [300, 480, 75, "vpa 2"]].map(([x0, x1, y, l]) => <g key={l as string}><rect x={x0 as number} y={(y as number) - 8} width={(x1 as number) - (x0 as number)} height="16" rx="4" fill={C.teal} opacity="0.75" /><text x={(x0 as number) + 4} y={(y as number) - 12} fontSize="9" fill={C.slate}>{l as string}</text></g>)}
      <rect x="220" y="32" width="40" height="16" rx="4" fill="none" stroke={C.amber} strokeDasharray="3 3" /><text x="240" y="60" fontSize="9" textAnchor="middle" fill={C.amber}>gap: unknown</text>
      <g className="scene-cursor"><path d="M60 20v110" stroke={C.copper} strokeWidth="1.5" /></g>
    </svg>
  ),
  login: () => (
    <svg viewBox="0 0 600 160" className="scene-svg">
      <g stroke={C.line} strokeWidth="1" fill="none"><path d="M60 40L160 90L120 140M160 90L260 60L300 120M260 60L380 100L440 50L540 90L470 140" /></g>
      {[[60, 40], [160, 90], [120, 140], [260, 60], [300, 120], [380, 100], [440, 50], [540, 90], [470, 140]].map(([x, y], i) => <circle key={i} cx={x} cy={y} r="4" fill={i % 3 ? C.navy : C.teal} className={i % 3 ? "" : "scene-pulse-dot"} />)}
      <g className="scene-sweep" style={{ transformOrigin: "300px 80px" }}><path d="M300 80 L300 30 A50 50 0 0 1 343 55 Z" fill={C.teal} opacity="0.12" /></g>
      <path d="M288 70h24v18h-24z" fill="var(--card)" stroke={C.navy} strokeWidth="1.5" /><path d="M292 70v-5a8 8 0 0116 0v5" fill="none" stroke={C.navy} strokeWidth="1.5" />
    </svg>
  ),
  empty: () => (
    <svg viewBox="0 0 600 160" className="scene-svg"><rect x="200" y="40" width="200" height="80" rx="8" fill="var(--panel)" stroke={C.line} strokeDasharray="6 6" /><text x="300" y="85" fontSize="11" textAnchor="middle" fill={C.slate}>no data in this case yet</text></svg>
  ),
};

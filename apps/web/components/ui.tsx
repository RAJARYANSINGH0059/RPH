"use client";

/** Shared page primitives: page template, status chips, key/value, data tables, evidence locators, empty/loading/error states. */
import Link from "next/link";
import { Fragment, useEffect, useState } from "react";
import { I } from "@/components/icons";
import { apiGet, fmtTime, invalidateCache, paise, peekCache } from "@/lib/api";
import { EVIDENCE_LEVEL_HELP } from "@/lib/guide";

/** Shown while a page waits. After a few seconds it says why, because the free-plan API sleeps when idle and a silent
 * skeleton makes a waking service look like a broken one. */
function Waiting() {
  const [secs, setSecs] = useState(0);
  useEffect(() => { const t = setInterval(() => setSecs((s) => s + 1), 1000); return () => clearInterval(t); }, []);
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      <div className="skeleton h-10" /><div className="skeleton h-24" /><div className="skeleton h-24" />
      {secs >= 4 && <p className="text-xs muted" role="status">Waiting for the analysis API ({secs}s). Free-plan services sleep when idle; the request is being retried automatically and the page will fill in once it wakes.</p>}
    </div>
  );
}

export function State({ loading, error, empty, children, onRetry }: { loading?: boolean; error?: string | null; empty?: React.ReactNode; children?: React.ReactNode; onRetry?: () => void }) {
  if (loading) return <Waiting />;
  if (error) {
    const denied = /not found|403|forbidden|insufficient/i.test(error);
    return <div className="card flex items-start gap-2 border-danger/30 bg-danger-soft text-sm text-danger" role="alert"><I.alert className="shrink-0" /><div className="flex-1"><div className="font-semibold">{denied ? "Not available to this account" : "Could not load"}</div><div>{error}</div></div>{onRetry && <button className="btn-secondary" onClick={onRetry}>Retry</button>}</div>;
  }
  if (empty) return <div className="card border-dashed text-center text-sm muted">{empty}</div>;
  return <>{children}</>;
}

/** Fetch helper for page components: returns {data, error, reload}.
 * A previously loaded path renders from the in-memory cache at once and revalidates in the background, so returning to a
 * screen is instant instead of a fresh round trip; `reload()` always refetches. */
export function useApi<T = any>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(() => (path ? peekCache<T>(path)?.data ?? null : null));
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) return;
    let alive = true;
    const hit = peekCache<T>(path);
    setError(null);
    setData(hit ? hit.data : null);
    if (hit?.fresh && tick === 0) return;           // recent enough: no request at all
    apiGet<T>(path).then((d) => alive && setData(d)).catch((e) => {
      if (!alive) return;
      if (hit) return;                              // keep showing cached data if a background revalidation fails
      setError(e.message);
    });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...deps]);
  return { data, error, reload: () => { invalidateCache(); setTick((t) => t + 1); }, loading: !data && !error && !!path };
}

const CHIP: Record<string, string> = {
  directly_observed: "lvl-directly_observed", observed: "lvl-directly_observed", corroborated: "lvl-corroborated", derived: "lvl-derived", candidate: "lvl-candidate", contradicted: "lvl-contradicted", stale: "lvl-stale",
  insufficient: "lvl-insufficient", unresolved: "lvl-insufficient", reported: "lvl-derived", extracted: "lvl-candidate", supported: "lvl-directly_observed", contested: "lvl-candidate",
  verified: "bg-ok-soft text-ok", success: "bg-ok-soft text-ok", synthetic: "bg-terracotta text-white", simulated: "bg-terracotta text-white", live: "bg-ok-soft text-ok", mock: "bg-saffron-soft text-warn", not_configured: "lvl-insufficient", configured: "lvl-derived", unavailable: "lvl-contradicted",
  STABLE: "bg-ok-soft text-ok", FRAGILE: "lvl-candidate", CHANGED: "lvl-contradicted", UNRESOLVED: "lvl-insufficient", high: "lvl-contradicted", medium: "lvl-candidate", low: "lvl-derived",
  COMPLETE_COVERAGE: "lvl-corroborated", PARTIAL_COVERAGE: "lvl-candidate", NOT_SUPPLIED: "lvl-contradicted", PARSE_FAILED: "lvl-contradicted", OCR_UNRELIABLE: "lvl-candidate", CURRENT_ONLY: "lvl-stale", HISTORICAL_UNKNOWN: "lvl-stale", OBSERVED_ZERO: "lvl-corroborated", UNKNOWN: "lvl-insufficient",
  DIRECTLY_OBSERVED: "lvl-directly_observed", CORROBORATED: "lvl-corroborated", DERIVED: "lvl-derived", CANDIDATE: "lvl-candidate", CONTRADICTED: "lvl-contradicted", PARTIAL: "lvl-candidate", UNASSESSED: "lvl-insufficient", NOT_APPLICABLE: "lvl-insufficient",
  REVIEW_REQUIRED: "lvl-candidate", CONFLICTING_EVIDENCE: "lvl-contradicted", INDETERMINATE: "lvl-insufficient", HUMAN_REVIEWED: "lvl-corroborated",
};
const CHIP_ICON: Record<string, string> = { contradicted: "✗", CONTRADICTED: "✗", stale: "◷", CURRENT_ONLY: "◷", HISTORICAL_UNKNOWN: "?", candidate: "?", CANDIDATE: "?", corroborated: "✓✓", CORROBORATED: "✓✓", directly_observed: "✓", DIRECTLY_OBSERVED: "✓", supported: "✓", verified: "✓", unresolved: "…", NOT_SUPPLIED: "∅", UNKNOWN: "?", synthetic: "⚑", simulated: "⚑" };

/** Status chip: text + glyph + colour (never colour alone). */
export function Chip({ v, title }: { v: string | null | undefined; title?: string }) {
  if (!v) return <span className="badge lvl-insufficient">—</span>;
  return <span className={`badge ${CHIP[v] || "bg-panel text-ink"}`} title={title || EVIDENCE_LEVEL_HELP[v] || v}>{CHIP_ICON[v] ? <span aria-hidden>{CHIP_ICON[v]}</span> : null}{v.replace(/_/g, " ")}</span>;
}
export const LevelBadge = ({ level }: { level: string }) => <Chip v={level} />;

export function KV({ rows, className = "" }: { rows: [string, React.ReactNode][]; className?: string }) {
  return <dl className={`grid grid-cols-[minmax(120px,max-content)_1fr] gap-x-4 gap-y-1.5 text-sm ${className}`}>{rows.map(([k, v], i) => <Fragment key={k + i}><dt className="muted">{k}</dt><dd className="min-w-0 break-words">{v ?? "—"}</dd></Fragment>)}</dl>;
}

/** Headline figure: the label reads first in small caps, the value is large enough to take in at a glance, and the hint
 * says what the number means. Used for every summary tile so the key numbers look the same everywhere. */
export function Stat({ label, value, hint, href, tone }: { label: string; value: React.ReactNode; hint?: string; href?: string; tone?: "warn" | "ok" | "info" }) {
  const ring = tone === "warn" ? "border-saffron/50" : tone === "ok" ? "border-ok/30" : "";
  const body = (
    <div className={`metric ${ring} ${href ? "transition hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]" : ""}`}>
      <div className="label mb-0">{label}</div>
      <div className="metric-value mt-2">{value}</div>
      {hint && <div className="mt-2 text-xs leading-snug muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block h-full">{body}</Link> : body;
}

export function Copyable({ value, className = "" }: { value: string; className?: string }) {
  const [done, setDone] = useState(false);
  return <span className={`inline-flex max-w-full items-center gap-1 ${className}`}><span className="mono truncate" title={value}>{value}</span><button className="btn-ghost !p-1" aria-label="Copy value" onClick={() => { try { navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1200); } catch { /* ignore */ } }}>{done ? <I.check width={12} height={12} /> : <I.file width={12} height={12} />}</button></span>;
}

/** Evidence locator: file + sha256 prefix + row/page/cell/json path. Links to the vault entry when a case is known. */
export function Locator({ caseId, fileId, file, sha256, locator, evidenceId }: { caseId?: string; fileId?: string | null; file?: string | null; sha256?: string | null; locator?: Record<string, any> | null; evidenceId?: string | null }) {
  const parts = locator ? Object.entries(locator).filter(([k, v]) => v !== null && v !== undefined && !["bbox", "boxes"].includes(k)).map(([k, v]) => `${k} ${Array.isArray(v) ? v.join("–") : String(v)}`).slice(0, 4) : [];
  const inner = <span className="mono text-[11px]">{file || (evidenceId ? `evidence ${evidenceId.slice(0, 8)}` : "source")}{sha256 ? ` · ${sha256.slice(0, 10)}…` : ""}{parts.length ? ` · ${parts.join(" · ")}` : ""}</span>;
  return caseId && fileId ? <Link href={`/cases/${caseId}/vault?file=${fileId}`} className="text-accent hover:underline">{inner}</Link> : inner;
}

export function Table({ cols, rows, empty = "Nothing to show.", dense }: { cols: (string | React.ReactNode)[]; rows: React.ReactNode[][]; empty?: React.ReactNode; dense?: boolean }) {
  return (
    <div className="card overflow-x-auto p-0">
      <table className={`data ${dense ? "text-xs" : ""}`}><thead><tr>{cols.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
        <tbody>{rows.length === 0 ? <tr><td colSpan={cols.length} className="py-6 text-center muted">{empty}</td></tr> : rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>
    </div>
  );
}

export function Section({ title, hint, children, actions, className = "" }: { title: React.ReactNode; hint?: string; children: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return <section className={`card ${className}`}><div className="mb-3.5 flex flex-wrap items-start justify-between gap-2"><div className="min-w-0"><h2 className="section-title">{title}</h2>{hint && <p className="mt-1 max-w-3xl text-xs leading-relaxed muted">{hint}</p>}</div>{actions}</div>{children}</section>;
}

export function Limitations({ items, title = "Limitations" }: { items?: string[]; title?: string }) {
  if (!items?.length) return null;
  return <div className="callout-warn text-xs"><I.shield className="shrink-0" width={16} height={16} /><div><div className="font-semibold">{title}</div><ul className="list-disc pl-4">{items.map((x) => <li key={x}>{x}</li>)}</ul></div></div>;
}

export function Money({ v }: { v: number | null | undefined }) { return <span className="num">{paise(v)}</span>; }
export function When({ v }: { v: string | null | undefined }) { return <span className="mono text-xs">{fmtTime(v)}</span>; }
export function Dir({ v }: { v: string | null | undefined }) {
  return <span className={`badge ${v === "debit" ? "bg-saffron-soft text-warn" : v === "credit" ? "bg-ok-soft text-ok" : "bg-panel text-ink"}`}>{v || "unknown"}</span>;
}

/** Primary action bar for the page template: one dominant action, optional secondaries. */
export function Actions({ primary, children }: { primary?: React.ReactNode; children?: React.ReactNode }) {
  return <div className="flex flex-wrap items-center gap-2">{children}{primary}</div>;
}

export function Toast({ msg, tone = "info", onClose }: { msg: string | null; tone?: "info" | "ok" | "warn"; onClose?: () => void }) {
  if (!msg) return null;
  return <div role="status" className={`card flex items-start justify-between gap-2 text-sm ${tone === "ok" ? "border-ok/30" : tone === "warn" ? "border-saffron/50" : ""}`}><span>{msg}</span>{onClose && <button className="btn-icon !h-7 !w-7" onClick={onClose} aria-label="Dismiss"><I.close width={14} height={14} /></button>}</div>;
}

/** Collapsible raw JSON for power users: never the only presentation of a result. */
export function Raw({ data, label = "Raw result (JSON)" }: { data: unknown; label?: string }) {
  return <details className="text-xs"><summary className="cursor-pointer muted">{label}</summary><pre className="mono mt-2 max-h-80 overflow-auto rounded-lg bg-panel p-3 text-[11px]">{JSON.stringify(data, null, 1)}</pre></details>;
}

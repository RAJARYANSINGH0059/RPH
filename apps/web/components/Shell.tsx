"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { I } from "@/components/icons";
import { clearSession, getUser, type User } from "@/lib/api";
import { EVIDENCE_LEVEL_HELP, GUIDE, STEPS } from "@/lib/guide";

export function Banner({ synthetic, uploaded }: { synthetic?: boolean; uploaded?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
      {synthetic && <span className="rounded-full bg-terracotta px-2.5 py-0.5 text-white">Synthetic demo</span>}
      {uploaded && <span className="rounded-full bg-ink px-2.5 py-0.5 text-white">Uploaded evidence</span>}
      <span className="rounded-full border border-terracotta/60 px-2.5 py-0.5 text-terracotta">No live police/bank connection</span>
      <span className="hidden rounded-full border border-line-strong px-2.5 py-0.5 text-ink-muted sm:inline">Human verification required</span>
    </div>
  );
}

const ONBOARD_KEY = "ps05x_onboarded_v3";

function Welcome({ onClose }: { onClose: () => void }) {
  const steps = [
    { icon: <I.factory />, t: "Generate a demo case", d: "The Synthetic Case Factory creates a fictional investigation with messy files. No credentials, no real data." },
    { icon: <I.upload />, t: "Or upload your own files", d: "Statements (CSV/XLSX), complaints (PDF/DOCX), scans and screenshots (OCR), technical observations (JSON)." },
    { icon: <I.money />, t: "Follow the money", d: "Transactions, warnings, reconstructed paths with unresolved hops made explicit, and cross-case bridges." },
    { icon: <I.graph />, t: "Inspect, don't assume", d: "Every relationship carries its source, time validity, limitations and counter-evidence. Then reconcile claims and export." },
  ];
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="welcome-title" className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <div className="card w-full max-w-2xl p-6">
        <div className="flex items-start justify-between gap-4">
          <div><div className="eyebrow">PS05-X · Investigative prototype</div><h2 id="welcome-title" className="mt-1 text-xl font-bold">Welcome to the workbench</h2><p className="mt-1 text-sm muted">Four steps cover everything. The Help button on every page explains that page&apos;s inputs and outputs.</p></div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><I.close /></button>
        </div>
        <ol className="mt-5 grid gap-3 sm:grid-cols-2">
          {steps.map((s, i) => (
            <li key={s.t} className="inset flex gap-3 p-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent-deep">{s.icon}</div>
              <div><div className="text-sm font-semibold"><span className="mr-1 muted">{i + 1}.</span>{s.t}</div><div className="text-xs muted">{s.d}</div></div>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
          <Link href="/guide" className="text-sm text-accent-deep underline" onClick={onClose}>Read the full guide</Link>
          <div className="flex gap-2"><Link href="/factory" className="btn" onClick={onClose}><I.factory /> Generate a demo case</Link><button className="btn-secondary" onClick={onClose}>Explore on my own</button></div>
        </div>
      </div>
    </div>
  );
}

export function HelpDrawer({ pageKey, onClose }: { pageKey: string; onClose: () => void }) {
  const g = GUIDE[pageKey];
  if (!g) return null;
  return (
    <aside role="dialog" aria-label={`Help: ${g.title}`} className="fixed inset-y-0 right-0 z-40 w-full max-w-md overflow-y-auto border-l border-line bg-card p-5 shadow-xl">
      <div className="flex items-start justify-between gap-3"><div><div className="eyebrow">How to use</div><h2 className="text-lg font-bold">{g.title}</h2></div><button className="btn-icon" onClick={onClose} aria-label="Close help"><I.close /></button></div>
      <p className="mt-2 text-sm">{g.purpose}</p>
      <Section title="What you give it" items={g.inputs} />
      <Section title="What you get" items={g.outputs} />
      <Section title="Tips" items={g.tips} />
      {pageKey === "graph" && <div className="mt-4"><div className="label">Evidence levels</div><ul className="space-y-1 text-xs">{Object.entries(EVIDENCE_LEVEL_HELP).map(([k, v]) => <li key={k}><LevelBadge level={k} /> <span className="muted">{v}</span></li>)}</ul></div>}
      <Link href="/guide" className="mt-5 inline-flex items-center gap-1 text-sm text-accent-deep underline" onClick={onClose}><I.guide /> Open the full guide</Link>
    </aside>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return <div className="mt-4"><div className="label">{title}</div><ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x) => <li key={x}>{x}</li>)}</ul></div>;
}

export function Stepper({ caseId, current }: { caseId: string; current: string }) {
  const idx = STEPS.findIndex((s) => s.key === current);
  return (
    <nav aria-label="Investigation steps" className="card mb-4 overflow-x-auto p-1.5">
      <ol className="flex min-w-max items-center gap-1">
        {STEPS.map((s, i) => {
          const state = i < idx ? "done" : i === idx ? "current" : "todo";
          return (
            <li key={s.key} className="flex items-center">
              <Link href={s.href(caseId)} title={s.hint} aria-current={state === "current" ? "step" : undefined}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm transition ${state === "current" ? "bg-accent text-white" : state === "done" ? "text-accent-deep hover:bg-accent-soft" : "muted hover:bg-panel"}`}>
                <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${state === "current" ? "bg-white/25" : state === "done" ? "bg-accent-soft" : "bg-panel"}`}>{state === "done" ? <I.check width={12} height={12} /> : i + 1}</span>
                <span className="font-medium">{s.label}</span>
                <span className="hidden text-xs opacity-80 xl:inline">· {s.hint}</span>
              </Link>
              {i < STEPS.length - 1 && <span className="mx-1 text-line-strong">›</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default function Shell({ children, caseId, caseTitle, synthetic, uploaded, title, subtitle, pageKey, step, actions }: { children: React.ReactNode; caseId?: string; caseTitle?: string; synthetic?: boolean; uploaded?: boolean; title?: string; subtitle?: string; pageKey?: string; step?: string; actions?: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [help, setHelp] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const u = getUser();
    if (!u) router.replace("/");
    setUser(u);
    try { if (!window.localStorage.getItem(ONBOARD_KEY)) setWelcome(true); } catch { /* ignore */ }
  }, [router]);
  useEffect(() => { setOpen(false); }, [path]);
  const closeWelcome = () => { setWelcome(false); try { window.localStorage.setItem(ONBOARD_KEY, "1"); } catch { /* ignore */ } };
  const nav = caseId
    ? [
        { href: "/cases", label: "Cases", icon: <I.cases /> },
        { href: `/cases/${caseId}/upload`, label: "Upload Evidence", icon: <I.upload /> },
        { href: `/cases/${caseId}/graph`, label: "Investigation Graph", icon: <I.graph /> },
        { href: `/cases/${caseId}/timeline`, label: "Timeline", icon: <I.timeline /> },
        { href: `/cases/${caseId}/reports`, label: "Reports", icon: <I.report /> },
        { href: "/sources", label: "Data Sources", icon: <I.sources /> },
      ]
    : [
        { href: "/cases", label: "Cases", icon: <I.cases /> },
        { href: "/factory", label: "Synthetic Case Factory", icon: <I.factory /> },
        { href: "/crosscase", label: "Cross-case Correlation", icon: <I.link /> },
        { href: "/guide", label: "How to use", icon: <I.guide /> },
        { href: "/sources", label: "Data Sources", icon: <I.sources /> },
      ];
  const caseTools = caseId ? [
    { href: `/cases/${caseId}`, label: "Overview", icon: <I.layers width={14} height={14} /> },
    { href: `/cases/${caseId}/transactions`, label: "Transactions & fund flow", icon: <I.money width={14} height={14} /> },
    { href: `/cases/${caseId}/crosscase`, label: "Related cases", icon: <I.link width={14} height={14} /> },
    { href: `/cases/${caseId}/claims`, label: "Victim claims", icon: <I.shield width={14} height={14} /> },
    { href: `/cases/${caseId}/cooperation`, label: "Cooperation pack", icon: <I.file width={14} height={14} /> },
  ] : [];
  const crumbs = [{ href: "/cases", label: "Cases" }, ...(caseId ? [{ href: `/cases/${caseId}`, label: caseTitle || "Case" }] : []), ...(title ? [{ href: path, label: title }] : [])];

  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:p-2">Skip to content</a>
      <aside className="jaali flex flex-col bg-rail text-rail-text md:sticky md:top-0 md:h-screen md:w-64 md:shrink-0">
        <div className="flex items-center justify-between gap-3 px-4 py-4">
          <Link href="/cases" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white shadow"><I.shield /></div>
            <div><div className="text-base font-bold leading-tight tracking-tight text-white">PS05-X</div><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-rail-text/70">Investigative prototype</div></div>
          </Link>
          <button className="rounded-lg p-2 text-rail-text hover:bg-white/10 md:hidden" aria-expanded={open} aria-controls="primary-nav" aria-label="Toggle navigation" onClick={() => setOpen((v) => !v)}><I.layers /></button>
        </div>
        <nav id="primary-nav" aria-label="Primary" className={`${open ? "flex" : "hidden"} flex-col gap-0.5 px-2 pb-3 md:flex`}>
          {nav.map((n) => {
            const active = path === n.href || (n.href !== "/cases" && path.startsWith(n.href));
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition ${active ? "bg-white/12 font-semibold text-white shadow-inner ring-1 ring-white/10" : "text-rail-text/85 hover:bg-white/8 hover:text-white"}`}>
                <span className={active ? "text-saffron" : "text-rail-text/70"}>{n.icon}</span>{n.label}
              </Link>
            );
          })}
          {caseId && (
            <div className="mx-1 mt-3 rounded-lg border border-white/10 bg-white/5 p-2.5 text-xs">
              <div className="mb-1.5 flex items-center justify-between"><span className="font-semibold uppercase tracking-wide text-rail-text/70">This case</span>{synthetic && <span className="rounded bg-terracotta px-1.5 py-0.5 text-[10px] font-bold uppercase text-white">Synthetic</span>}</div>
              <div className="mb-2 truncate font-medium text-white" title={caseTitle}>{caseTitle || caseId.slice(0, 8)}</div>
              <div className="flex flex-col gap-0.5">{caseTools.map((t) => <Link key={t.href} className={`flex items-center gap-1.5 rounded px-1.5 py-1 hover:bg-white/10 ${path === t.href ? "text-saffron" : "text-rail-text"}`} href={t.href}>{t.icon}{t.label}</Link>)}</div>
            </div>
          )}
        </nav>
        <div className={`${open ? "block" : "hidden"} mt-auto space-y-2 border-t border-white/10 px-4 py-4 text-xs text-rail-text/80 md:block`}>
          <button className="flex items-center gap-1.5 hover:text-white" onClick={() => setWelcome(true)}><I.play width={14} height={14} /> Quick tour</button>
          {user && <div className="truncate"><span className="font-medium text-white">{user.display_name}</span> <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-bold uppercase">{user.role}</span></div>}
          <button className="flex items-center gap-1.5 hover:text-white" onClick={() => { clearSession(); router.push("/"); }}><I.logout width={14} height={14} /> Sign out</button>
        </div>
      </aside>
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-line bg-card/85 backdrop-blur">
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 md:px-6">
            <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1 text-xs muted">
              {crumbs.map((c, i) => <span key={c.href + i} className="flex min-w-0 items-center gap-1">{i > 0 && <span className="text-line-strong">/</span>}{i < crumbs.length - 1 ? <Link href={c.href} className="truncate hover:underline">{c.label}</Link> : <span className="truncate font-medium text-ink">{c.label}</span>}</span>)}
            </nav>
            <Banner synthetic={synthetic} uploaded={uploaded} />
          </div>
        </header>
        <main id="main" className="p-4 md:p-6">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              {title && <h1 className="truncate text-2xl font-bold tracking-tight">{title}</h1>}
              {subtitle && <p className="mt-0.5 text-sm muted">{subtitle}</p>}
            </div>
            <div className="flex items-center gap-2">
              {actions}
              {pageKey && <button className="btn-secondary" onClick={() => setHelp(true)} aria-haspopup="dialog"><I.help /> Help</button>}
            </div>
          </div>
          {caseId && step && <Stepper caseId={caseId} current={step} />}
          {children}
        </main>
      </div>
      {help && pageKey && <><div className="fixed inset-0 z-30 bg-ink/25" onClick={() => setHelp(false)} aria-hidden /><HelpDrawer pageKey={pageKey} onClose={() => setHelp(false)} /></>}
      {welcome && <Welcome onClose={closeWelcome} />}
    </div>
  );
}

export function State({ loading, error, empty, children, onRetry }: { loading?: boolean; error?: string | null; empty?: React.ReactNode; children?: React.ReactNode; onRetry?: () => void }) {
  if (loading) return <div className="space-y-2" role="status" aria-label="Loading"><div className="skeleton h-10" /><div className="skeleton h-24" /><div className="skeleton h-24" /></div>;
  if (error) return <div className="card flex items-start gap-2 border-danger/30 bg-danger-soft text-sm text-danger" role="alert"><I.alert className="shrink-0" /><div className="flex-1">{error}</div>{onRetry && <button className="btn-secondary" onClick={onRetry}>Retry</button>}</div>;
  if (empty) return <div className="card border-dashed text-center text-sm muted">{empty}</div>;
  return <>{children}</>;
}

export function LevelBadge({ level }: { level: string }) {
  return <span className={`badge lvl-${level}`} title={EVIDENCE_LEVEL_HELP[level]}>{level.replace("_", " ")}</span>;
}

export function SourceBadge({ kind }: { kind: "synthetic" | "uploaded" | "connector" | "licensed" }) {
  const map = { synthetic: ["bg-terracotta text-white", "Synthetic"], uploaded: ["bg-ink text-white", "Uploaded"], connector: ["bg-panel text-ink", "Connector · current snapshot"], licensed: ["bg-accent-soft text-accent-deep", "Licensed feed"] } as const;
  return <span className={`badge ${map[kind][0]}`}>{map[kind][1]}</span>;
}

export function Stat({ label, value, hint, href, tone }: { label: string; value: React.ReactNode; hint?: string; href?: string; tone?: "warn" | "ok" | "info" }) {
  const ring = tone === "warn" ? "border-saffron/50" : tone === "ok" ? "border-ok/30" : "";
  const body = (
    <div className={`card h-full ${ring} ${href ? "transition hover:-translate-y-0.5 hover:shadow-md" : ""}`}>
      <div className="label mb-0">{label}</div>
      <div className="num mt-1 text-2xl font-bold tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 text-xs muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

export function Copyable({ value, className = "" }: { value: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <span className={`inline-flex max-w-full items-center gap-1 ${className}`}>
      <span className="mono truncate" title={value}>{value}</span>
      <button className="btn-ghost !p-1" aria-label="Copy value" onClick={() => { try { navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1200); } catch { /* ignore */ } }}>{done ? <I.check width={12} height={12} /> : <I.file width={12} height={12} />}</button>
    </span>
  );
}

"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { I } from "@/components/icons";
import { clearSession, getUser, type User } from "@/lib/api";
import { EVIDENCE_LEVEL_HELP, GUIDE, STEPS } from "@/lib/guide";

export function Banner({ synthetic }: { synthetic?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
      {synthetic && <span className="rounded-full bg-synthetic px-2.5 py-0.5 text-white">Synthetic data</span>}
      <span className="rounded-full border border-synthetic/60 px-2.5 py-0.5 text-synthetic">No live police/bank connection</span>
      <span className="hidden rounded-full border border-line px-2.5 py-0.5 text-ink-muted sm:inline">Investigative aid · human verification required</span>
    </div>
  );
}

const ONBOARD_KEY = "ps05x_onboarded_v2";

function Welcome({ onClose }: { onClose: () => void }) {
  const steps = [
    { icon: <I.factory />, t: "Generate a demo case", d: "Synthetic Case Factory creates a fictional investigation with messy files. No credentials, no real data." },
    { icon: <I.upload />, t: "Or upload your own files", d: "Statements (CSV/XLSX), complaints (PDF/DOCX), technical observations (JSON). Every value keeps its source position." },
    { icon: <I.money />, t: "Follow the money", d: "Transactions, duplicate and date warnings, and reconstructed multi-hop paths." },
    { icon: <I.graph />, t: "Inspect, don't assume", d: "Click any relationship for its evidence, time validity, limitations and counter-evidence. Then export a report." },
  ];
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="welcome-title" className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
      <div className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div><h2 id="welcome-title" className="text-xl font-bold">Welcome to PS05-X</h2><p className="mt-1 text-sm text-ink-muted">Four steps cover everything. The Help button on every page explains that page&apos;s inputs and outputs.</p></div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><I.close /></button>
        </div>
        <ol className="mt-5 grid gap-3 sm:grid-cols-2">
          {steps.map((s, i) => (
            <li key={s.t} className="flex gap-3 rounded-xl border border-line bg-[#fbfcfd] p-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-light text-accent">{s.icon}</div>
              <div><div className="text-sm font-semibold"><span className="mr-1 text-ink-muted">{i + 1}.</span>{s.t}</div><div className="text-xs text-ink-muted">{s.d}</div></div>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-2">
          <Link href="/guide" className="text-sm text-accent underline" onClick={onClose}>Read the full guide</Link>
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
    <aside role="dialog" aria-label={`Help: ${g.title}`} className="fixed inset-y-0 right-0 z-40 w-full max-w-md overflow-y-auto border-l border-line bg-white p-5 shadow-xl">
      <div className="flex items-start justify-between gap-3"><div><div className="text-xs font-semibold uppercase tracking-wide text-accent">How to use</div><h2 className="text-lg font-bold">{g.title}</h2></div><button className="btn-icon" onClick={onClose} aria-label="Close help"><I.close /></button></div>
      <p className="mt-2 text-sm">{g.purpose}</p>
      <Section title="What you give it" items={g.inputs} />
      <Section title="What you get" items={g.outputs} />
      <Section title="Tips" items={g.tips} />
      {pageKey === "graph" && (
        <div className="mt-4"><div className="label">Evidence levels</div><ul className="space-y-1 text-xs">{Object.entries(EVIDENCE_LEVEL_HELP).map(([k, v]) => <li key={k}><LevelBadge level={k} /> <span className="text-ink-muted">{v}</span></li>)}</ul></div>
      )}
      <Link href="/guide" className="mt-5 inline-flex items-center gap-1 text-sm text-accent underline" onClick={onClose}><I.guide /> Open the full guide</Link>
    </aside>
  );
}

function Section({ title, items }: { title: string; items: string[] }) {
  return <div className="mt-4"><div className="label">{title}</div><ul className="list-disc space-y-1 pl-5 text-sm">{items.map((x) => <li key={x}>{x}</li>)}</ul></div>;
}

export function Stepper({ caseId, current }: { caseId: string; current: string }) {
  const idx = STEPS.findIndex((s) => s.key === current);
  return (
    <nav aria-label="Investigation steps" className="card mb-4 overflow-x-auto p-2">
      <ol className="flex min-w-max items-center gap-1">
        {STEPS.map((s, i) => {
          const state = i < idx ? "done" : i === idx ? "current" : "todo";
          return (
            <li key={s.key} className="flex items-center">
              <Link href={s.href(caseId)} title={s.hint} aria-current={state === "current" ? "step" : undefined}
                className={`flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm ${state === "current" ? "bg-accent text-white" : state === "done" ? "text-accent-dark hover:bg-accent-light" : "text-ink-muted hover:bg-[#f1f4f7]"}`}>
                <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${state === "current" ? "bg-white/25" : state === "done" ? "bg-accent-light" : "bg-[#eef1f4]"}`}>{state === "done" ? <I.check width={12} height={12} /> : i + 1}</span>
                <span className="font-medium">{s.label}</span>
                <span className="hidden text-xs opacity-80 lg:inline">· {s.hint}</span>
              </Link>
              {i < STEPS.length - 1 && <span className="mx-1 text-line">›</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default function Shell({ children, caseId, synthetic, title, subtitle, pageKey, step, actions }: { children: React.ReactNode; caseId?: string; synthetic?: boolean; title?: string; subtitle?: string; pageKey?: string; step?: string; actions?: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [help, setHelp] = useState(false);
  const [welcome, setWelcome] = useState(false);
  useEffect(() => {
    const u = getUser();
    if (!u) router.replace("/");
    setUser(u);
    try { if (!window.localStorage.getItem(ONBOARD_KEY)) setWelcome(true); } catch { /* ignore */ }
  }, [router]);
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
        { href: "/guide", label: "How to use", icon: <I.guide /> },
        { href: "/sources", label: "Data Sources", icon: <I.sources /> },
      ];
  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <aside className="flex flex-col border-b border-line bg-white md:sticky md:top-0 md:h-screen md:w-64 md:border-b-0 md:border-r">
        <div className="flex items-center gap-3 px-4 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent text-white"><I.shield /></div>
          <div><Link href="/cases" className="text-base font-bold leading-tight tracking-tight">PS05-X</Link><div className="text-[11px] text-ink-muted">Investigation workbench</div></div>
        </div>
        <nav aria-label="Primary" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {nav.map((n) => {
            const active = path === n.href || (n.href !== "/cases" && path.startsWith(n.href));
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={`flex items-center gap-2.5 whitespace-nowrap rounded-lg px-3 py-2 text-sm ${active ? "bg-accent-light font-semibold text-accent-dark" : "text-ink hover:bg-[#f1f4f7]"}`}>
                <span className={active ? "text-accent" : "text-ink-muted"}>{n.icon}</span>{n.label}
              </Link>
            );
          })}
        </nav>
        {caseId && (
          <div className="mx-3 mt-3 rounded-lg border border-line bg-[#fbfcfd] p-3 text-xs">
            <div className="mb-1 font-semibold text-ink-muted">This case</div>
            <div className="flex flex-col gap-1">
              <Link className="flex items-center gap-1.5 text-accent hover:underline" href={`/cases/${caseId}`}><I.layers width={14} height={14} /> Overview</Link>
              <Link className="flex items-center gap-1.5 text-accent hover:underline" href={`/cases/${caseId}/transactions`}><I.money width={14} height={14} /> Transactions &amp; fund flow</Link>
            </div>
          </div>
        )}
        <div className="mt-auto space-y-2 px-4 py-4 text-xs text-ink-muted">
          <button className="flex items-center gap-1.5 hover:text-ink" onClick={() => setWelcome(true)}><I.play width={14} height={14} /> Show quick tour</button>
          {user && <div className="truncate"><span className="font-medium text-ink">{user.display_name}</span> <span className="badge bg-[#eef1f4] text-ink-muted">{user.role}</span></div>}
          <button className="flex items-center gap-1.5 hover:text-ink" onClick={() => { clearSession(); router.push("/"); }}><I.logout width={14} height={14} /> Sign out</button>
        </div>
      </aside>
      <main id="main" className="min-w-0 flex-1 p-4 md:p-6">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h1 className="truncate text-2xl font-bold tracking-tight">{title}</h1>}
            {subtitle && <p className="text-sm text-ink-muted">{subtitle}</p>}
            <div className="mt-1.5"><Banner synthetic={synthetic} /></div>
          </div>
          <div className="flex items-center gap-2">
            {actions}
            {pageKey && <button className="btn-secondary" onClick={() => setHelp(true)} aria-haspopup="dialog"><I.help /> Help</button>}
          </div>
        </div>
        {caseId && step && <Stepper caseId={caseId} current={step} />}
        {children}
      </main>
      {help && pageKey && <><div className="fixed inset-0 z-30 bg-ink/20" onClick={() => setHelp(false)} aria-hidden /><HelpDrawer pageKey={pageKey} onClose={() => setHelp(false)} /></>}
      {welcome && <Welcome onClose={closeWelcome} />}
    </div>
  );
}

export function State({ loading, error, empty, children }: { loading?: boolean; error?: string | null; empty?: React.ReactNode; children?: React.ReactNode }) {
  if (loading) return <div className="card flex items-center gap-3 text-sm text-ink-muted" role="status"><span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />Loading…</div>;
  if (error) return <div className="card flex items-start gap-2 border-[#f1c5c5] bg-[#fff5f5] text-sm text-[#8a1c1c]" role="alert"><I.alert /><div>{error}</div></div>;
  if (empty) return <div className="card border-dashed text-center text-sm text-ink-muted">{empty}</div>;
  return <>{children}</>;
}

export function LevelBadge({ level }: { level: string }) {
  const map: Record<string, string> = { directly_observed: "bg-[#e7eff9] text-[#174a84]", corroborated: "bg-[#e3f3f0] text-[#136f63]", derived: "bg-[#eef1f4] text-[#3d4852]", candidate: "bg-[#fdf3e0] text-[#8a5a0f]", contradicted: "bg-[#fde8e8] text-[#8a1c1c]", stale: "bg-[#f2ebe8] text-[#6d4c41]", insufficient: "bg-[#eef1f4] text-ink-muted" };
  return <span className={`badge ${map[level] || "bg-[#eef1f4]"}`} title={EVIDENCE_LEVEL_HELP[level]}>{level.replace("_", " ")}</span>;
}

export function Stat({ label, value, hint, href, tone }: { label: string; value: React.ReactNode; hint?: string; href?: string; tone?: "warn" | "ok" | "info" }) {
  const ring = tone === "warn" ? "border-[#f3dfb4]" : tone === "ok" ? "border-[#cfe9e3]" : "border-line";
  const body = (
    <div className={`card h-full ${ring} ${href ? "transition hover:-translate-y-0.5 hover:shadow-md" : ""}`}>
      <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-ink-muted">{hint}</div>}
    </div>
  );
  return href ? <Link href={href} className="block">{body}</Link> : body;
}

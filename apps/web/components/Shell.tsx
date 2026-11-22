"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { I, type IconName } from "@/components/icons";
import { api, getCaseContext, getUser, isDemo, setCaseContext, signOut, type User } from "@/lib/api";
import { EVIDENCE_LEVEL_HELP, GUIDE, WALKTHROUGH } from "@/lib/guide";
import { NAV, UTILITY, hrefFor, matchRoute, type NavChild, type NavGroup } from "@/lib/nav";
export { State, LevelBadge, Stat, Copyable } from "@/components/ui";

const ONBOARD_KEY = "ps05x_onboarded_v4";
const SIDEBAR_KEY = "ps05x_sidebar_v4";

export function Banner({ synthetic, uploaded, demo }: { synthetic?: boolean; uploaded?: boolean; demo?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
      {(synthetic || demo) && <span className="whitespace-nowrap rounded-full bg-terracotta px-2.5 py-0.5 text-white">{demo ? "Synthetic demo — not real case data" : "Synthetic"}</span>}
      {uploaded && <span className="whitespace-nowrap rounded-full bg-ink px-2.5 py-0.5 text-white">Uploaded evidence</span>}
      <span className="whitespace-nowrap rounded-full border border-terracotta/60 px-2.5 py-0.5 text-terracotta">No live police/bank connection</span>
      <span className="hidden whitespace-nowrap rounded-full border border-line-strong px-2.5 py-0.5 text-ink-muted xl:inline">Human verification required</span>
    </div>
  );
}

function Welcome({ onClose, caseId }: { onClose: () => void; caseId: string | null }) {
  return (
    <div role="dialog" aria-modal="true" aria-labelledby="welcome-title" className="fixed inset-0 z-50 flex items-center justify-center bg-ink/50 p-4">
      <div className="card w-full max-w-3xl p-6">
        <div className="flex items-start justify-between gap-4">
          <div><div className="eyebrow">PS05-X · Investigative prototype</div><h2 id="welcome-title" className="mt-1 text-xl font-bold">Guided walkthrough</h2><p className="mt-1 text-sm muted">Fifteen steps through one synthetic investigation. Every step links to the real page; nothing here is a second menu.</p></div>
          <button className="btn-icon" onClick={onClose} aria-label="Close"><I.close /></button>
        </div>
        <ol className="mt-4 grid max-h-[55vh] gap-2 overflow-y-auto sm:grid-cols-2">
          {WALKTHROUGH.map((s, i) => (
            <li key={s.title} className="inset flex gap-3 p-2.5">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-bold text-accent-deep">{i + 1}</span>
              <div className="min-w-0"><Link href={s.href(caseId)} className="text-sm font-semibold hover:underline" onClick={onClose}>{s.title}</Link><div className="text-xs muted">{s.what}</div></div>
            </li>
          ))}
        </ol>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <Link href="/guide" className="text-sm text-accent-deep underline" onClick={onClose}>Read the full guide</Link>
          <div className="flex gap-2"><Link href="/factory" className="btn" onClick={onClose}><I.factory /> Generate Operation Desert Mirage</Link><button className="btn-secondary" onClick={onClose}>Explore on my own</button></div>
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
      {[["What you give it", g.inputs], ["What you get", g.outputs], ["Tips", g.tips]].map(([t, items]) => <div key={t as string} className="mt-4"><div className="label">{t as string}</div><ul className="list-disc space-y-1 pl-5 text-sm">{(items as string[]).map((x) => <li key={x}>{x}</li>)}</ul></div>)}
      <div className="mt-4"><div className="label">Evidence levels</div><ul className="space-y-1 text-xs">{Object.entries(EVIDENCE_LEVEL_HELP).map(([k, v]) => <li key={k}><span className={`badge lvl-${k}`}>{k.replace(/_/g, " ")}</span> <span className="muted">{v}</span></li>)}</ul></div>
      <Link href="/guide" className="mt-5 inline-flex items-center gap-1 text-sm text-accent-deep underline" onClick={onClose}><I.guide /> Open the full guide</Link>
    </aside>
  );
}

function Icon({ name, ...p }: { name: string } & React.SVGProps<SVGSVGElement>) {
  const C = (I as Record<string, (p: React.SVGProps<SVGSVGElement>) => React.ReactNode>)[name] || I.layers;
  return <>{C(p)}</>;
}

type ShellProps = { children: React.ReactNode; caseId?: string; caseTitle?: string; synthetic?: boolean; uploaded?: boolean; title?: string; subtitle?: string; pageKey?: string; step?: string; actions?: React.ReactNode; primary?: React.ReactNode; wide?: boolean };

/** Icon for a sidebar row, chosen from the destination's own words so related features share a visual family. */
const ICON_RULES: [RegExp, IconName][] = [
  [/upload|intake|vault|file|package|export|ocr/, "upload"],
  [/graph|network|chokepoint|resilience|cluster/, "graph"],
  [/timeline|replay|history|activity|operation-timeline/, "timeline"],
  [/report|finding|result|benchmark|model/, "report"],
  [/source|infra|dns|domain|hosting|threat|connector|host/, "sources"],
  [/factory|synthetic|challenge|lab|adversarial/, "factory"],
  [/transaction|money|fund|path|bounded|account|split|claim|recovery|intervention|price/, "money"],
  [/case|registry|workspace|cooperation|crosscase|campaign/, "cases"],
  [/role|entit|people|holder|attribution|review|dissent/, "user"],
  [/evidence|coverage|integrity|proof|completeness|preservation|request|ivoi|dependen/, "shield"],
  [/hypothes|counterproof|adversary|branch|lab|what-if|scenario/, "branch"],
  [/alert|queue|audit|guide|help|settings|privacy|rule/, "alert"],
  [/lifecycle|twin|journey|dna/, "layers"],
];
function iconForChild(child: NavChild, group?: NavGroup): IconName {
  const hay = `${child.key} ${child.path} ${child.label}`.toLowerCase();
  for (const [re, name] of ICON_RULES) if (re.test(hay)) return name;
  return (group?.icon as IconName) || "file";
}

export default function Shell({ children, caseId, caseTitle, synthetic, uploaded, title, subtitle, pageKey, actions, primary, wide }: ShellProps) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [help, setHelp] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [q, setQ] = useState("");
  const [ctx, setCtx] = useState<{ id: string; title: string } | null>(null);
  const [health, setHealth] = useState<"checking" | "ready" | "down">("checking");
  const [cases, setCases] = useState<{ id: string; title: string; is_synthetic: boolean }[]>([]);
  const searchRef = useRef<HTMLInputElement>(null);
  const route = useMemo(() => matchRoute(path), [path]);

  useEffect(() => {
    const u = getUser();
    if (!u) { router.replace("/"); return; }
    setUser(u);
    try { if (!window.localStorage.getItem(ONBOARD_KEY)) setWelcome(true); } catch { /* ignore */ }
    try { const s = window.localStorage.getItem(SIDEBAR_KEY); if (s) { const j = JSON.parse(s); setCollapsed(!!j.collapsed); setOpen(j.open || {}); } } catch { /* ignore */ }
    // Served from the shared read cache: the shell mounts on every page, so these must not be two fresh round trips per click.
    api("/health/ready").then(() => setHealth("ready")).catch(() => setHealth("down"));
    api("/cases").then((cs) => setCases(cs.slice(0, 40))).catch(() => undefined);
  }, [router]);
  useEffect(() => { setDrawer(false); }, [path]);
  useEffect(() => {
    if (caseId && caseTitle) setCaseContext({ id: caseId, title: caseTitle });
    const sync = () => setCtx(getCaseContext());
    sync();
    window.addEventListener("ps05x:case", sync);
    return () => window.removeEventListener("ps05x:case", sync);
  }, [caseId, caseTitle]);
  useEffect(() => {
    if (route?.group && !open[route.group.key]) setOpen((o) => ({ ...o, [route.group!.key]: true }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [route?.group?.key]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchRef.current?.focus(); }
      if (e.key === "?" && !(e.target as HTMLElement)?.closest("input,textarea")) { setHelp(true); }
      if (e.key === "Escape") { setHelp(false); setDrawer(false); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const persist = useCallback((c: boolean, o: Record<string, boolean>) => { try { window.localStorage.setItem(SIDEBAR_KEY, JSON.stringify({ collapsed: c, open: o })); } catch { /* ignore */ } }, []);
  const toggleGroup = (k: string) => setOpen((o) => { const n = { ...o, [k]: !o[k] }; persist(collapsed, n); return n; });
  const toggleCollapsed = () => setCollapsed((c) => { persist(!c, open); return !c; });
  const closeWelcome = () => { setWelcome(false); try { window.localStorage.setItem(ONBOARD_KEY, "1"); } catch { /* ignore */ } };
  const activeCase = caseId || ctx?.id || null;
  const activeTitle = caseTitle || ctx?.title || null;
  const demo = isDemo(user);
  const ql = q.trim().toLowerCase();
  const filtered: NavGroup[] = ql ? NAV.map((g) => ({ ...g, children: g.children.filter((c) => `${c.label} ${c.hint} ${g.label}`.toLowerCase().includes(ql)) })).filter((g) => g.children.length) : NAV;
  const crumbs = [{ href: "/overview", label: "Command Centre" }, ...(route?.group ? [{ href: hrefFor(route.group.children[0], activeCase), label: route.group.label }] : []), ...(activeCase && route?.child.caseScoped ? [{ href: `/cases/${activeCase}`, label: activeTitle || "Case" }] : []), ...(title ? [{ href: path, label: title }] : [])];

  /** Each row shows the full feature name with its plain-language description underneath, so nothing has to be guessed
   * from an abbreviation or discovered by hovering. Prefetch stays off (the sidebar lists every route, and prefetching
   * them all would queue a click's own request behind dozens of others); routes are warmed on hover and focus instead. */
  const NavLink = ({ child, group }: { child: NavChild; group?: NavGroup }) => {
    const href = hrefFor(child, activeCase);
    const active = route?.child.key === child.key;
    const needsCase = child.caseScoped && !activeCase;
    const icon = iconForChild(child, group);
    const warm = { onMouseEnter: () => router.prefetch(href), onFocus: () => router.prefetch(href) };
    if (collapsed) {
      return (
        <Link prefetch={false} href={href} {...warm} aria-current={active ? "page" : undefined} title={`${child.label}: ${child.hint}`}
          className={`flex justify-center rounded-xl px-2 py-2 transition ${active ? "bg-white/12 text-white ring-1 ring-white/10" : "text-rail-text/85 hover:bg-white/8 hover:text-white"}`}>
          <Icon name={icon} width={16} height={16} />
        </Link>
      );
    }
    return (
      <Link prefetch={false} href={href} {...warm} aria-current={active ? "page" : undefined}
        className={`navrow ${active ? "bg-white/12 text-white ring-1 ring-white/10" : "text-rail-text/90 hover:bg-white/8 hover:text-white"}`}>
        <span className={`navrow-icon ${active ? "text-saffron" : "text-rail-text/70"}`}><Icon name={icon} width={14} height={14} /></span>
        <span className="min-w-0 flex-1">
          <span className="navrow-name">{child.label}{needsCase && <span className="ml-1.5 rounded bg-white/12 px-1 py-px align-middle text-[9px] font-bold uppercase tracking-wide text-rail-text/80" title="Select a case first">case</span>}</span>
          <span className="navrow-desc">{child.hint}</span>
        </span>
      </Link>
    );
  };

  const sidebar = (
    <nav id="primary-nav" aria-label="Features" className="flex min-h-0 flex-1 flex-col">
      <div className={`px-3 pb-2 ${collapsed ? "hidden" : ""}`}>
        <div className="mb-2 rounded-lg border border-white/10 bg-white/5 p-2 text-xs">
          <div className="mb-1 flex items-center justify-between"><span className="font-semibold uppercase tracking-wide text-rail-text/70">Workspace</span>{(demo || synthetic) && <span className="rounded bg-terracotta px-1.5 py-0.5 text-[9px] font-bold uppercase text-white">Synthetic demo</span>}</div>
          <select aria-label="Selected case" className="w-full rounded bg-rail-2 px-2 py-1 text-xs text-white outline-none ring-1 ring-white/10" value={activeCase || ""}
            onChange={(e) => { const c = cases.find((x) => x.id === e.target.value); if (c) { setCaseContext({ id: c.id, title: c.title }); router.push(`/cases/${c.id}`); } else { setCaseContext(null); } }}>
            <option value="">No case selected</option>
            {cases.map((c) => <option key={c.id} value={c.id}>{c.is_synthetic ? "⚑ " : ""}{c.title.slice(0, 48)}</option>)}
          </select>
        </div>
        <label className="relative block"><I.search className="pointer-events-none absolute left-2 top-2 text-rail-text/60" width={14} height={14} /><input ref={searchRef} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search features (Ctrl+K)" aria-label="Search features" className="w-full rounded-lg bg-rail-2 py-1.5 pl-7 pr-2 text-xs text-white placeholder:text-rail-text/60 outline-none ring-1 ring-white/10 focus:ring-accent" /></label>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {filtered.map((g) => {
          const isOpen = !!open[g.key] || !!ql;
          const groupActive = route?.group?.key === g.key;
          return (
            <div key={g.key} className="mb-0.5">
              <button type="button" onClick={() => (collapsed ? router.push(hrefFor(g.children[0], activeCase)) : toggleGroup(g.key))} aria-expanded={isOpen} aria-controls={`grp-${g.key}`} title={collapsed ? g.label : undefined}
                className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition ${groupActive ? "text-white" : "text-rail-text hover:bg-white/8 hover:text-white"} ${collapsed ? "justify-center" : ""}`}>
                <span className={groupActive ? "text-saffron" : "text-rail-text/70"}><Icon name={g.icon as IconName} width={16} height={16} /></span>
                {!collapsed && <><span className="text-[10px] font-semibold tracking-[0.14em] text-rail-text/45">{g.num}</span><span className="flex-1 text-left text-[11px] font-bold uppercase leading-tight tracking-[0.08em]">{g.label}</span><I.chevron width={14} height={14} className={`transition-transform ${isOpen ? "rotate-90" : ""}`} /></>}
              </button>
              {(isOpen || collapsed) && (
                <div id={`grp-${g.key}`} className="mb-1 flex flex-col gap-0.5">
                  {g.children.map((c, i) => (
                    <Fragment key={c.key}>
                      {!collapsed && c.section && c.section !== g.children[i - 1]?.section && (
                        <div className="mt-2 px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-rail-text/40">{c.section}</div>
                      )}
                      <NavLink child={c} group={g} />
                    </Fragment>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {ql && filtered.length === 0 && <div className="px-3 py-4 text-xs text-rail-text/70">No feature matches “{q}”.</div>}
      </div>
      <div className={`mt-auto border-t border-white/10 px-2 py-2 text-xs text-rail-text/80 ${collapsed ? "flex flex-col items-center gap-1" : "space-y-0.5"}`}>
        {UTILITY.map((u) => <Link prefetch={false} key={u.key} href={u.path} title={u.hint} className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 hover:bg-white/8 hover:text-white ${route?.child.key === u.key ? "text-white" : ""}`}><I.help width={14} height={14} />{!collapsed && u.label}</Link>)}
        <button className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 hover:bg-white/8 hover:text-white ${collapsed ? "justify-center" : ""}`} onClick={() => setWelcome(true)}><I.play width={14} height={14} />{!collapsed && "Replay walkthrough"}</button>
        <Link prefetch={false} href="/settings" className={`flex items-center gap-2 rounded-lg px-2.5 py-1.5 hover:bg-white/8 hover:text-white ${collapsed ? "justify-center" : ""}`}><I.settings width={14} height={14} />{!collapsed && "Settings"}</Link>
        <button className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 hover:bg-white/8 hover:text-white ${collapsed ? "justify-center" : ""}`} onClick={async () => { await signOut(); router.push("/"); }}><I.logout width={14} height={14} />{!collapsed && "Sign out"}</button>
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-card focus:p-2">Skip to content</a>
      <aside className={`jaali hidden flex-col bg-rail text-rail-text md:sticky md:top-0 md:flex md:h-screen md:shrink-0 transition-[width] ${collapsed ? "md:w-[76px]" : "md:w-[272px]"}`}>
        <div className={`flex items-center gap-2 px-3 py-3 ${collapsed ? "justify-center" : "justify-between"}`}>
          <Link href="/overview" className="flex items-center gap-2.5" title="PS05-X">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-white shadow"><I.shield /></div>
            {!collapsed && <div><div className="text-base font-bold leading-tight tracking-tight text-white">PS05-X</div><div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-rail-text/70">Investigative prototype</div></div>}
          </Link>
          {!collapsed && <button className="rounded-lg p-1.5 text-rail-text hover:bg-white/10" onClick={toggleCollapsed} aria-label="Collapse navigation"><I.chevron className="rotate-180" width={16} height={16} /></button>}
        </div>
        {collapsed && <button className="mx-auto mb-1 rounded-lg p-1.5 text-rail-text hover:bg-white/10" onClick={toggleCollapsed} aria-label="Expand navigation"><I.chevron width={16} height={16} /></button>}
        {sidebar}
      </aside>
      {drawer && <div className="fixed inset-0 z-40 md:hidden"><div className="absolute inset-0 bg-ink/50" onClick={() => setDrawer(false)} aria-hidden /><aside className="jaali absolute inset-y-0 left-0 flex w-[88vw] max-w-sm flex-col bg-rail text-rail-text shadow-xl" aria-label="Navigation drawer"><div className="flex items-center justify-between px-3 py-3"><span className="font-bold text-white">PS05-X</span><button className="btn-icon !bg-transparent !text-white" onClick={() => setDrawer(false)} aria-label="Close navigation"><I.close /></button></div>{sidebar}</aside></div>}
      <div className="min-w-0 flex-1">
        <header className="sticky top-0 z-20 border-b border-line bg-card/85 backdrop-blur">
          <div className="flex h-16 items-center justify-between gap-3 px-4 md:px-6">
            <div className="flex min-w-0 items-center gap-2">
              <button className="btn-icon md:hidden" onClick={() => setDrawer(true)} aria-label="Open navigation"><I.menu /></button>
              <nav aria-label="Breadcrumb" className="hidden min-w-0 items-center gap-1 text-xs muted 2xl:flex">
                {crumbs.map((c, i) => <span key={c.href + i} className="flex min-w-0 items-center gap-1">{i > 0 && <span className="text-line-strong">/</span>}{i < crumbs.length - 1 ? <Link href={c.href} className="truncate hover:underline">{c.label}</Link> : <span className="truncate font-medium text-ink">{c.label}</span>}</span>)}
              </nav>
            </div>
            <div className="flex items-center gap-2">
              <span className={`hidden items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold sm:inline-flex ${health === "ready" ? "border-ok/40 text-ok" : health === "down" ? "border-danger/40 text-danger" : "border-line-strong text-ink-muted"}`} title="API connection health"><span aria-hidden>{health === "ready" ? "●" : health === "down" ? "○" : "◌"}</span>{health === "ready" ? "API ready" : health === "down" ? "API unreachable" : "Checking API"}</span>
              {(demo || synthetic || uploaded) && <span className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-white ${demo || synthetic ? "bg-terracotta" : "bg-ink"}`}>{demo ? "Synthetic demo" : synthetic ? "Synthetic" : "Uploaded evidence"}</span>}
              {user && <div className="hidden items-center gap-1.5 rounded-full border border-line-strong px-2 py-0.5 text-[11px] lg:flex" title={user.email}><I.user width={13} height={13} /><span className="max-w-[120px] truncate font-medium">{user.display_name}</span><span className="rounded bg-panel px-1 text-[10px] font-bold uppercase">{user.role.replace("_", " ")}</span></div>}
            </div>
          </div>
        </header>
        <main id="main" className={`mx-auto p-4 md:p-6 ${wide ? "" : "max-w-[1600px]"}`}>
          {title && (
            <section className="hero rise mb-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="hero-eyebrow">
                    {route?.group && <><span>{route.group.num}</span><span aria-hidden>·</span><span>{route.group.label}</span><span aria-hidden>·</span></>}
                    <span className="text-accent-deep">{route?.child.label || title}</span>
                    {caseTitle && <><span aria-hidden>·</span><span className="mono normal-case tracking-normal">{caseTitle.slice(0, 40)}</span></>}
                  </div>
                  <h1 className="hero-title mt-2.5 text-[30px] md:text-[42px]">{title.replace(/^\[SYNTHETIC\]\s*/i, "")}</h1>
                  {subtitle && <p className="mt-3 max-w-3xl text-[15px] leading-relaxed muted">{subtitle}</p>}
                  <div className="mt-3"><Banner synthetic={synthetic} uploaded={uploaded} demo={demo} /></div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {actions}
                  {pageKey && GUIDE[pageKey] && <button className="btn-secondary" onClick={() => setHelp(true)} aria-haspopup="dialog"><I.help /> Help</button>}
                  {primary}
                </div>
              </div>
            </section>
          )}
          <div className="rise rise-1">{children}</div>
        </main>
      </div>
      {help && pageKey && GUIDE[pageKey] && <><div className="fixed inset-0 z-30 bg-ink/25" onClick={() => setHelp(false)} aria-hidden /><HelpDrawer pageKey={pageKey} onClose={() => setHelp(false)} /></>}
      {welcome && <Welcome onClose={closeWelcome} caseId={activeCase} />}
    </div>
  );
}

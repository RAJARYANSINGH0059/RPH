"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { clearSession, getUser, type User } from "@/lib/api";

export function Banner({ synthetic }: { synthetic?: boolean }) {
  return (
    <div className="flex flex-wrap gap-2 text-[11px] font-semibold uppercase tracking-wide">
      {synthetic && <span className="rounded bg-synthetic px-2 py-0.5 text-white">Synthetic data</span>}
      <span className="rounded border border-synthetic px-2 py-0.5 text-synthetic">No live police/bank connection</span>
      <span className="rounded border border-line px-2 py-0.5 text-ink-muted">Investigative aid · human verification required</span>
    </div>
  );
}

export default function Shell({ children, caseId, synthetic, title }: { children: React.ReactNode; caseId?: string; synthetic?: boolean; title?: string }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    const u = getUser();
    if (!u) router.replace("/");
    setUser(u);
  }, [router]);
  const nav = caseId
    ? [
        { href: "/cases", label: "Cases" },
        { href: `/cases/${caseId}/upload`, label: "Upload Evidence" },
        { href: `/cases/${caseId}/graph`, label: "Investigation Graph" },
        { href: `/cases/${caseId}/timeline`, label: "Timeline" },
        { href: `/cases/${caseId}/reports`, label: "Reports" },
        { href: "/sources", label: "Data Sources" },
      ]
    : [
        { href: "/cases", label: "Cases" },
        { href: "/factory", label: "Synthetic Case Factory" },
        { href: "/sources", label: "Data Sources" },
      ];
  return (
    <div className="min-h-screen md:flex">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">Skip to content</a>
      <aside className="border-b border-line bg-white md:w-60 md:border-b-0 md:border-r">
        <div className="px-4 py-4">
          <Link href="/cases" className="text-lg font-bold tracking-tight">PS05-X</Link>
          <div className="text-xs text-ink-muted">Evidence-centred investigation workbench</div>
        </div>
        <nav aria-label="Primary" className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-0">
          {nav.map((n) => {
            const active = path === n.href || (n.href !== "/cases" && path.startsWith(n.href));
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={`whitespace-nowrap rounded-md px-3 py-2 text-sm ${active ? "bg-accent-light font-semibold text-accent-dark" : "text-ink hover:bg-[#f1f4f7]"}`}>
                {n.label}
              </Link>
            );
          })}
        </nav>
        {caseId && (
          <div className="px-4 pt-2 text-xs text-ink-muted md:pt-4">
            <div className="font-medium">Case view</div>
            <Link className="underline" href={`/cases/${caseId}`}>Overview</Link> · <Link className="underline" href={`/cases/${caseId}/transactions`}>Transactions</Link>
          </div>
        )}
        <div className="px-4 py-4 text-xs text-ink-muted">
          {user && <div className="mb-1">{user.display_name} <span className="badge bg-[#eef1f4] text-ink-muted">{user.role}</span></div>}
          <button className="underline" onClick={() => { clearSession(); router.push("/"); }}>Sign out</button>
        </div>
      </aside>
      <main id="main" className="flex-1 p-4 md:p-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          {title && <h1 className="text-xl font-semibold">{title}</h1>}
          <Banner synthetic={synthetic} />
        </div>
        {children}
      </main>
    </div>
  );
}

export function State({ loading, error, empty, children }: { loading?: boolean; error?: string | null; empty?: string | null; children?: React.ReactNode }) {
  if (loading) return <div className="card text-sm text-ink-muted" role="status">Loading…</div>;
  if (error) return <div className="card border-[#f1c5c5] bg-[#fff5f5] text-sm text-[#8a1c1c]" role="alert">{error}</div>;
  if (empty) return <div className="card text-sm text-ink-muted">{empty}</div>;
  return <>{children}</>;
}

export function LevelBadge({ level }: { level: string }) {
  const map: Record<string, string> = { directly_observed: "bg-[#e7eff9] text-[#174a84]", corroborated: "bg-[#e3f3f0] text-[#136f63]", derived: "bg-[#eef1f4] text-[#3d4852]", candidate: "bg-[#fdf3e0] text-[#8a5a0f]", contradicted: "bg-[#fde8e8] text-[#8a1c1c]", stale: "bg-[#f2ebe8] text-[#6d4c41]", insufficient: "bg-[#eef1f4] text-ink-muted" };
  return <span className={`badge ${map[level] || "bg-[#eef1f4]"}`}>{level.replace("_", " ")}</span>;
}

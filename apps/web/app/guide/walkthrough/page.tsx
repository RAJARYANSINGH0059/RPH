"use client";

import Link from "next/link";
import Shell from "@/components/Shell";
import { getCaseContext } from "@/lib/api";
import { WALKTHROUGH } from "@/lib/guide";

export default function Page() {
  const c = typeof window !== "undefined" ? getCaseContext()?.id || null : null;
  return (
    <Shell title="Guided Walkthrough" subtitle="Fifteen steps through one synthetic investigation. Each step opens the real page; this list is a guide, not a second navigation." pageKey="guide">
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{WALKTHROUGH.map((s: any, i: any) => <li key={s.title} className="card"><div className="flex items-start gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-rail text-sm font-bold text-white">{i + 1}</span><div><Link href={s.href(c)} className="font-semibold hover:underline">{s.title}</Link><p className="mt-1 text-sm muted">{s.what}</p></div></div></li>)}</ol>
    </Shell>
  );
}

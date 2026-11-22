"use client";

import Link from "next/link";
import Shell, { LevelBadge } from "@/components/Shell";
import { I } from "@/components/icons";
import { EVIDENCE_LEVEL_HELP, GUIDE, WALKTHROUGH } from "@/lib/guide";

const ORDER = ["cases", "factory", "overview", "upload", "transactions", "graph", "timeline", "reports", "sources"];

export default function GuidePage() {
  return (
    <Shell title="How to use PS05-X" subtitle="Everything an investigator needs to know, page by page. Each page also has a Help button with the same content.">
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <nav aria-label="Guide sections" className="card h-max lg:sticky lg:top-6">
          <div className="label">Contents</div>
          <ol className="space-y-1 text-sm">{ORDER.map((k: any) => <li key={k}><a className="text-accent hover:underline" href={`#${k}`}>{GUIDE[k].title}</a></li>)}<li><a className="text-accent hover:underline" href="#levels">Evidence levels</a></li><li><a className="text-accent hover:underline" href="#rules">What the tool will never do</a></li></ol>
        </nav>
        <div className="space-y-4">
          <div className="callout"><I.play className="shrink-0 text-accent" /><div><div className="font-semibold">The guided walkthrough (15 steps)</div><ol className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">{WALKTHROUGH.map((s, i) => <li key={s.title}><span className="font-semibold">{i + 1}. {s.title}</span></li>)}</ol><div className="mt-2 text-xs text-ink-muted">Replay it any time from the sidebar footer; every step opens the real page.</div></div></div>
          {ORDER.map((k: any) => {
            const g = GUIDE[k];
            return (
              <section key={k} id={k} className="card scroll-mt-6">
                <h2 className="section-title">{g.title}</h2>
                <p className="mt-1 text-sm">{g.purpose}</p>
                <div className="mt-3 grid gap-3 md:grid-cols-3">
                  <div className="rounded-lg bg-canvas p-3"><div className="label">What you give it</div><ul className="list-disc space-y-1 pl-4 text-sm">{g.inputs.map((x: any) => <li key={x}>{x}</li>)}</ul></div>
                  <div className="rounded-lg bg-canvas p-3"><div className="label">What you get</div><ul className="list-disc space-y-1 pl-4 text-sm">{g.outputs.map((x: any) => <li key={x}>{x}</li>)}</ul></div>
                  <div className="rounded-lg bg-accent-light/60 p-3"><div className="label">Tips</div><ul className="list-disc space-y-1 pl-4 text-sm">{g.tips.map((x: any) => <li key={x}>{x}</li>)}</ul></div>
                </div>
              </section>
            );
          })}
          <section id="levels" className="card scroll-mt-6">
            <h2 className="section-title">Evidence levels</h2>
            <p className="mt-1 text-sm text-ink-muted">Every relationship in the graph and report carries one of these. Scores shown next to them are heuristic ranking scores, not probabilities.</p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(EVIDENCE_LEVEL_HELP).map(([k, v]: [any, any]) => <li key={k} className="flex items-start gap-2 rounded-lg border border-line p-2 text-sm"><LevelBadge level={k} /><span>{v}</span></li>)}</ul>
          </section>
          <section id="rules" className="card scroll-mt-6">
            <h2 className="section-title">What the tool will never do</h2>
            <ul className="mt-2 grid gap-2 sm:grid-cols-2 text-sm">
              {["Call two domains commonly owned because they share an IP, CDN, ASN or registrar.", "Merge two people or accounts because their names look similar.", "Resolve an ambiguous date (03/04/26) silently.", "Drop a duplicate row; both are kept and flagged.", "Invent a missing value.", "Present current DNS as historical DNS.", "Label anyone a criminal; it says “possible pattern, requires review”.", "Freeze, lien or file anything; it prepares evidence for authorised humans."].map((x: any) => <li key={x} className="flex gap-2"><I.shield className="mt-0.5 shrink-0 text-accent" width={16} height={16} />{x}</li>)}
            </ul>
          </section>
          <div className="flex flex-wrap gap-2"><Link href="/factory" className="btn"><I.factory /> Generate a demo case</Link><Link href="/cases" className="btn-secondary">Go to cases</Link></div>
        </div>
      </div>
    </Shell>
  );
}

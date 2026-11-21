"use client";

import { useEffect, useState } from "react";
import { CorrelationView } from "@/components/CrossCase";
import Shell, { State } from "@/components/Shell";
import { api } from "@/lib/api";

export default function CrossCasePage() {
  const [cases, setCases] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  useEffect(() => { api("/cases").then(setCases).catch((e) => setError(e.message)); }, []);
  const toggle = (id: string) => setSel(sel.includes(id) ? sel.filter((x: any) => x !== id) : sel.length < 12 ? [...sel, id] : sel);
  return (
    <Shell title="Cross-case correlation" subtitle="Select two or more cases you are authorised to access. Only exact, source-backed bridges are asserted; shared hosting stays a candidate." pageKey="crosscase">
      <State loading={cases === null && !error} error={error} empty={cases && cases.length < 2 ? "You need at least two accessible cases. Generate another synthetic case or ask a case owner to add you." : null}>
        <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
          <div className="card p-0 xl:sticky xl:top-20 xl:self-start">
            <div className="px-4 py-3"><h2 className="section-title">Your cases</h2><p className="text-xs muted">{sel.length} selected (2–12)</p></div>
            <ul className="max-h-[60vh] divide-y divide-line overflow-y-auto">
              {cases?.map((c: any) => (
                <li key={c.id}><label className="flex cursor-pointer items-start gap-2 px-4 py-2 hover:bg-panel/60"><input type="checkbox" className="mt-1" checked={sel.includes(c.id)} onChange={() => toggle(c.id)} /><span className="min-w-0"><span className="block truncate text-sm font-medium">{c.title}</span><span className="text-[11px] muted">{c.is_synthetic ? "synthetic" : "uploaded"} · {c.internal_ref || "no ref"}</span></span></label></li>
              ))}
            </ul>
          </div>
          <div>
            {sel.length < 2 ? <div className="card border-dashed text-sm muted">Pick at least two cases on the left. Results list every bridge with its class, the source files and locators in each case, limitations and counter-evidence. Nothing is merged.</div> : <CorrelationView caseIds={sel} />}
          </div>
        </div>
      </State>
    </Shell>
  );
}

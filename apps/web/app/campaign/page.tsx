"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { MotionScene } from "@/components/motion";
import { Chip, Limitations, Section, Table, Toast } from "@/components/ui";
import { api } from "@/lib/api";

export default function Page() {
  const [cases, setCases] = useState<any[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [res, setRes] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("/cases").then(setCases).catch((e) => setMsg(e.message)); }, []);
  async function compare() { setBusy(true); setMsg(null); try { setRes(await api("/campaign/compare", { method: "POST", body: JSON.stringify({ case_ids: sel }) })); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); } }
  return (
    <Shell title="Fraud Campaign Evolution" subtitle="Compare structural fingerprints across cases you can access, even when domains, VPAs and accounts changed. Generic templates, shared CDNs and popular payment handles are excluded. Pattern similarity never establishes common ownership or a criminal organisation." pageKey="campaign">
      <div className="space-y-3">
        <Section title="Pick two or more cases" hint="Identifier rotation is flagged only when the structure is at least medium-similar and no identifier is shared.">
          <div className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3 text-sm">{cases.map((c: any) => <label key={c.id} className="inset flex items-center gap-2 p-2"><input type="checkbox" checked={sel.includes(c.id)} onChange={(e) => setSel((s) => e.target.checked ? [...s, c.id] : s.filter((x: any) => x !== c.id))} /><span className="truncate">{c.is_synthetic ? "⚑ " : ""}{c.title}</span></label>)}</div>
          <button className="btn mt-3" disabled={sel.length < 2 || busy} onClick={compare}>{busy ? "Comparing…" : `Compare ${sel.length} case(s)`}</button>
          <Toast msg={msg} onClose={() => setMsg(null)} />
        </Section>
        {res && (
          <>
            {res.pairs.map((p: any) => (
              <Section key={p.case_a + p.case_b} title={<span className="flex items-center gap-2"><Chip v={p.relationship_status.includes("HIGH") ? "contested" : p.relationship_status.includes("MEDIUM") ? "candidate" : "unresolved"} title={p.relationship_status} /> {p.titles[0]} ↔ {p.titles[1]}</span>} hint={`Aggregate ${p.aggregate_score_not_probability ?? "—"} (${p.aggregate_label}; not a probability) · identifier rotation candidate: ${p.identifier_rotation.rotation_candidate ? "yes" : "no"}`}>
                <Table dense cols={["Dimension", "Label", "Score", "Basis", "Notes"]} rows={Object.entries(p.dimension_results).map(([k, v]: [string, any]) => [k.replace(/_/g, " "), <Chip key="l" v={v.label} />, v.score ?? "—", <span key="b" className="text-xs">{v.basis}</span>, <span key="n" className="text-xs muted">{v.caution || (v.generic_excluded?.length ? `generic excluded: ${v.generic_excluded.join(", ")}` : "")}{v.shared?.length ? ` shared: ${v.shared.join(", ")}` : ""}</span>])} />
                <div className="mt-2 grid gap-2 md:grid-cols-2 text-xs"><div><div className="label">Changed identifiers</div>{Object.entries(p.identifier_rotation.changed_identifiers).map(([k, v]: [string, any]) => <div key={k}><span className="font-medium">{k}</span>: {v.a.length} vs {v.b.length}</div>)}<div className="mt-1">Shared: {Object.entries(p.identifier_rotation.shared_identifiers).map(([k, v]: [string, any]) => `${k} ${v.join(", ")}`).join("; ") || "none"}</div><div className="muted">{p.identifier_rotation.time_order_of_observations || "no time order"}</div></div><div><div className="label">Alternative explanations</div><ul className="list-disc pl-4">{p.alternative_explanations.map((a: string) => <li key={a}>{a}</li>)}</ul></div></div>
                <Limitations items={p.limitations} />
              </Section>
            ))}
            <MotionScene scene="campaign_evolution" height={110} />
          </>
        )}
      </div>
    </Shell>
  );
}

"use client";

import { useState } from "react";
import CasePage from "@/components/CasePage";
import { MotionScene } from "@/components/motion";
import { Chip, KV, Limitations, Section, State, Table, Toast, useApi, When } from "@/components/ui";
import { api } from "@/lib/api";

export default function LabPage() {
  return <CasePage title="Counterfactual Investigation Lab" subtitle="Deliberately perturb an analytical copy of the case (shared hosting, stale DNS, OCR substitution, a missing statement…) and see which findings survive. Source files and database records are never modified." pageKey="lab" wide>{(c, id) => <Body id={id} />}</CasePage>;
}

function Body({ id }: { id: string }) {
  const profiles = useApi<any>(`/cases/${id}/lab/profiles`);
  const runs = useApi<any>(`/cases/${id}/lab/runs`);
  const [profile, setProfile] = useState("shared_hosting");
  const [seed, setSeed] = useState(42001);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function run() { setBusy(true); setMsg(null); try { setRes(await api(`/cases/${id}/lab/run`, { method: "POST", body: JSON.stringify({ profile, seed }) })); runs.reload(); } catch (e: any) { setMsg(e.message); } finally { setBusy(false); } }
  return (
    <State loading={profiles.loading} error={profiles.error} onRetry={profiles.reload}>
      {profiles.data && (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_1.3fr]">
            <Section title="Choose a perturbation" hint="Each profile encodes a plausible alternative data interpretation or evidence defect.">
              <ul className="max-h-[50vh] space-y-1 overflow-auto text-sm">{Object.entries(profiles.data.profiles).map(([k, d]: [any, any]) => <li key={k}><button className={`w-full rounded-lg border p-2 text-left transition hover:bg-panel ${profile === k ? "border-accent bg-accent-soft/40" : "border-line"}`} aria-pressed={profile === k} onClick={() => setProfile(k)}><div className="mono text-xs font-semibold">{k}</div><div className="text-xs muted">{String(d)}</div></button></li>)}</ul>
              <div className="mt-3 flex items-center gap-2 text-sm"><label>Seed <input type="number" className="input !w-28" value={seed} onChange={(e) => setSeed(Number(e.target.value))} /></label><button className="btn ml-auto" disabled={busy} onClick={run}>{busy ? "Running on analytical copy…" : "Run stress test"}</button></div>
              <Toast msg={msg} onClose={() => setMsg(null)} />
            </Section>
            <div className="space-y-3">
              {res ? (
                <Section title={<span className="flex items-center gap-2">Result <Chip v={res.robustness} /></span>} hint={res.robustness_explanation}>
                  <KV rows={[["Profile", <span key="p" className="mono">{res.scenario.profile}</span>], ["Seed", String(res.scenario.seed)], ["Source evidence immutable", res.scenario.source_evidence_immutable ? "yes (in-memory copy)" : "no"], ["Edges before → after", `${res.perturbation_applied.edges_before} → ${res.perturbation_applied.edges_after}`], ["Affected evidence / entities", res.perturbation_applied.affected_evidence_or_entities.slice(0, 6).join(", ") || "—"], ["Common operator asserted", res.safeguard_check.common_operator_asserted ? "YES — safeguard failure" : "no"], ["Unresolved/uncertain paths", `${res.uncertainty_change.unresolved_or_uncertain_paths_before} → ${res.uncertainty_change.after}`]]} />
                  <div className="mt-3 grid gap-3 md:grid-cols-2 text-xs">
                    <div><div className="label">Stable ({res.findings_stable.length})</div><ul className="list-disc pl-4">{res.findings_stable.slice(0, 8).map((p: string[], i: number) => <li key={i}>{p.map((a: any) => a.slice(-5)).join(" → ")}</li>)}</ul></div>
                    <div><div className="label">Weakened / changed status ({res.findings_weakened.length})</div><ul className="list-disc pl-4">{res.findings_weakened.map((w: any, i: number) => <li key={i}>{w.path.map((a: string) => a.slice(-5)).join(" → ")}: {w.from} → {w.to}</li>)}</ul></div>
                    <div><div className="label">Disappeared ({res.findings_disappeared.length})</div><ul className="list-disc pl-4">{res.findings_disappeared.slice(0, 8).map((p: string[], i: number) => <li key={i} className="danger">{p.map((a: any) => a.slice(-5)).join(" → ")}</li>)}</ul></div>
                    <div><div className="label">Appeared ({res.findings_appeared.length})</div><ul className="list-disc pl-4">{res.findings_appeared.slice(0, 8).map((p: string[], i: number) => <li key={i} className="warn">{p.map((a: any) => a.slice(-5)).join(" → ")}</li>)}</ul></div>
                  </div>
                  {res.triage_changes.length > 0 && <div className="mt-2 text-xs"><div className="label">Triage label changes</div>{res.triage_changes.map((t: any) => <div key={t.account}>{t.account}: {t.from || "—"} → {t.to || "—"}</div>)}</div>}
                  {res.counter_evidence_discovered.length > 0 && <div className="callout mt-3 text-xs">{res.counter_evidence_discovered.join(" ")}</div>}
                  <Limitations items={res.limitations} />
                </Section>
              ) : <div className="card text-sm muted">Run a profile to compare original and revised findings.</div>}
              <MotionScene scene="network_correlation" height={110} />
            </div>
          </div>
          <Section title="Previous runs (reproducible by profile + seed)"><Table dense cols={["Profile", "Seed", "Robustness", "When"]} rows={(runs.data || []).map((r: any) => [<span key="p" className="mono">{r.profile}</span>, r.seed, <Chip key="r" v={r.robustness} />, <When key="w" v={r.created_at} />])} empty="No runs yet." /></Section>
        </div>
      )}
    </State>
  );
}

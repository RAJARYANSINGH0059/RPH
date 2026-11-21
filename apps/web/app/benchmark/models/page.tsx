"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { Limitations, Section, State, Table, useApi } from "@/components/ui";
import { Chip, Toast, When } from "@/components/ui";
import { api, getUser, isReviewer } from "@/lib/api";

export default function Page() {
  const mc = useApi<any>("/benchmark/model-card");
  const rules = useApi<any>("/rules");
  const [msg, setMsg] = useState<string | null>(null);
  async function compile(typ: string) { setMsg(null); try { await api("/rules/compile", { method: "POST", body: JSON.stringify({ name: typ.replace(/_/g, "-"), typology: typ, seeds: [9001, 9002, 9003] }) }); rules.reload(); } catch (e: any) { setMsg(e.message); } }
  async function decide(id: string, decision: string) { const reason = window.prompt("Reason"); if (!reason) return; try { await api(`/rules/${id}/decision`, { method: "POST", body: JSON.stringify({ decision, reason }) }); rules.reload(); } catch (e: any) { setMsg(e.message); } }
  return (
    <Shell title="Model and Rules Performance" subtitle="The triage model is a ranking cue trained on synthetic cases, compared with transparent rules. The prevention-rule compiler turns an approved typology into a versioned candidate rule evaluated on held-out synthetic seeds; nothing is ever deployed." pageKey="benchmark">
      <div className="space-y-3">
        <State loading={mc.loading} error={mc.error} onRetry={mc.reload}>{mc.data && <Section title="Triage model card (synthetic-only)"><pre className="mono max-h-72 overflow-auto rounded-lg bg-panel p-3 text-[11px]">{JSON.stringify(mc.data, null, 1).slice(0, 5000)}</pre></Section>}</State>
        <State loading={rules.loading} error={rules.error} onRetry={rules.reload}>
          {rules.data && <Section title="Prevention-rule compiler" hint="Compile a known typology, evaluate on held-out seeds, then a supervisor approves or rejects the version.">
            <div className="flex flex-wrap gap-2">{Object.keys(rules.data.typologies).map((t: any) => <button key={t} className="btn-secondary !py-1" onClick={() => compile(t)}>Compile {t.replace(/_/g, " ")}</button>)}</div>
            <Toast msg={msg} onClose={() => setMsg(null)} />
            <Table dense cols={["Rule", "Version", "Precision", "Recall", "FPR", "Alerts / case", "Cases", "Approval", "Created", ""]} rows={rules.data.rules.map((r: any) => [r.name, r.version, r.evaluation.precision ?? "—", r.evaluation.recall ?? "—", r.evaluation.false_positive_rate ?? "—", r.evaluation.alert_volume_per_case ?? "—", r.evaluation.cases, <Chip key="a" v={r.approval_status === "approved" ? "verified" : r.approval_status === "rejected" ? "contradicted" : "candidate"} title={r.approval_status} />, <When key="c" v={r.created_at} />, isReviewer(getUser()) && r.approval_status === "draft" ? <span key="d" className="flex gap-1"><button className="btn-secondary !py-0.5" onClick={() => decide(r.id, "approved")}>Approve</button><button className="btn-secondary !py-0.5" onClick={() => decide(r.id, "rejected")}>Reject</button></span> : <span key="d" className="text-xs muted">{r.deployment.split(":")[0]}</span>])} empty="No candidate rules compiled yet." />
          </Section>}
        </State>
        <Limitations items={["Synthetic-only performance; not real police accuracy.", "A rule hit or model score is a triage cue, never a determination about a person."]} />
      </div>
    </Shell>
  );
}

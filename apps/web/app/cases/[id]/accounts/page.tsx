"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, Money } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Account and Beneficiary Analysis' subtitle='Per-account features computed from money edges only, with the transparent rules triage and the optional ML cue. A triage label is a reason to look, never a conclusion about a person.' pageKey='accounts'>
      {(id) => <ApiTable title='Account and Beneficiary Analysis' hint='' path={`/cases/${id}/paths`} pick={(d) => Object.entries(d.features).map(([account, f]: [any, any]) => ({ account, f }))} empty='No accounts with money edges.' raw={false} limitations={() => ["Rules and ML triage are cues for review; they are not probabilities of guilt and never label a person.", "Features come from supplied statements only."]} cols={[
        { h: "Account", cell: (r) => <span className="mono">{r.account}</span> },
        { h: "In / out (count)", cell: (r) => `${r.f.tx_in} / ${r.f.tx_out}` },
        { h: "Total in", cell: (r) => <Money v={r.f.total_in_minor} /> },
        { h: "Total out", cell: (r) => <Money v={r.f.total_out_minor} /> },
        { h: "Fan-in / fan-out", cell: (r) => `${r.f.fan_in} / ${r.f.fan_out}` },
        { h: "Median holding (h)", cell: (r) => r.f.median_holding_hours < 0 ? "—" : r.f.median_holding_hours.toFixed(1) },
        { h: "Own statement", cell: (r) => r.f.has_own_statement ? "yes" : "no" },
        { h: "Rules triage", cell: (r) => <span className="text-xs"><Chip v={r.f.triage.label.startsWith("possible") ? "candidate" : r.f.triage.label === "weak_signal" ? "derived" : "insufficient"} title={r.f.triage.label} /> {r.f.triage.reasons.join(", ")}</span> },
        { h: "ML cue", cell: (r) => <span className="text-xs">{r.f.ml_triage?.label ?? "—"}{r.f.ml_triage?.score !== undefined ? ` (${r.f.ml_triage.score})` : ""}</span> },
      ]} />}
    </ListPage>
  );
}

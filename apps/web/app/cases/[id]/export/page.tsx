"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { Section, State, useApi } from "@/components/ui";
import { I } from "@/components/icons";
import { saveAs } from "@/lib/api";

export default function Page() {
  return <ListPage title="Export Centre" subtitle="Every downloadable artefact for this case in one place. Exports carry the data status (SYNTHETIC / UPLOADED) and never include sealed ground truth." pageKey="export">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const paths = useApi<any>(`/cases/${id}/paths`);
  const reqs = useApi<any>(`/cases/${id}/requests`);
  const rows: [string, string, () => void][] = [
    ["Report JSON", "full source-cited report", () => saveAs(`/cases/${id}/report.json`, `report_${id.slice(0, 8)}.json`)], ["Report PDF", "deterministic PDF", () => saveAs(`/cases/${id}/report.pdf`, `report_${id.slice(0, 8)}.pdf`)],
    ["Transactions CSV", "all rows", () => saveAs(`/cases/${id}/report/transactions.csv`, `transactions_${id.slice(0, 8)}.csv`)], ["Payment bridge PDF", "instruction ↔ transaction", () => saveAs(`/cases/${id}/payment-instructions/report.pdf`, `bridge_${id.slice(0, 8)}.pdf`)],
    ["Restitution pack PDF", "claims reconciliation", () => saveAs(`/cases/${id}/claims/pack.pdf`, `restitution_${id.slice(0, 8)}.pdf`)], ["Restitution pack JSON", "machine-readable", () => saveAs(`/cases/${id}/claims/pack.json`, `restitution_${id.slice(0, 8)}.json`)],
    ...((paths.data?.paths || []).map((p: any, i: number) => [`Proof manifest path #${i}`, `${p.accounts.length} accounts · ${p.status}`, () => saveAs(`/cases/${id}/paths/${i}/proof.json`, `proof_${i}.json`)] as [string, string, () => void])),
    ...((reqs.data?.requests || []).map((r: any) => [`Request draft: ${r.title}`, r.status, () => saveAs(`/cases/${id}/requests/${r.id}/draft.pdf`, `request_${r.id.slice(0, 8)}.pdf`)] as [string, string, () => void])),
  ];
  return (
    <State loading={paths.loading} error={paths.error} onRetry={paths.reload}>
      {paths.data && <div className="space-y-3"><Section title={`Artefacts (${rows.length})`}><ul className="grid gap-2 md:grid-cols-2">{rows.map(([t, d, fn], i) => <li key={i} className="inset flex items-center justify-between gap-3 p-2 text-sm"><div><div className="font-medium">{t}</div><div className="text-xs muted">{d}</div></div><button className="btn-secondary !py-1" onClick={fn}><I.download /> Download</button></li>)}</ul></Section>
        <div className="card flex items-center justify-between text-sm"><span>Cooperation pack ZIP (manifest + hashes) is exported from the handoff page after supervisor endorsement.</span><Link href={`/cases/${id}/cooperation`} className="btn-secondary">Open handoff</Link></div></div>}
    </State>
  );
}

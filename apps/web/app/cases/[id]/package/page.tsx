"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { Section, State, useApi } from "@/components/ui";
import { I } from "@/components/icons";
import { saveAs } from "@/lib/api";

export default function Page() {
  return <ListPage title="Evidence Package Builder" subtitle="Assemble the artefacts an examiner or another agency needs: proof certificates per path, restitution readiness pack, payment-bridge report, cooperation pack (supervisor gate) and the full JSON report with hashes. Every export carries the synthetic watermark when applicable." pageKey="package">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/paths`);
  const items = [
    ["Full report (JSON)", "Observed facts, derived analysis, hypotheses, counter-evidence, limitations", () => saveAs(`/cases/${id}/report.json`, `report_${id.slice(0, 8)}.json`)],
    ["Report (PDF)", "Deterministic, source-cited PDF", () => saveAs(`/cases/${id}/report.pdf`, `report_${id.slice(0, 8)}.pdf`)],
    ["Transactions (CSV)", "Every parsed row with raw text and warnings", () => saveAs(`/cases/${id}/report/transactions.csv`, `transactions_${id.slice(0, 8)}.csv`)],
    ["Payment bridge (PDF)", "Instructions and their best transaction match", () => saveAs(`/cases/${id}/payment-instructions/report.pdf`, `payment_bridge_${id.slice(0, 8)}.pdf`)],
    ["Restitution readiness pack (PDF / JSON)", "Claimed, traced, held, restored, unresolved", () => saveAs(`/cases/${id}/claims/pack.pdf`, `restitution_${id.slice(0, 8)}.pdf`)],
  ];
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <Section title="Downloads"><ul className="grid gap-2 md:grid-cols-2">{items.map(([t, d, fn]) => <li key={t as string} className="inset flex items-center justify-between gap-3 p-3 text-sm"><div><div className="font-medium">{t as string}</div><div className="text-xs muted">{d as string}</div></div><button className="btn-secondary" onClick={fn as () => void}><I.download /> Download</button></li>)}</ul></Section>
          <Section title={`Proof certificates (${data.paths.length} paths)`} hint="Each manifest is hash-protected and verifiable offline with scripts/verify_proof.py."><ul className="grid gap-2 md:grid-cols-2">{data.paths.map((p: any, i: number) => <li key={i} className="inset flex items-center justify-between gap-2 p-2 text-xs"><span className="mono">#{i} {p.accounts.map((a: string) => a.slice(-4)).join(" → ")} · {p.status}</span><span className="flex gap-1"><button className="btn-secondary !py-1" onClick={() => saveAs(`/cases/${id}/paths/${i}/proof.json`, `proof_${i}.json`)}>JSON</button><button className="btn-secondary !py-1" onClick={() => saveAs(`/cases/${id}/paths/${i}/proof.pdf`, `proof_${i}.pdf`)}>PDF</button></span></li>)}</ul></Section>
          <div className="card flex items-center justify-between text-sm"><span>Inter-state cooperation pack (requires supervisor endorsement before export).</span><Link href={`/cases/${id}/cooperation`} className="btn-secondary">Open handoff</Link></div>
        </div>
      )}
    </State>
  );
}

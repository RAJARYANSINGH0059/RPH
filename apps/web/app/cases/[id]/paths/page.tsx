"use client";

import { useState } from "react";
import ListPage from "@/components/ListPage";
import { Chip, Locator, Money, Section, State, Table, useApi, When } from "@/components/ui";
import { I } from "@/components/icons";
import { saveAs } from "@/lib/api";

export default function Page() {
  return <ListPage title="Multi-Hop Fund Path" subtitle="Hop-by-hop detail for one reconstructed path with the source row behind every hop, and the proof certificate (JSON manifest + PDF) an examiner can verify offline with scripts/verify_proof.py." pageKey="paths">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/paths`);
  const [idx, setIdx] = useState(0);
  const p = data?.paths?.[idx];
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <div className="card flex flex-wrap items-center gap-3 text-sm"><label>Path <select className="input !w-auto" value={idx} onChange={(e) => setIdx(Number(e.target.value))}>{data.paths.map((x: any, i: number) => <option key={i} value={i}>#{i} {x.accounts.map((a: string) => a.slice(-4)).join(" → ")} · {x.status}</option>)}</select></label>
            {p && <div className="ml-auto flex gap-2"><button className="btn-secondary" onClick={() => saveAs(`/cases/${id}/paths/${idx}/proof.json`, `proof_path${idx}.json`)}><I.download /> Proof manifest (JSON)</button><button className="btn-secondary" onClick={() => saveAs(`/cases/${id}/paths/${idx}/proof.pdf`, `proof_path${idx}.pdf`)}><I.download /> Certificate (PDF)</button></div>}</div>
          {p && <Section title={`Hops (${p.hop_count})`} hint="Every hop cites its statement row; corroborated hops appear in two statements.">
            <Table cols={["#", "From", "To", "Amount", "Reference", "Event time", "Precision", "Class", "Flags", "Source row"]} rows={p.hops.map((h: any, k: number) => [k + 1, <span key="f" className="mono">{h.src}</span>, <span key="t" className="mono">{h.dst}</span>, <Money key="a" v={h.amount_minor} />, <span key="r" className="mono text-xs">{h.reference || "—"}</span>, <When key="w" v={h.time} />, h.precision, <Chip key="c" v={h.hop_class === "uncertain_time" ? "candidate" : h.hop_class} title={h.hop_class} />, h.flags.join(", ") || "—", <Locator key="l" caseId={id} evidenceId={h.evidence_item_id} />])} />
            <p className="mt-2 text-xs muted">Verify offline: <code className="kbd">python scripts/verify_proof.py proof_path{idx}.json --files &lt;folder with the original files&gt;</code>. A modified file or changed value fails verification.</p>
          </Section>}
          {!p && <div className="card text-sm muted">No reconstructed path.</div>}
        </div>
      )}
    </State>
  );
}

"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, Locator } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Evidence-to-Claim Mapping' subtitle='Every relationship the report asserts, with the exact source record behind it: file, hash, locator and extraction method. Assertions without a source are reported as gaps.' pageKey='evidence-claims'>
      {(id) => <ApiTable title='Evidence-to-Claim Mapping' hint='Rows without a cited source are gaps, never silently accepted.' path={`/cases/${id}/report.json`} pick={(d) => d.relationships || []} empty='No assertions yet.' raw={false} limitations={undefined} cols={[
        { h: "Assertion", cell: (r) => <span className="text-xs"><span className="mono">{r.type}</span> {r.source} → {r.target}</span> },
        { h: "Level", cell: (r) => <Chip v={r.evidence_level} /> },
        { h: "Method", cell: (r) => <span className="mono text-xs">{r.method}</span> },
        { h: "Sources", cell: (r) => <ul className="text-xs">{r.sources.map((s: any, i: any) => <li key={i}><Locator file={s.file} sha256={s.sha256} locator={s.locator} evidenceId={s.evidence_item_id} /> · {s.method}</li>)}{r.sources.length === 0 && <li className="warn">no source cited — gap</li>}</ul> },
        { h: "Limitations", cell: (r) => <span className="text-xs warn">{r.limitations.slice(0, 2).join(", ")}</span> },
      ]} />}
    </ListPage>
  );
}

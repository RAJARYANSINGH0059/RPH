"use client";

import ListPage from "@/components/ListPage";
import { Chip, KV, Limitations, Section, State, Table, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Evidence Integrity and Hashes" subtitle="Separate dimensions per file: file integrity (SHA-256 recomputed), source authenticity (provenance class; verified only with a recorded method), statement completeness, arithmetic consistency, extraction agreement and provenance. No single authenticity score." pageKey="integrity">{(id) => <Body id={id} />}</ListPage>;
}

const D = (v: string) => <Chip v={v === "ok" || v === "consistent" || v === "agree" || v === "recorded" || v === "as_supplied" ? "verified" : v === "MODIFIED" || v === "inconsistent" || v === "disputed" ? "contradicted" : v.startsWith("unverified") || v === "review_required" || v === "partial" ? "candidate" : "insufficient"} title={v} />;

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/integrity`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-3"><div className="metric"><div className="label mb-0">Files</div><div className="metric-value mt-2">{data.files.length}</div></div><div className="metric"><div className="label mb-0">Row-level anomalies</div><div className="metric-value mt-2">{data.anomaly_count}</div></div><div className="metric"><div className="label mb-0">Provisional transactions</div><div className="metric-value mt-2">{data.provisional_transaction_ids.length}</div><div className="text-xs muted">disputed rows cannot become confirmed links silently</div></div></div>
          <Section title="Dimensions per file"><Table dense cols={["File", "Integrity", "Authenticity", "Completeness", "Arithmetic", "Extraction", "Provenance"]} rows={data.files.map((f: any) => [<span key="n" className="font-medium">{f.file.name}</span>, D(f.dimensions.file_integrity), <span key="a" className="text-xs">{D(f.dimensions.source_authenticity)} {f.source_authenticity.provenance_class}</span>, D(f.dimensions.statement_completeness), D(f.dimensions.arithmetic_consistency), D(f.dimensions.extraction_agreement), D(f.dimensions.provenance)])} /></Section>
          {data.files.filter((f: any) => f.statement_forensics).map((f: any) => (
            <Section key={f.file.id} title={`Statement forensics — ${f.file.name}`} hint={f.statement_forensics.arithmetic ? `${f.statement_forensics.arithmetic.formula}: opening ${f.statement_forensics.arithmetic.opening_minor} + credits ${f.statement_forensics.arithmetic.credits_minor} − debits ${f.statement_forensics.arithmetic.debits_minor} = ${f.statement_forensics.arithmetic.expected_closing_minor}; stated ${f.statement_forensics.arithmetic.stated_closing_minor} (difference ${f.statement_forensics.arithmetic.difference_minor} paise)` : "No running balance column: arithmetic not checkable."}>
              <Table dense cols={["Row", "Kind", "Severity", "Detail"]} rows={f.statement_forensics.anomalies.map((a: any) => [a.row ?? "—", <span key="k" className="mono">{a.kind}</span>, <Chip key="s" v={a.severity} />, <span key="d" className="text-xs">{a.detail}</span>])} empty="No anomalies in this statement." />
            </Section>
          ))}
          {data.files.filter((f: any) => f.metadata_leads?.available && f.metadata_leads.leads?.length).map((f: any) => <Section key={f.file.id + "m"} title={`PDF metadata leads — ${f.file.name}`} hint={f.metadata_leads.note}><ul className="list-disc pl-5 text-xs">{f.metadata_leads.leads.map((l: string) => <li key={l}>{l}</li>)}</ul><KV className="mt-2 text-xs" rows={Object.entries(f.metadata_leads.metadata || {}).map(([k, v]: [any, any]) => [k, String(v)])} /></Section>)}
          <Limitations items={data.limitations} />
        </div>
      )}
    </State>
  );
}

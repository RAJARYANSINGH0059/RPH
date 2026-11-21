"use client";

/** Generic "fetch one endpoint, render sections" page used by the focused views (infra, vault, audit, …).
 * Each view supplies real rows from real API data; nothing is mocked. */
import CasePage from "@/components/CasePage";
import { Limitations, Raw, Section, State, Table, useApi } from "@/components/ui";

export type Col = { h: string; cell: (r: any) => React.ReactNode };

export function ApiTable({ path, cols, pick, empty, title, hint, dense = true, limitations, raw }: { path: string; cols: Col[]; pick?: (d: any) => any[]; empty?: string; title: string; hint?: string; dense?: boolean; limitations?: (d: any) => string[] | undefined; raw?: boolean }) {
  const { data, error, reload } = useApi<any>(path);
  const rows = data ? (pick ? pick(data) : Array.isArray(data) ? data : []) : [];
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && <div className="space-y-3"><Section title={`${title} (${rows.length})`} hint={hint} className="!p-0 [&>div]:px-4 [&>div]:pt-4"><Table dense={dense} cols={cols.map((c) => c.h)} rows={rows.map((r: any) => cols.map((c) => c.cell(r)))} empty={empty} /></Section>{limitations && <Limitations items={limitations(data)} />}{raw && <Raw data={data} />}</div>}
    </State>
  );
}

export default function ListPage({ title, subtitle, pageKey, children }: { title: string; subtitle: string; pageKey?: string; children: (id: string, c: any) => React.ReactNode }) {
  return <CasePage title={title} subtitle={subtitle} pageKey={pageKey} wide>{(c, id) => children(id, c)}</CasePage>;
}

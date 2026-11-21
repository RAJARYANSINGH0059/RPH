"use client";

/** Case-scoped page template: loads the case header, renders Shell with case context, hands the case to children. */
import { useParams } from "next/navigation";
import Shell from "@/components/Shell";
import { State, useApi } from "@/components/ui";

export type CaseHead = { id: string; title: string; is_synthetic: boolean; internal_ref: string; status: string; files_count: number; transactions_count: number; relationships_count: number; findings_awaiting_review: number };

export default function CasePage({ title, subtitle, pageKey, actions, primary, wide, children }: { title: string; subtitle: string; pageKey?: string; actions?: React.ReactNode; primary?: React.ReactNode; wide?: boolean; children: (c: CaseHead, id: string) => React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const { data: c, error, reload } = useApi<CaseHead>(`/cases/${id}`);
  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={!!c && !c.is_synthetic} title={title} subtitle={subtitle} pageKey={pageKey} actions={actions} primary={primary} wide={wide}>
      <State loading={!c && !error} error={error} onRetry={reload}>{c && children(c, id)}</State>
    </Shell>
  );
}

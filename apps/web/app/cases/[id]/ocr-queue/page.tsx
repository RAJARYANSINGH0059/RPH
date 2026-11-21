"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, Locator } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='OCR Review Queue' subtitle='Low-confidence or unverified OCR extractions that need a human to check against the image. OCR output is never treated as verified evidence.' pageKey='ocr-queue'>
      {(id) => <ApiTable title='OCR Review Queue' hint='' path={`/cases/${id}/twin`} pick={(d) => d.events.filter((e: any) => ["WEBSITE_CAPTURE_SUPPLIED", "PAYMENT_PAGE_OBSERVED"].includes(e.event_type) || (e.evidence_class === "candidate" && e.layer !== "infrastructure"))} empty='No OCR-derived items awaiting verification (OCR may be off on this deployment).' raw={false} limitations={undefined} cols={[
        { h: "Class", cell: (e) => <Chip v={e.evidence_class} /> },
        { h: "Label", cell: (e) => e.label },
        { h: "Engine / confidence", cell: (e) => <span className="text-xs">{e.attributes.ocr?.engine ?? "—"} · {e.attributes.ocr?.confidence ?? "—"} · {e.attributes.ocr?.quality ?? ""}</span> },
        { h: "Excerpt", cell: (e) => <span className="text-xs mono">{(e.attributes.excerpt || "").slice(0, 120)}</span> },
        { h: "Source", cell: (e) => <Locator evidenceId={e.evidence_ids?.[0]} file={e.attributes.file} locator={e.source_locator} /> },
      ]} />}
    </ListPage>
  );
}

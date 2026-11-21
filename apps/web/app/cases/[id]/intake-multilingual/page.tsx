"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { KV, Section, State, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Multilingual Evidence Intake" subtitle="OCR engine chain and language coverage for this deployment: Tesseract (English + Hindi where trained data is installed) → RapidOCR (English/Latin) → explicit unavailable. Engine, version, confidence and boxes are stored on every OCR evidence item." pageKey="multilingual">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/health/live`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <Section title="OCR engines on this deployment"><KV rows={[["Mode", data.ocr.mode], ["Active engine", data.ocr.active_engine || "none (images are stored for manual review)"], ["Tesseract", data.ocr.tesseract.available ? `v${data.ocr.tesseract.version} · languages ${data.ocr.tesseract.languages?.join(", ")}` : data.ocr.tesseract.reason], ["RapidOCR", data.ocr.rapidocr.available ? `v${data.ocr.rapidocr.version} · ${data.ocr.rapidocr.languages?.join(", ")}` : data.ocr.rapidocr.reason]]} /><p className="mt-2 text-xs muted">Hindi OCR needs the Tesseract `hin` trained data (shipped in the Docker image). The free-tier API runs with OCR off because the runtime exceeded its memory; uploads still store the image and flag it for manual review.</p></Section>
          <div className="card flex items-center justify-between text-sm"><span>Upload scans, screenshots or Hindi/English PDFs through Evidence Intake; low-confidence extractions land in the OCR Review Queue.</span><Link href={`/cases/${id}/upload`} className="btn">Open Evidence Intake</Link></div>
        </div>
      )}
    </State>
  );
}

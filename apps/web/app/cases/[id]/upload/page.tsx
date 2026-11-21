"use client";

import { useParams } from "next/navigation";
import { DragEvent, useEffect, useRef, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api } from "@/lib/api";

const FIELDS: [string, string][] = [["datetime", "Date / time"], ["narration", "Narration"], ["reference", "Reference / UTR"], ["debit", "Debit"], ["credit", "Credit"], ["amount", "Amount (single column)"], ["direction", "Dr/Cr column"], ["balance", "Balance"], ["counterparty", "Counterparty id"], ["counterparty_name", "Counterparty name"], ["account", "Account no."], ["channel", "Channel"]];
const KINDS = [["CSV / XLSX", "Bank or UPI statements, any column names", <I.money key="1" />], ["PDF / DOCX / TXT", "Complaints, notes, reports", <I.file key="2" />], ["JSON", "Technical observations (DNS, hosting, URL, RDAP)", <I.sources key="3" />], ["PNG / JPG", "Screenshots (OCR only if an engine is installed)", <I.eye key="4" />]];
const WARN_HELP: Record<string, string> = { header_detected_at: "Title lines were skipped before the header row.", balance_reconciliation_mismatch: "Opening + credits − debits does not equal the closing balance; a row may be missing or wrong.", unmapped_columns: "Some columns were kept as raw text but not interpreted.", mapping_incomplete: "Date or amount column not found; set the mapping below.", duplicate_file: "This exact file was uploaded before.", extension_mismatch: "The file content is a different type than its extension suggests.", ocr_unavailable: "No OCR engine on the server; the image is stored and hashed for manual review.", no_text_layer: "Scanned page; no text could be extracted.", account_column_absent: "No account column; the statement holder is inferred from the file.", decoded_as_latin1: "Non-UTF-8 text was decoded with a fallback." };
const helpFor = (w: string) => Object.entries(WARN_HELP).find(([k]) => w.startsWith(k))?.[1] || "";

export default function UploadPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<any>(null);
  const [runs, setRuns] = useState<any[]>([]);
  const [files, setFiles] = useState<any[]>([]);
  const [results, setResults] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [mapping, setMapping] = useState<Record<string, Record<string, string>>>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const load = () => Promise.all([api(`/cases/${id}`), api(`/cases/${id}/parse-runs`), api(`/cases/${id}/files`)]).then(([cc, rr, ff]) => { setC(cc); setRuns(rr); setFiles(ff); }).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function send(list: FileList | File[]) {
    const fd = new FormData(); Array.from(list).forEach((f) => fd.append("files", f));
    setBusy(true); setError(null);
    try { const r = await api(`/cases/${id}/upload`, { method: "POST", body: fd }); setResults(r); await load(); }
    catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }
  function onDrop(e: DragEvent) { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) send(e.dataTransfer.files); }
  async function remap(fileId: string) {
    setBusy(true);
    try { const r = await api(`/cases/${id}/files/${fileId}/remap`, { method: "POST", body: JSON.stringify({ mapping: mapping[fileId] || {} }) }); setResults([r]); await load(); }
    catch (err: any) { setError(err.message); } finally { setBusy(false); }
  }
  const fileName = (fid: string) => files.find((f: any) => f.id === fid)?.original_name || fid;

  return (
    <Shell caseId={id} caseTitle={c?.title} synthetic={c?.is_synthetic} uploaded={c && !c.is_synthetic} title="Upload evidence" subtitle="Drop files, read the preview, correct a column mapping if needed. Originals are never modified." pageKey="upload" step={runs.length ? "parse" : "upload"}>
      <div className="space-y-4">
        <div role="button" tabIndex={0} aria-label="Drop files or press Enter to choose files" onClick={() => inputRef.current?.click()} onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
          className={`card cursor-pointer border-2 border-dashed py-8 text-center transition ${drag ? "border-accent bg-accent-light" : "hover:border-accent/50"}`}>
          <div className="mx-auto mb-2 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-light text-accent"><I.upload width={24} height={24} /></div>
          <div className="font-semibold">Drag and drop files here, or click to choose</div>
          <div className="mt-1 text-xs text-ink-muted">Up to 20 files, 25 MB each. Content is type-checked by magic bytes, hashed with SHA-256 and never executed.</div>
          <input ref={inputRef} type="file" multiple className="hidden" onChange={(e) => e.target.files && send(e.target.files)} />
        </div>
        <div className="grid gap-2 sm:grid-cols-4">{KINDS.map(([t, d, ic]) => <div key={t as string} className="flex gap-2 rounded-xl border border-line bg-card p-2.5 text-xs"><span className="text-accent">{ic}</span><div><div className="font-semibold">{t}</div><div className="text-ink-muted">{d}</div></div></div>)}</div>
        {busy && <div className="card flex items-center gap-3 text-sm" role="status"><span className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />Uploading and parsing…</div>}
        {error && <div className="card flex gap-2 border-danger/30 bg-danger-soft text-sm text-danger" role="alert"><I.alert />{error}</div>}
        {results.map((r: any) => (
          <div key={r.file.id} className="card space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 font-semibold"><I.check className="text-ok" />{r.file.original_name} <span className="badge bg-panel">{r.file.detected_kind}</span><span className={`badge ${r.file.status === "parsed" ? "bg-ok-soft text-ok" : r.file.status === "failed" ? "bg-danger-soft text-danger" : "bg-saffron-soft text-warn"}`}>{r.file.status.replace("_", " ")}</span></div>
              <div className="mono text-[11px] text-ink-muted">sha256 {r.file.sha256}</div>
            </div>
            {r.parse_run?.warnings?.length > 0 && (
              <div className="rounded-lg border border-saffron/50 bg-saffron-soft p-2.5 text-xs"><div className="mb-1 font-semibold warn">What the parser noticed</div><ul className="space-y-0.5">{r.parse_run.warnings.map((w: string, i: number) => <li key={i}><span className="mono">{w.replace(/_/g, " ")}</span>{helpFor(w) && <span className="text-ink-muted"> — {helpFor(w)}</span>}</li>)}</ul></div>
            )}
            {r.preview?.counts && <div className="flex flex-wrap gap-2 text-xs">{Object.entries(r.preview.counts).map(([k, v]: any) => <span key={k} className="rounded-full bg-panel px-2.5 py-1"><strong>{v}</strong> {k.replace(/_/g, " ")}</span>)}{r.preview.reconciliation && <span className={`rounded-full px-2.5 py-1 ${r.preview.reconciliation.mismatch_minor ? "bg-saffron-soft warn" : "bg-ok-soft text-ok"}`}>balance {r.preview.reconciliation.mismatch_minor ? `mismatch ₹${(r.preview.reconciliation.mismatch_minor / 100).toFixed(2)}` : "reconciles"}</span>}</div>}
            {r.preview?.headers && (
              <details open={Object.keys(r.preview.mapping).length < 4}>
                <summary className="cursor-pointer text-sm font-semibold">Column mapping <span className="font-normal text-ink-muted">— {Object.keys(r.preview.mapping).length} of {r.preview.headers.length} columns understood; change a mapping and re-parse if something is wrong</span></summary>
                <div className="mt-2 grid gap-2 md:grid-cols-3 lg:grid-cols-4">
                  {FIELDS.map(([f, label]: [any, any]) => (
                    <label key={f} className="text-xs"><span className="text-ink-muted">{label}</span>
                      <select className="input mt-0.5" value={(mapping[r.file.id] || {})[f] ?? r.preview.mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [r.file.id]: { ...(mapping[r.file.id] || {}), [f]: e.target.value } })}>
                        <option value="">— not mapped —</option>{r.preview.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}
                      </select></label>))}
                </div>
                <button className="btn-secondary mt-2" onClick={() => remap(r.file.id)} disabled={busy}>Re-parse with this mapping</button>
              </details>
            )}
            {r.preview?.rows && <div className="overflow-x-auto rounded-lg border border-line"><table className="data"><thead><tr><th>Row</th>{r.preview.headers.map((h: string) => <th key={h}>{h}{Object.entries(r.preview.mapping).find(([, v]) => v === h) && <div className="font-normal normal-case text-accent">↳ {Object.entries(r.preview.mapping).find(([, v]) => v === h)![0].replace("_", " ")}</div>}</th>)}<th>Flags</th></tr></thead>
              <tbody>{r.preview.rows.map((row: any) => <tr key={row.row}><td className="text-xs text-ink-muted">{row.row}</td>{r.preview.headers.map((h: string) => <td key={h} className="whitespace-nowrap text-xs">{row.raw[h] ?? ""}</td>)}<td className="text-xs warn">{row.warnings.map((w: string) => w.replace(/_/g, " ")).join(", ")}</td></tr>)}</tbody></table></div>}
            {r.preview?.snippets && <div className="space-y-1 text-xs"><div className="label">Extracted text (first blocks)</div>{r.preview.snippets.map((s: any, i: number) => <pre key={i} className="whitespace-pre-wrap rounded-lg bg-canvas p-2">[{Object.entries(s.locator).map(([k, v]: [any, any]) => `${k} ${v}`).join(", ")} · {s.method.replace("_", " ")}] {s.text}</pre>)}<div className="text-ink-muted">Indicators found: {Object.entries(r.preview.indicators || {}).map(([k, v]: [any, any]) => `${v} ${k}`).join(", ") || "none"}</div></div>}
            {r.preview?.snippets && r.preview.snippets.some((x: any) => x.method === "ocr") && (
              <div className="rounded-xl border border-saffron/50 bg-saffron-soft/40 p-3 text-xs">
                <div className="mb-1 flex items-center gap-2 font-semibold warn"><I.eye width={14} height={14} /> OCR output — needs human verification</div>
                <p className="muted">Text below was read from an image by the OCR engine. Confidence is the engine&apos;s own estimate; compare against the original page before relying on any identifier.</p>
                <ul className="mt-2 space-y-1">{r.preview.snippets.filter((x: any) => x.method === "ocr").map((x: any, i: number) => <li key={i} className="rounded-lg border border-line bg-card p-2"><div className="mono">{Object.entries(x.locator).map(([k, v]: [any, any]) => `${k} ${v}`).join(", ")}{x.ocr ? ` · ${x.ocr.engine} v${x.ocr.engine_version} · confidence ${x.ocr.confidence === null ? "n/a" : Math.round(x.ocr.confidence * 100) + "%"} · quality ${x.ocr.quality}` : ""}</div><pre className="mt-1 whitespace-pre-wrap">{x.text}</pre></li>)}</ul>
              </div>
            )}
            {r.preview?.sample && <div className="text-xs text-ink-muted">{r.preview.observations} observations: {Object.entries(r.preview.by_type).map(([k, v]: [any, any]) => `${v} ${k}`).join(", ")}</div>}
            {r.preview?.error && <div className="text-xs text-danger">{r.preview.error}</div>}
          </div>
        ))}
        <State loading={!c && !error}>
          <div className="card p-0">
            <div className="px-4 py-3"><h2 className="font-semibold">Parse history</h2><p className="text-xs text-ink-muted">Every parse keeps the parser version so results are reproducible.</p></div>
            {runs.length === 0 ? <div className="px-4 pb-4 text-sm text-ink-muted">Nothing parsed yet.</div> : (
              <table className="data"><thead><tr><th>File</th><th>Parser</th><th>Result</th><th>Status</th><th>Warnings</th></tr></thead>
                <tbody>{runs.map((r: any) => <tr key={r.id}><td className="font-medium">{fileName(r.source_file_id)}</td><td className="text-xs">{r.parser_name}@{r.parser_version}</td><td className="text-xs">{r.stats.transactions !== undefined ? `${r.stats.transactions} transactions · ${r.stats.ambiguous_dates} ambiguous dates · ${r.stats.duplicates} duplicates` : r.stats.observations !== undefined ? `${r.stats.observations} observations` : `${r.stats.blocks ?? 0} text blocks`}</td><td><span className={`badge ${r.status === "completed" ? "bg-ok-soft text-ok" : "bg-danger-soft text-danger"}`}>{r.status}</span></td><td className="text-xs warn">{(r.warnings || []).slice(0, 4).map((w: string) => w.replace(/_/g, " ")).join("; ")}</td></tr>)}</tbody></table>
            )}
          </div>
        </State>
      </div>
    </Shell>
  );
}

"use client";

import { useParams } from "next/navigation";
import { DragEvent, useEffect, useRef, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api } from "@/lib/api";

const FIELDS = ["datetime", "narration", "reference", "debit", "credit", "amount", "direction", "balance", "counterparty", "counterparty_name", "account", "channel"];

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
    const fd = new FormData();
    Array.from(list).forEach((f) => fd.append("files", f));
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
  const fileName = (fid: string) => files.find((f) => f.id === fid)?.original_name || fid;

  return (
    <Shell caseId={id} synthetic={c?.is_synthetic} title="Upload evidence">
      <div className="space-y-4">
        <div role="button" tabIndex={0} aria-label="Drop files or press Enter to choose files" onClick={() => inputRef.current?.click()} onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
          className={`card cursor-pointer border-2 border-dashed text-center ${drag ? "border-accent bg-accent-light" : ""}`}>
          <div className="font-medium">Drag and drop files here, or click to choose</div>
          <div className="mt-1 text-xs text-ink-muted">Supported: PDF (text or scanned), CSV, XLSX, JSON (technical observations), DOCX, TXT, PNG/JPG (OCR only if an engine is installed). Max 25 MB each, 20 per upload. Files are hashed (SHA-256), type-checked by content, never executed.</div>
          <input ref={inputRef} type="file" multiple className="hidden" onChange={(e) => e.target.files && send(e.target.files)} />
        </div>
        {busy && <div className="card text-sm" role="status">Uploading and parsing…</div>}
        {error && <div className="card border-[#f1c5c5] bg-[#fff5f5] text-sm text-[#8a1c1c]" role="alert">{error}</div>}
        {results.map((r) => (
          <div key={r.file.id} className="card space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2"><div className="font-semibold">{r.file.original_name} <span className="badge bg-[#eef1f4]">{r.file.detected_kind}</span> <span className="badge bg-[#eef1f4]">{r.file.status}</span></div><div className="font-mono text-xs">{r.file.sha256}</div></div>
            {r.parse_run?.warnings?.length > 0 && <ul className="list-disc pl-5 text-xs text-[#8a5a0f]">{r.parse_run.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}</ul>}
            {r.preview?.headers && (
              <div>
                <div className="label">Column mapping (edit and re-parse if wrong)</div>
                <div className="grid gap-2 md:grid-cols-3">
                  {FIELDS.map((f) => (
                    <label key={f} className="text-xs">{f}
                      <select className="input" value={(mapping[r.file.id] || {})[f] ?? r.preview.mapping[f] ?? ""} onChange={(e) => setMapping({ ...mapping, [r.file.id]: { ...(mapping[r.file.id] || {}), [f]: e.target.value } })}>
                        <option value="">— not mapped —</option>{r.preview.headers.map((h: string) => <option key={h} value={h}>{h}</option>)}
                      </select></label>))}
                </div>
                <button className="btn-secondary mt-2" onClick={() => remap(r.file.id)} disabled={busy}>Re-parse with this mapping</button>
                <div className="mt-3 overflow-x-auto"><table className="data"><thead><tr><th>Row</th>{r.preview.headers.map((h: string) => <th key={h}>{h}</th>)}<th>Flags</th></tr></thead>
                  <tbody>{r.preview.rows.map((row: any) => <tr key={row.row}><td>{row.row}</td>{r.preview.headers.map((h: string) => <td key={h} className="whitespace-nowrap text-xs">{row.raw[h] ?? ""}</td>)}<td className="text-xs text-[#8a5a0f]">{row.warnings.join(", ")}</td></tr>)}</tbody></table></div>
              </div>
            )}
            {r.preview?.snippets && <div className="space-y-1 text-xs">{r.preview.snippets.map((s: any, i: number) => <pre key={i} className="whitespace-pre-wrap rounded bg-[#f6f8fa] p-2">[{JSON.stringify(s.locator)} · {s.method}] {s.text}</pre>)}<div className="text-ink-muted">Indicators found: {JSON.stringify(r.preview.indicators)}</div></div>}
            {r.preview?.sample && <div className="text-xs text-ink-muted">{r.preview.observations} observations · {JSON.stringify(r.preview.by_type)}</div>}
            {r.preview?.error && <div className="text-xs text-[#8a1c1c]">{r.preview.error}</div>}
          </div>
        ))}
        <State loading={!c && !error} empty={runs.length === 0 ? "No parse runs yet." : null}>
          <div className="card overflow-x-auto p-0"><table className="data"><thead><tr><th>File</th><th>Parser</th><th>Status</th><th>Stats</th><th>Warnings</th></tr></thead>
            <tbody>{runs.map((r) => <tr key={r.id}><td>{fileName(r.source_file_id)}</td><td>{r.parser_name}@{r.parser_version}</td><td>{r.status}</td><td className="text-xs">{r.stats.transactions !== undefined ? `${r.stats.transactions} tx, ${r.stats.ambiguous_dates} ambiguous dates, ${r.stats.duplicates} dup` : r.stats.observations !== undefined ? `${r.stats.observations} observations` : `${r.stats.blocks ?? 0} blocks`}</td><td className="text-xs text-[#8a5a0f]">{(r.warnings || []).slice(0, 5).join("; ")}</td></tr>)}</tbody></table></div>
        </State>
      </div>
    </Shell>
  );
}

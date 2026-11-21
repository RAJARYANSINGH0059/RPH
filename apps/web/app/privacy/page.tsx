"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { KV, Limitations, Section, State, Table, Toast, useApi } from "@/components/ui";
import { api, getUser, isReviewer } from "@/lib/api";

export default function Page() {
  const st = useApi<any>("/privacy/status");
  const [cases, setCases] = useState<any[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [res, setRes] = useState<any>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => { api("/cases").then(setCases).catch(() => undefined); }, []);
  async function match() { setMsg(null); try { setRes(await api("/privacy/match", { method: "POST", body: JSON.stringify({ case_ids: sel }) })); } catch (e: any) { setMsg(e.message); } }
  async function reveal(eid: string) { const purpose = window.prompt("Purpose / necessity for revealing the raw identifier (recorded in the audit log)"); if (!purpose) return; try { const r = await api("/privacy/reveal", { method: "POST", body: JSON.stringify({ entity_id: eid, purpose }) }); setMsg(`Revealed (audited): ${r.raw_value}`); } catch (e: any) { setMsg(e.message); } }
  return (
    <Shell title="Privacy-Preserving Cross-Case Matching" subtitle="Keyed HMAC tokens over normalised identifiers let you discover a possible identifier match without showing raw values to everyone. Enabled only when a server-side key is configured. Deterministic keyed hashing is not anonymisation." pageKey="privacy">
      <State loading={st.loading} error={st.error} onRetry={st.reload}>
        {st.data && (
          <div className="space-y-3">
            <Section title="Capability"><KV rows={[["Enabled", st.data.enabled ? "yes" : "no"], ["Key version", st.data.key_version || "—"], ["Construction", st.data.construction], ["Reason", st.data.reason || "—"]]} /></Section>
            {st.data.enabled ? (
              <Section title="Match across cases"><div className="grid gap-1 sm:grid-cols-3 text-sm">{cases.map((c: any) => <label key={c.id} className="inset flex items-center gap-2 p-2"><input type="checkbox" checked={sel.includes(c.id)} onChange={(e) => setSel((s) => e.target.checked ? [...s, c.id] : s.filter((x: any) => x !== c.id))} /><span className="truncate">{c.title}</span></label>)}</div><button className="btn mt-2" disabled={sel.length < 2} onClick={match}>Match tokens</button>
                {res && <Table dense cols={["Token", "Type", "Cases", "Raw value", ""]} rows={res.matches.map((m: any) => [<span key="t" className="mono text-xs">{m.token.slice(0, 16)}…</span>, m.entity_type, m.cases.length, "hidden", isReviewer(getUser()) ? <button key="r" className="btn-secondary !py-1" onClick={() => reveal(m.entity_ids[0])}>Reveal (audited)</button> : <span key="r" className="text-xs muted">supervisor only</span>])} empty="No shared identifier tokens." />}
                <Toast msg={msg} onClose={() => setMsg(null)} /></Section>
            ) : <div className="callout-warn text-sm">Disabled by design on this deployment: no CROSSCASE_TOKEN_KEY is configured and no key is hard-coded. Cross-case correlation with explicit permissions remains available.</div>}
            <Limitations items={st.data.limitations} />
          </div>
        )}
      </State>
    </Shell>
  );
}

"use client";

import { useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { api, fmtTime, getUser } from "@/lib/api";

const STYLE: Record<string, string> = { live: "bg-[#e3f3f0] text-[#136f63]", configured: "bg-[#e7eff9] text-[#174a84]", not_configured: "bg-[#eef1f4] text-ink-muted", unavailable: "bg-[#fde8e8] text-[#8a1c1c]", mock: "bg-[#fdf3e0] text-[#8a5a0f]" };

export default function SourcesPage() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const role = getUser()?.role;
  useEffect(() => { api("/connectors/status").then(setRows).catch((e) => setError(e.message)); }, []);
  async function check() { setBusy(true); try { setRows(await api("/connectors/healthcheck", { method: "POST" })); } catch (e: any) { setError(e.message); } finally { setBusy(false); } }
  return (
    <Shell title="Data sources and settings">
      <State loading={!rows && !error} error={error}>
        <div className="space-y-4">
          <div className="card text-sm">
            <p>External connectors are optional, server-side only, host-allowlisted and fault-isolated. Synthetic mode and manual uploads work with every provider offline. A connector is shown as <strong>live</strong> only after a real authenticated request succeeded. Current DNS/RDAP lookups are labelled as current observations, never as historical evidence.</p>
            {(role === "admin" || role === "supervisor") && <button className="btn mt-2" onClick={check} disabled={busy}>{busy ? "Checking…" : "Run health checks"}</button>}
          </div>
          <div className="card overflow-x-auto p-0"><table className="data"><thead><tr><th>Connector</th><th>Status</th><th>Provider</th><th>Detail</th><th>Checked</th></tr></thead>
            <tbody>{rows?.map((r) => <tr key={r.name}><td className="font-medium">{r.name}</td><td><span className={`badge ${STYLE[r.status]}`}>{r.status.replace("_", " ")}</span></td><td className="text-xs">{r.provider}</td><td className="text-xs">{r.detail}</td><td className="text-xs">{fmtTime(r.last_checked)}</td></tr>)}</tbody></table></div>
          <div className="card text-xs text-ink-muted"><div className="label">Configuration</div>Set <code>ENABLE_RDAP</code>, <code>ENABLE_DNS</code>, <code>URLHAUS_AUTH_KEY</code>, <code>THREATFOX_AUTH_KEY</code>, <code>MISP_URL</code>/<code>MISP_KEY</code> in the API environment. No NCRP/CFCFRMS/bank integration exists in this build; such integration requires written authorisation, documented APIs and test credentials.</div>
        </div>
      </State>
    </Shell>
  );
}

"use client";

import { useEffect, useState } from "react";
import Shell, { State } from "@/components/Shell";
import { I } from "@/components/icons";
import { api, fmtTime, getUser } from "@/lib/api";

const STYLE: Record<string, string> = { live: "bg-ok-soft text-ok", configured: "bg-accent-soft text-accent-deep", not_configured: "bg-panel text-ink-muted", unavailable: "bg-danger-soft text-danger", mock: "bg-saffron-soft text-warn" };
const MEANING: Record<string, string> = { live: "A real authenticated request succeeded in this process.", configured: "Credentials/flags are present; no request has been made yet.", not_configured: "Disabled or no key. The app works without it.", unavailable: "Configured but the last health check failed.", mock: "Offline synthetic adapter; never contacts a network." };
const ABOUT: Record<string, string> = { rdap: "Current domain registration data (registrar, creation date). Current state only, not historical ownership.", dns: "Current A-record answers from the system resolver. Not passive/historical DNS.", urlhaus: "abuse.ch URLhaus malware-URL indicators (community key).", threatfox: "abuse.ch ThreatFox IOC look-ups (community key; IOCs expire after ~6 months).", misp: "Operator-run MISP instance via its Automation API.", synthetic_mock: "Technical observations shipped inside synthetic case bundles." };

export default function SourcesPage() {
  const [rows, setRows] = useState<any[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const role = getUser()?.role;
  useEffect(() => { api("/connectors/status").then(setRows).catch((e) => setError(e.message)); }, []);
  async function check() { setBusy(true); try { setRows(await api("/connectors/healthcheck", { method: "POST" })); } catch (e: any) { setError(e.message); } finally { setBusy(false); } }
  return (
    <Shell title="Data sources and settings" subtitle="External look-ups are optional, server-side, host-allowlisted and fault-isolated." pageKey="sources"
      actions={(role === "admin" || role === "supervisor") && <button className="btn" onClick={check} disabled={busy}>{busy ? "Checking…" : <><I.play /> Run health checks</>}</button>}>
      <State loading={!rows && !error} error={error}>
        <div className="space-y-4">
          <div className="callout"><I.shield className="shrink-0 text-accent" /><div>Synthetic mode and manual uploads work with every provider offline. A connector shows <strong>live</strong> only after a real authenticated request succeeded. Current DNS/RDAP answers are labelled as current observations, never as historical evidence. There is no NCRP, CFCFRMS or bank integration in this build.</div></div>
          <ul className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {rows?.map((r: any) => (
              <li key={r.name} className="card">
                <div className="flex items-start justify-between gap-2"><div className="font-semibold">{r.name.replace("_", " ")}</div><span className={`badge ${STYLE[r.status]}`}>{r.status.replace("_", " ")}</span></div>
                <div className="mt-1 text-xs text-ink-muted">{r.provider}</div>
                <p className="mt-2 text-sm">{ABOUT[r.name]}</p>
                <div className="mt-2 rounded-lg bg-canvas p-2 text-xs"><div className="font-semibold">{MEANING[r.status]}</div><div className="text-ink-muted">{r.detail}</div></div>
                <div className="mt-1 text-[11px] text-ink-muted">checked {fmtTime(r.last_checked)}</div>
              </li>
            ))}
          </ul>
          <div className="card text-xs text-ink-muted"><div className="label">How operators enable a connector</div>Set <code>ENABLE_RDAP=true</code>, <code>ENABLE_DNS=true</code>, <code>URLHAUS_AUTH_KEY</code>, <code>THREATFOX_AUTH_KEY</code> or <code>MISP_URL</code>/<code>MISP_KEY</code> in the API environment (Render dashboard or <code>apps/api/.env</code>) and restart. Keys never reach the browser.</div>
        </div>
      </State>
    </Shell>
  );
}

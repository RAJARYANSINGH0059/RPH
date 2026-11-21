"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { Chip, KV, Section, State, Table, useApi, When } from "@/components/ui";
import { api, getUser, isReviewer } from "@/lib/api";

export default function Page() {
  const live = useApi<any>("/health/live");
  const ready = useApi<any>("/health/ready");
  const [checked, setChecked] = useState<any[] | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  async function run() { setMsg(null); try { setChecked(await api("/connectors/healthcheck", { method: "POST" })); } catch (e: any) { setMsg(e.message); } }
  return (
    <Shell title="Integration Health" subtitle="API liveness and readiness, OCR runtime, storage backend, ML model status and connector health checks (supervisor/admin)." pageKey="sources">
      <div className="space-y-3">
        <State loading={live.loading} error={live.error} onRetry={live.reload}>{live.data && <Section title="API"><KV rows={[["Service", `${live.data.service} ${live.data.version}`], ["Database", ready.data ? `${ready.data.database} · migrations ${ready.data.migrations}` : "…"], ["OCR", `${live.data.ocr.mode} · active ${live.data.ocr.active_engine || "none"}`], ["Storage", `${live.data.storage.backend}${live.data.storage.note ? ` · ${live.data.storage.note}` : ""}`], ["ML triage model", live.data.ml_triage_model.status || JSON.stringify(live.data.ml_triage_model).slice(0, 120)]]} /></Section>}</State>
        <Section title="Connector health check" hint={isReviewer(getUser()) ? "Runs one real request per configured connector." : "Only supervisors/admins can trigger live checks; demo visitors see configured states on the Connectors page."}>
          <button className="btn-secondary" onClick={run} disabled={!isReviewer(getUser())}>Run health check</button>
          {msg && <p className="mt-2 text-sm danger">{msg}</p>}
          {checked && <Table dense cols={["Connector", "Status", "Detail", "Checked"]} rows={checked.map((c: any) => [c.name, <Chip key="s" v={c.status} />, <span key="d" className="text-xs">{c.detail}</span>, <When key="w" v={c.last_checked} />])} />}
        </Section>
      </div>
    </Shell>
  );
}

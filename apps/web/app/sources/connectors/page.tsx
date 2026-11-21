"use client";

import Shell from "@/components/Shell";
import { Chip, Limitations, State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  const { data, error, reload } = useApi<any[]>("/connectors/status");
  return (
    <Shell title="Connectors and Integrations" subtitle="RDAP, current DNS, URLhaus, ThreatFox, MISP and the synthetic mock. Keys live only in server environment variables. Results of live connectors are current-time observations and are labelled as such." pageKey="sources">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <div className="space-y-3"><Table cols={["Connector", "Provider", "Status", "Detail", "Last checked"]} rows={data.map((c: any) => [c.name, c.provider, <Chip key="s" v={c.status} />, <span key="d" className="text-xs">{c.detail}</span>, <When key="w" v={c.last_checked} />])} />
          <Limitations items={["No police, bank, NCRP/CFCFRMS, telecom or registrar integration exists; by design.", "Current DNS/RDAP lookups are never presented as historical evidence.", "SSRF guard: HTTPS allowlist, private/metadata ranges blocked, no redirects, bounded size and time."]} /></div>}
      </State>
    </Shell>
  );
}

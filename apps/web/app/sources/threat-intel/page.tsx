"use client";

import Shell from "@/components/Shell";
import { Chip, State, Table, useApi, When } from "@/components/ui";

export default function Page() {
  const { data, error, reload } = useApi<any[]>("/connectors/status");
  const ti = (data || []).filter((c: any) => /urlhaus|threatfox|misp/i.test(c.name) || /urlhaus|threatfox|misp/i.test(c.provider));
  return (
    <Shell title="Threat-Intelligence Sources" subtitle="URLhaus, ThreatFox and MISP adapters with honest states. 'live' appears only after a real authenticated request succeeded; synthetic .test domains are never looked up." pageKey="sources">
      <State loading={!data && !error} error={error} onRetry={reload}>
        {data && <Table cols={["Connector", "Provider", "Status", "Detail", "Last checked"]} rows={ti.map((c: any) => [c.name, c.provider, <Chip key="s" v={c.status} />, <span key="d" className="text-xs">{c.detail}</span>, <When key="w" v={c.last_checked} />])} empty="No threat-intelligence connectors registered." />}
      </State>
    </Shell>
  );
}

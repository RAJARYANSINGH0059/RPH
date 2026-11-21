"use client";

import Link from "next/link";
import ListPage from "@/components/ListPage";
import { MotionScene } from "@/components/motion";
import { KV, Section, State, useApi } from "@/components/ui";

export default function Page() {
  return <ListPage title="Campaign DNA" subtitle="This case's structural fingerprint (version campaign-fingerprint-1.0): page structure, payment-instruction pattern, financial choreography, message template and infrastructure timeline. Personal identifiers are excluded. Compare cases in Fraud Campaign Evolution." pageKey="dna">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/campaign/fingerprint/${id}`);
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Object.entries(data.dimensions).map(([k, v]: [string, any]) => <Section key={k} title={k.replace(/_/g, " ")}><KV className="text-xs" rows={Object.entries(v).filter(([kk]) => kk !== "trigrams").map(([kk, vv]: [any, any]) => [kk.replace(/_/g, " "), Array.isArray(vv) ? (vv.length ? vv.slice(0, 12).map((x: any) => typeof x === "object" ? JSON.stringify(x) : String(x)).join(", ") + (vv.length > 12 ? ` … (${vv.length})` : "") : "none") : String(vv)])} /></Section>)}
          </div>
          <div className="flex items-center justify-between gap-3 card text-sm"><span>Compare this fingerprint with other cases you can access.</span><Link href="/campaign" className="btn">Open Fraud Campaign Evolution</Link></div>
          <MotionScene scene="campaign_evolution" height={110} />
        </div>
      )}
    </State>
  );
}

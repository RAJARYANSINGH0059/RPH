"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, Money, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Split and Merged Transfer Analysis' subtitle='Hops where the amount divides (split) or grows (merged inflow). Amount changes are flagged, never smoothed over.' pageKey='splits'>
      {(id) => <ApiTable title='Split and Merged Transfer Analysis' hint='' path={`/cases/${id}/paths`} pick={(d) => d.paths.flatMap((p: any, i: any) => p.hops.map((h: any, k: any) => ({ i, h, prev: k > 0 ? p.hops[k - 1].amount_minor : p.total_in_minor })).filter((r: any) => r.h.flags.length))} empty='No split or merged hops.' raw={false} limitations={undefined} cols={[
        { h: "Path", cell: (r) => `#${r.i}` },
        { h: "Hop", cell: (r) => <span className="mono">{r.h.src.slice(-6)} → {r.h.dst.slice(-6)}</span> },
        { h: "Amount", cell: (r) => <Money v={r.h.amount_minor} /> },
        { h: "Running before", cell: (r) => <Money v={r.prev} /> },
        { h: "Flag", cell: (r) => <Chip v="candidate" title={r.h.flags.join(",")} /> },
        { h: "Flags", cell: (r) => r.h.flags.join(", ") },
        { h: "When", cell: (r) => <When v={r.h.time} /> },
      ]} />}
    </ListPage>
  );
}

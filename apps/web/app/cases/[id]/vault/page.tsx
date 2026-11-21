"use client";

import ListPage, { ApiTable } from "@/components/ListPage";
import { Chip, When } from "@/components/ui";

export default function Page() {
  return (
    <ListPage title='Evidence Vault' subtitle='Original files as uploaded: SHA-256, detected kind (by content), size, parse status. Originals are immutable; every derived record cites one of these.' pageKey='vault'>
      {(id) => <ApiTable title='Evidence Vault' hint='' path={`/cases/${id}/files`} pick={(d) => d} empty='No files. Use Evidence Intake to upload.' raw={false} limitations={undefined} cols={[
        { h: "File", cell: (f) => <span className="font-medium">{f.original_name}</span> },
        { h: "SHA-256", cell: (f) => <span className="mono text-[11px]">{f.sha256}</span> },
        { h: "Kind", cell: (f) => f.detected_kind },
        { h: "Size", cell: (f) => `${(f.size_bytes / 1024).toFixed(1)} KB` },
        { h: "Status", cell: (f) => <Chip v={f.status === "parsed" ? "verified" : f.status === "failed" ? "contradicted" : "candidate"} title={f.status} /> },
        { h: "Synthetic", cell: (f) => f.is_synthetic ? <Chip v="synthetic" /> : "no" },
        { h: "Uploaded", cell: (f) => <When v={f.uploaded_at} /> },
      ]} />}
    </ListPage>
  );
}

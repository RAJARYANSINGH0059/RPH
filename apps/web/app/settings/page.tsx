"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { KV, Section } from "@/components/ui";
import { getUser, type User } from "@/lib/api";

export default function Page() {
  const [u, setU] = useState<User | null>(null);
  const [reduced, setReduced] = useState(false);
  useEffect(() => { setU(getUser()); setReduced(window.matchMedia("(prefers-reduced-motion: reduce)").matches); }, []);
  return (
    <Shell title="User Settings" subtitle="Profile and session information. Passwords and roles are managed by operators; demo visitors are anonymous and time-limited.">
      <div className="space-y-3 max-w-2xl">
        <Section title="Profile">{u && <KV rows={[["Name", u.display_name], ["Email", u.email], ["Role", u.role.replace("_", " ")], ["Session", "HttpOnly cookie on this origin; no token in browser storage"]]} />}</Section>
        <Section title="Preferences"><KV rows={[["Reduced motion", reduced ? "on (system setting) — scenes are static" : "off (system setting)"], ["Sidebar state", "remembered on this device"], ["Walkthrough", "replay from the sidebar footer"]]} /><p className="mt-2 text-xs muted">Motion follows your operating-system preference; there is nothing to configure here that would store personal data.</p></Section>
        <Section title="Sign out"><button className="btn-secondary" onClick={async () => { const { signOut } = await import("@/lib/api"); await signOut(); window.location.href = "/"; }}>Sign out of this workspace</button></Section>
      </div>
    </Shell>
  );
}

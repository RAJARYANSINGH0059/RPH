"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { I } from "@/components/icons";
import { signInStaff } from "@/lib/api";

export default function StaffLogin() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(null);
    try { await signInStaff(email, password); router.push("/overview"); } catch (err: any) { setError(err.message); setBusy(false); }
  }
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4" aria-label="Staff sign-in">
        <div className="flex items-center gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rail text-white"><I.shield /></div><div><div className="eyebrow">Protected</div><h1 className="text-xl font-bold">Staff sign-in</h1></div></div>
        <p className="text-xs muted">For analyst, supervisor and admin accounts. The public demo does not need this page.</p>
        <label className="block"><span className="label">Email</span><input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label className="block"><span className="label">Password</span><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <div role="alert" className="rounded-lg bg-danger-soft p-2.5 text-sm text-danger">{error}</div>}
        <button className="btn w-full justify-center" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        <Link href="/" className="block text-center text-xs text-accent-deep underline">Back to the public demo</Link>
      </form>
    </main>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import Shell from "@/components/Shell";
import { Toast } from "@/components/ui";
import { api, getUser, isDemo, setCaseContext } from "@/lib/api";

export default function Page() {
  const router = useRouter();
  const [form, setForm] = useState({ title: "", internal_ref: "", summary: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const demo = isDemo(getUser());
  async function create(e: FormEvent) { e.preventDefault(); setMsg(null); try { const c = await api("/cases", { method: "POST", body: JSON.stringify(form) }); setCaseContext({ id: c.id, title: c.title }); router.push(`/cases/${c.id}/upload`); } catch (err: any) { setMsg(err.message); } }
  return (
    <Shell title="Create Case" subtitle={demo ? "Demo visitors create synthetic cases only; upload synthetic or test material." : "One case per investigation. Uploaded material must be lawfully obtained and authorised for this use."} pageKey="cases">
      <form onSubmit={create} className="card max-w-2xl space-y-3" aria-label="Create case">
        <label className="block"><span className="label">Title</span><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={1} maxLength={200} /></label>
        <label className="block"><span className="label">Internal reference</span><input className="input" value={form.internal_ref} onChange={(e) => setForm({ ...form, internal_ref: e.target.value })} maxLength={100} /></label>
        <label className="block"><span className="label">Allegation summary</span><textarea className="input" value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} maxLength={5000} /></label>
        <button className="btn">Create and go to Evidence Intake</button>
        <Toast msg={msg} onClose={() => setMsg(null)} />
      </form>
    </Shell>
  );
}

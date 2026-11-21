"use client";

import { FormEvent, useState } from "react";
import ListPage from "@/components/ListPage";
import { Chip, Section, State, Table, Toast, useApi, When } from "@/components/ui";
import { api } from "@/lib/api";

export default function Page() {
  return <ListPage title="Alternative Hypotheses" subtitle="Versioned investigative hypotheses with alternatives and recorded dissent. A hypothesis cannot be marked supported without evidence; every revision keeps its history and reason." pageKey="hypotheses">{(id) => <Body id={id} />}</ListPage>;
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any[]>(`/cases/${id}/hypotheses`);
  const [form, setForm] = useState({ title: "", statement: "", kind: "other", alternatives: "" });
  const [msg, setMsg] = useState<string | null>(null);
  async function create(e: FormEvent) { e.preventDefault(); setMsg(null); try { await api(`/cases/${id}/hypotheses`, { method: "POST", body: JSON.stringify({ ...form, alternatives: form.alternatives.split("\n").filter(Boolean) }) }); setForm({ title: "", statement: "", kind: "other", alternatives: "" }); reload(); } catch (err: any) { setMsg(err.message); } }
  async function setStatus(h: any, status: string) { const reason = window.prompt("Reason for this change (recorded in the history)"); if (!reason) return; try { await api(`/cases/${id}/hypotheses/${h.id}`, { method: "POST", body: JSON.stringify({ status, reason }) }); reload(); } catch (err: any) { setMsg(err.message); } }
  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-3">
          <Toast msg={msg} onClose={() => setMsg(null)} />
          <Section title={`Hypotheses (${data.length})`}>
            <Table dense cols={["Title", "Kind", "Statement", "Alternatives", "Status", "Version", "Reviews", "Updated", ""]} rows={data.map((h: any) => [<span key="t" className="font-medium">{h.title}</span>, h.kind, <span key="s" className="text-xs">{h.statement}</span>, <ul key="a" className="list-disc pl-3 text-xs">{h.alternatives.map((x: string) => <li key={x}>{x}</li>)}</ul>, <Chip key="st" v={h.status === "supported" ? "supported" : h.status === "disputed" ? "contested" : h.status === "withdrawn" ? "contradicted" : "unresolved"} title={h.status} />, `v${h.version}`, <span key="r" className="text-xs">{h.reviews.length}{h.dissent_on_file ? " · dissent" : ""}</span>, <When key="u" v={h.updated_at} />, <select key="x" className="input !w-auto !py-0.5 text-xs" value="" onChange={(e) => e.target.value && setStatus(h, e.target.value)} aria-label="Change status"><option value="">change…</option>{["open", "under_review", "supported", "disputed", "unresolved", "withdrawn"].map((s: any) => <option key={s} value={s}>{s}</option>)}</select>])} empty="No hypotheses yet." />
          </Section>
          <Section title="New hypothesis" hint="State what you think and list the alternative explanations you have not excluded.">
            <form onSubmit={create} className="grid gap-2 text-sm md:grid-cols-2"><input className="input" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} required minLength={3} /><select className="input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value })}>{["relationship", "path", "role", "campaign", "other"].map((k: any) => <option key={k}>{k}</option>)}</select><textarea className="input" placeholder="Statement" value={form.statement} onChange={(e) => setForm({ ...form, statement: e.target.value })} /><textarea className="input" placeholder="Alternative explanations (one per line)" value={form.alternatives} onChange={(e) => setForm({ ...form, alternatives: e.target.value })} /><button className="btn md:col-span-2 justify-center">Record hypothesis</button></form>
          </Section>
        </div>
      )}
    </State>
  );
}

"use client";

/** Account typologies: the patterns an account's records show, each with its evidence and its innocent explanations.
 *
 * Nothing here is a verdict. Every triggered pattern is shown beside the ordinary explanations that fit the same
 * records, the threshold it was judged against, and what the evidence cannot see.
 */
import Link from "next/link";
import { useState } from "react";
import CasePage from "@/components/CasePage";
import { KV, Limitations, Section, State, Table, useApi } from "@/components/ui";
import { I } from "@/components/icons";

export default function TypologiesPage() {
  return (
    <CasePage
      title="Account Typologies"
      subtitle="What each account's records show, pattern by pattern, with the transactions that triggered it, the threshold it was judged against and the ordinary explanations that fit the same records. No account is labelled, and nothing is decided automatically."
      pageKey="typologies"
      wide
    >
      {(c, id) => <Body id={id} />}
    </CasePage>
  );
}

/* These badges describe what the records showed. They deliberately do not reuse the evidence-level vocabulary
   (corroborated, derived, candidate, contradicted), because an observed pattern is not corroborated evidence and a
   pattern that did not fire is not insufficient evidence; borrowing those words would overstate both. */
const LABEL: Record<string, { tone: string; short: string; text: string }> = {
  possible_mule_pattern_requires_review: { tone: "bg-saffron-soft text-warn", short: "review required", text: "Several patterns — requires review" },
  single_pattern_observed_requires_review: { tone: "bg-saffron-soft text-warn", short: "review required", text: "One pattern — requires review" },
  no_pattern_observed: { tone: "bg-panel text-ink", short: "no pattern", text: "No pattern observed" },
};

const STATUS: Record<string, { tone: string; text: string }> = {
  observed: { tone: "bg-ok-soft text-ok", text: "observed" },
  not_observed: { tone: "bg-panel text-ink", text: "not observed" },
  not_enough_history: { tone: "bg-saffron-soft text-warn", text: "not enough history" },
  not_enough_evidence: { tone: "bg-saffron-soft text-warn", text: "not enough evidence" },
};

function Typology({ t }: { t: any }) {
  const [open, setOpen] = useState(false);
  return (
    <li className={`inset p-3 ${t.triggered ? "border-saffron/50" : ""}`}>
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className={`badge ${STATUS[t.status]?.tone || "bg-panel text-ink"}`}>{STATUS[t.status]?.text || t.status.replace(/_/g, " ")}</span>
            <span className="card-title">{t.type.replace(/_/g, " ")}</span>
          </span>
          <span className="mt-1 block text-[13px] leading-relaxed muted">{t.explanation}</span>
        </span>
        <I.chevron className={`mt-1 shrink-0 transition-transform ${open ? "rotate-90" : ""}`} width={14} height={14} />
      </button>

      {open && (
        <div className="mt-3 space-y-3 border-t border-line pt-3">
          {Object.keys(t.observed_values || {}).length > 0 && (
            <div><div className="label">What was observed</div>
              <KV rows={Object.entries(t.observed_values).map(([k, v]) => [k.replace(/_/g, " "), <span key={k} className="mono text-xs">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>] as [string, React.ReactNode])} />
            </div>
          )}
          <div><div className="label">Judged against</div>
            <KV rows={Object.entries(t.thresholds || {}).filter(([k]) => k !== "why").map(([k, v]) => [k.replace(/_/g, " "), <span key={k} className="mono text-xs">{JSON.stringify(v)}</span>] as [string, React.ReactNode])} />
            {t.thresholds?.why && <p className="mt-1 text-xs muted">{t.thresholds.why}</p>}
          </div>
          {t.supporting_transactions?.length > 0 && (
            <div><div className="label">Transactions that triggered it ({t.supporting_transactions.length})</div>
              <div className="mono max-h-28 overflow-auto text-[11px] leading-relaxed">{t.supporting_transactions.join(", ")}</div>
            </div>
          )}
          {t.alternatives?.length > 0 && (
            <div><div className="label">Ordinary explanations that fit the same records</div>
              <ul className="list-disc pl-5 text-[13px] leading-relaxed">{t.alternatives.map((a: string) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
          {t.limitations?.length > 0 && (
            <div><div className="label">What this cannot see</div>
              <ul className="list-disc pl-5 text-[13px] leading-relaxed muted">{t.limitations.map((a: string) => <li key={a}>{a}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/typologies`);
  const [selected, setSelected] = useState<string | null>(null);
  const profile = data?.profiles?.find((p: any) => p.account_ref === selected) || data?.profiles?.[0];

  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="metric"><div className="label mb-0">Accounts examined</div><div className="metric-value mt-2">{data.accounts_examined}</div></div>
            <div className="metric"><div className="label mb-0">Showing a pattern</div><div className="metric-value mt-2">{data.accounts_with_a_pattern}</div><div className="mt-1 text-xs muted">each needs a human decision</div></div>
            <div className="metric"><div className="label mb-0">Rule set</div><div className="metric-value mt-2 !text-[22px]">v{data.typology_version}</div><div className="mt-1 text-xs muted">thresholds published below</div></div>
          </div>

          <div className="wb-grid">
            <Section title="Accounts" hint={data.note}>
              <Table dense cols={["Account", "Patterns", "Assessment", ""]}
                rows={data.profiles.map((p: any) => [
                  <span key="a" className="mono text-xs" title={p.account_ref}>{p.masked_account_ref}</span>,
                  <span key="n" className="num font-semibold">{p.patterns_observed}</span>,
                  <span key="l" className={`badge ${LABEL[p.label]?.tone || "bg-panel text-ink"}`} title={LABEL[p.label]?.text || p.label}>{LABEL[p.label]?.short || p.label.replace(/_/g, " ")}</span>,
                  <button key="b" className="btn-secondary !py-1" onClick={() => setSelected(p.account_ref)}>Open</button>,
                ])} />
            </Section>

            {profile && (
              <Section title={<span className="mono">{profile.masked_account_ref}</span>}
                hint={LABEL[profile.label]?.text || profile.label}
                actions={<Link href={`/cases/${id}/roles`} className="btn-secondary">Account-control review <I.arrow /></Link>}>
                <ul className="space-y-2">{profile.typologies.map((t: any) => <Typology key={t.type} t={t} />)}</ul>
                <div className="mt-3">
                  <div className="label">Evidence coverage</div>
                  <KV rows={[
                    ["Own statement in the case", profile.evidence_coverage.has_own_statement ? "yes" : "no"],
                    ["Transactions in / out", `${profile.evidence_coverage.transactions_in} / ${profile.evidence_coverage.transactions_out}`],
                    ["Rules triage (existing)", `${profile.rules_triage.label} · score ${profile.rules_triage.heuristic_score}`],
                  ]} />
                </div>
                <Limitations items={profile.limitations} />
              </Section>
            )}
          </div>
        </div>
      )}
    </State>
  );
}

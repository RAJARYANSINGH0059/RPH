"use client";

/** Infrastructure evidence, record by record.
 *
 * The other infrastructure screens read the case graph and show the entities. This one shows the records those
 * entities came from: which types were asked of each name, which answered, what the answer was, when it was read
 * and how long it may be reused — and, just as importantly, which types returned nothing and why.
 *
 * Nothing here is a current lookup dressed as history. Current observations and dated historical ones are kept in
 * separate places on the page, and a provider that is not configured says so rather than showing a blank.
 */
import Link from "next/link";
import { useState } from "react";
import CasePage from "@/components/CasePage";
import { KV, Limitations, Section, State, Table, When, useApi } from "@/components/ui";
import { I } from "@/components/icons";

export default function InfraRecordsPage() {
  return (
    <CasePage
      title="Domain, DNS and Address Records"
      subtitle="Every record type asked of each name, the answer or the reason there was none, the registration and allocation behind it, the certificates that name it, and the dated historical observations the case holds. A record read today describes today."
      pageKey="records"
      wide
    >
      {(c, id) => <Body id={id} />}
    </CasePage>
  );
}

/* Record answers are facts about a name, not evidence levels, so these badges use their own words. */
const STATUS_TONE: Record<string, string> = {
  answered: "bg-ok-soft text-ok",
  nodata: "bg-panel text-ink",
  nxdomain: "bg-saffron-soft text-warn",
  timeout: "bg-saffron-soft text-warn",
  no_nameservers: "bg-saffron-soft text-warn",
  resolver_error: "bg-saffron-soft text-warn",
};

const PROVIDER_TONE: Record<string, string> = {
  live: "bg-ok-soft text-ok",
  configured: "bg-panel text-ink",
  not_configured: "bg-panel text-ink",
  unavailable: "bg-saffron-soft text-warn",
  mock: "bg-terracotta text-white",
};

function Badge({ tone, children, title }: { tone: string; children: React.ReactNode; title?: string }) {
  return <span className={`badge ${tone}`} title={title}>{children}</span>;
}

function valueText(record: string, v: any): string {
  if (record === "A" || record === "AAAA") return v.ip;
  if (record === "CNAME") return v.target;
  if (record === "MX") return `${v.exchange}${v.preference != null ? ` (preference ${v.preference})` : ""}`;
  if (record === "NS") return v.nameserver;
  if (record === "PTR") return v.hostname;
  if (record === "TXT") return (v.strings || []).join(" · ");
  return v.raw || JSON.stringify(v);
}

function DomainCard({ d, meanings }: { d: any; meanings: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const asked: string[] = d.record_types_asked || [];
  const answered: string[] = d.record_types_answered || [];
  const notAsked: string[] = d.record_types_not_asked || [];
  return (
    <li className="inset p-3">
      <button className="flex w-full items-start justify-between gap-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className="min-w-0">
          <span className="card-title mono">{d.domain}</span>
          <span className="mt-1 flex flex-wrap items-center gap-1">
            {asked.map((rt) => (
              <Badge key={rt} tone={answered.includes(rt) ? "bg-ok-soft text-ok" : "bg-panel text-ink"}
                     title={answered.includes(rt) ? "answered" : "asked, no record of this type"}>{rt}</Badge>
            ))}
            {notAsked.length > 0 && (
              <Badge tone="bg-panel text-ink" title="These record types were never asked for, so nothing is known about them">
                {notAsked.join(" ")} not asked
              </Badge>
            )}
          </span>
        </span>
        <I.chevron className={`mt-1 shrink-0 transition-transform ${open ? "rotate-90" : ""}`} width={14} height={14} />
      </button>

      {open && (
        <div className="mt-3 space-y-3 border-t border-line pt-3">
          {Object.keys(d.records || {}).length === 0 && <p className="text-sm muted">No DNS record was read for this name.</p>}
          {Object.entries(d.records || {}).map(([record, rows]: [string, any]) => (
            <div key={record}>
              <div className="label">{record}</div>
              <Table dense cols={["Status", "Value", "TTL", "Read at", "Reusable until", "Resolver"]}
                rows={(rows as any[]).map((r) => [
                  <Badge key="s" tone={STATUS_TONE[r.status] || "bg-panel text-ink"} title={r.status_meaning || meanings[r.status]}>{(r.status || "").replace(/_/g, " ")}</Badge>,
                  <span key="v" className="mono text-xs">
                    {r.status === "answered"
                      ? (r.values || []).map((v: any, i: number) => <div key={i}>{valueText(record, v)}</div>)
                      : <span className="muted">{r.status_meaning || r.error || "—"}</span>}
                  </span>,
                  <span key="t" className="num text-xs">{r.ttl ?? "—"}</span>,
                  <When key="o" v={r.observed_at} />,
                  r.valid_until ? <When key="u" v={r.valid_until} /> : <span key="u" className="text-xs muted">—</span>,
                  <span key="r" className="mono text-[11px] muted">{r.resolver || "—"}</span>,
                ])} />
            </div>
          ))}

          {d.registration && (
            <div>
              <div className="label">Registration</div>
              <KV rows={[
                ["Registrar", d.registration.registrar_name || "not supplied"],
                ["Registrar IANA ID", d.registration.registrar_iana_id || "not supplied"],
                ["Reseller", d.registration.reseller || "not supplied by the registry"],
                ["Registered", d.registration.registered || "not supplied"],
                ["Expires", d.registration.expires || "not supplied"],
                ["Last changed", d.registration.last_changed || "not supplied"],
                ["Registrant", d.registration.redaction?.includes("withheld")
                  ? "withheld or redacted by the registry"
                  : (d.registration.registrant_name || "not supplied")],
                ["Delegation signed", String(d.registration.secure_dns ?? "not supplied")],
              ]} />
            </div>
          )}

          {(d.discovered_names || []).length > 0 && (
            <div>
              <div className="label">Names found in certificates ({d.discovered_names.length})</div>
              <p className="mb-1 text-xs muted">Certified, not observed serving. None of these has been resolved by this system.</p>
              <div className="mono max-h-24 overflow-auto text-[11px] leading-relaxed">{d.discovered_names.join(", ")}</div>
            </div>
          )}

          <KV rows={[
            ["Addresses observed", d.addresses?.length ? <span key="a" className="mono text-xs">{d.addresses.join(", ")}</span> : "none"],
            ["Nameservers", d.nameservers?.length ? <span key="n" className="mono text-xs">{d.nameservers.join(", ")}</span> : "none read"],
            ["Mail exchangers", d.mail_exchangers?.length ? <span key="m" className="mono text-xs">{d.mail_exchangers.join(", ")}</span> : "none read"],
            ["Aliases", d.aliases?.length ? <span key="c" className="mono text-xs">{d.aliases.join(", ")}</span> : "none read"],
            ["Dated historical observations", d.historical_observations || 0],
          ]} />
        </div>
      )}
    </li>
  );
}

function Body({ id }: { id: string }) {
  const { data, error, reload } = useApi<any>(`/cases/${id}/infrastructure`);

  return (
    <State loading={!data && !error} error={error} onRetry={reload}>
      {data && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <div className="metric"><div className="label mb-0">Domains</div><div className="metric-value mt-2">{data.coverage_summary.domains}</div>
              <div className="mt-1 text-xs muted">{data.coverage_summary.domains_with_registration} with registration read</div></div>
            <div className="metric"><div className="label mb-0">Addresses</div><div className="metric-value mt-2">{data.coverage_summary.addresses}</div>
              <div className="mt-1 text-xs muted">{data.coverage_summary.addresses_with_allocation} with allocation, {data.coverage_summary.addresses_with_reverse_dns} with reverse DNS</div></div>
            <div className="metric"><div className="label mb-0">Certificates</div><div className="metric-value mt-2">{data.coverage_summary.certificates}</div>
              <div className="mt-1 text-xs muted">issuance records, not proof of service</div></div>
            <div className="metric"><div className="label mb-0">Historical sources</div><div className="metric-value mt-2">{data.coverage_summary.historical_observation_sources}</div>
              <div className="mt-1 text-xs muted">dated observations, kept apart from current lookups</div></div>
          </div>

          {data.domains.length === 0 && data.addresses.length === 0 && (
            <Section title="No infrastructure evidence in this case" hint="Nothing is inferred in its absence.">
              <p className="text-sm muted">
                Upload a complaint or technical-observations file carrying a domain, URL or address, or run the
                configured connectors from the sources page. Until then this case holds no infrastructure evidence,
                which is reported as an absence rather than as a negative finding.
              </p>
              <Link href="/sources/connectors" className="btn-secondary mt-3">Connector states <I.arrow /></Link>
            </Section>
          )}

          {data.domains.length > 0 && (
            <Section title="Domains" hint="Expand a name for its records, its registration and the names certificates reveal.">
              <ul className="space-y-2">{data.domains.map((d: any) => <DomainCard key={d.domain} d={d} meanings={data.record_status_meanings} />)}</ul>
            </Section>
          )}

          {data.addresses.length > 0 && (
            <Section title="Addresses" hint="Allocation names the organisation holding the range. It is not the subscriber and not a person's location.">
              <Table cols={["Address", "Family", "Range", "Network holder", "Reverse DNS", "Classification", "Domains here"]}
                rows={data.addresses.map((a: any) => [
                  <span key="i" className="mono text-xs">{a.ip}</span>,
                  <Badge key="f" tone="bg-panel text-ink">{a.family}</Badge>,
                  <span key="p" className="mono text-xs">{a.allocation?.prefix || "—"}</span>,
                  <span key="o" className="text-xs">{a.allocation?.organisation || a.allocation?.network_name || "not read"}</span>,
                  <span key="r" className="mono text-xs">{a.reverse_dns?.hostname || "not read"}</span>,
                  <span key="c" className="text-xs">{a.classification}{a.network_classification ? ` · ${a.network_classification.classification}` : ""}</span>,
                  <span key="d" className="mono text-[11px]">{(a.domains || []).join(", ") || "—"}</span>,
                ])} />
            </Section>
          )}

          <div className="wb-grid">
            {data.certificates.length > 0 && (
              <Section title="Certificates" hint="A log entry records issuance. It does not establish that a site was serving.">
                <Table dense cols={["Identifier", "Issuer", "Common name", "Validity", "State"]}
                  rows={data.certificates.map((c: any) => [
                    <span key="k" className="mono text-[11px]">{c.certificate_key}</span>,
                    <span key="s" className="text-xs">{c.issuer_name || "—"}</span>,
                    <span key="n" className="mono text-xs">{c.common_name || "—"}</span>,
                    <span key="v" className="text-[11px]">{c.not_before || "?"} → {c.not_after || "?"}</span>,
                    <Badge key="t" tone={c.validity_state === "expired" ? "bg-saffron-soft text-warn" : "bg-panel text-ink"}>{(c.validity_state || "").replace(/_/g, " ")}</Badge>,
                  ])} />
              </Section>
            )}

            {data.historical_observations.length > 0 && (
              <Section title="Dated historical observations" hint="Kept separate from current lookups, with each provider's own sighting window.">
                <Table dense cols={["Name", "Value", "Record", "First seen", "Last seen", "Source"]}
                  rows={data.historical_observations.flatMap((h: any) => (h.records || []).map((r: any) => [
                    <span key="n" className="mono text-xs">{r.name}</span>,
                    <span key="v" className="mono text-xs">{r.value}</span>,
                    <Badge key="r" tone="bg-panel text-ink">{r.record}</Badge>,
                    <span key="f" className="text-[11px]">{r.first_seen || "—"}</span>,
                    <span key="l" className="text-[11px]">{r.last_seen || "—"}</span>,
                    <span key="s" className="text-[11px] muted">{h.provider || "supplied"}</span>,
                  ]))} />
              </Section>
            )}
          </div>

          {data.shared_certificate_names.length > 0 && (
            <Section title="Names sharing a certificate" hint="Candidate links only. Platform and CDN certificates routinely cover unrelated customers.">
              {data.shared_certificate_names.map((s: any) => (
                <div key={s.domain} className="mb-2">
                  <div className="label">{s.domain} · {s.name_count} other name(s)</div>
                  <ul className="space-y-1 text-xs">
                    {(s.names || []).slice(0, 20).map((n: any) => (
                      <li key={n.name} className="inset p-2">
                        <span className="mono">{n.name}</span>
                        <Badge tone="bg-saffron-soft text-warn">candidate</Badge>
                        <ul className="mt-1 list-disc pl-5 muted">{(n.alternatives || []).map((a: string) => <li key={a}>{a}</li>)}</ul>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </Section>
          )}

          {data.lookup_failures.length > 0 && (
            <Section title="Lookups that did not answer" hint="A failed lookup is not a negative finding; nothing is known about what it would have returned.">
              <Table dense cols={["About", "Name", "Record", "Status", "Reason"]}
                rows={data.lookup_failures.map((f: any) => [
                  <span key="a" className="text-xs">{f.about}</span>,
                  <span key="n" className="mono text-xs">{f.name || "—"}</span>,
                  <span key="r" className="text-xs">{f.record || "—"}</span>,
                  <Badge key="s" tone="bg-saffron-soft text-warn">{(f.status || "error").replace(/_/g, " ")}</Badge>,
                  <span key="e" className="text-[11px] muted">{f.status_meaning || f.error || "—"}</span>,
                ])} />
            </Section>
          )}

          <div className="wb-grid">
            <Section title="Providers" hint="A provider reports live only once a real request has succeeded in this process.">
              <Table dense cols={["Provider", "State", "What it covers"]}
                rows={Object.entries(data.connectors).map(([name, c]: [string, any]) => [
                  <span key="n" className="mono text-xs">{name}</span>,
                  <Badge key="s" tone={PROVIDER_TONE[c.status] || "bg-panel text-ink"}>{c.status.replace(/_/g, " ")}</Badge>,
                  <span key="d" className="text-[11px] muted">{c.detail}</span>,
                ])} />
            </Section>

            <Section title="What the graph gained" hint="Each record type becomes the relationship it means, and no more.">
              <KV rows={Object.entries(data.relationship_counts).map(([k, v]) => [k.replace(/_/g, " "), <span key={k} className="num font-semibold">{String(v)}</span>])} />
              {Object.keys(data.relationship_counts).length === 0 && <p className="text-sm muted">No infrastructure relationship has been built in this case.</p>}
              <Link href={`/cases/${id}/graph`} className="btn-secondary mt-3">Open the graph workbench <I.arrow /></Link>
            </Section>
          </div>

          <Limitations items={data.limitations} />
          <div className="card text-sm">{data.next}{" "}
            <Link href={`/cases/${id}/requests`} className="text-accent-deep underline">Draft an evidence request</Link>.
          </div>
        </div>
      )}
    </State>
  );
}

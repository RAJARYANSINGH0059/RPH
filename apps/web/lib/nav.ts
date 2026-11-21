/** The single navigation registry. The left sidebar, breadcrumbs, search and route labels are all generated from this file.
 * Case-scoped destinations resolve against the selected case; without a case they point to the registry with a hint.
 * `scripts/check-nav.mjs` asserts that every destination occurs exactly once. */

export type NavChild = { key: string; label: string; hint: string; path: string; caseScoped?: boolean; helpKey?: string; roles?: string[] };
export type NavGroup = { key: string; num: string; label: string; icon: string; children: NavChild[] };

const c = (key: string, label: string, hint: string, path: string, helpKey?: string): NavChild => ({ key, label, hint, path, caseScoped: true, helpKey });
const g = (key: string, label: string, hint: string, path: string, helpKey?: string): NavChild => ({ key, label, hint, path, helpKey });

export const NAV: NavGroup[] = [
  { key: "command", num: "01", label: "Command Centre", icon: "layers", children: [
    g("overview", "Overview", "Operational summary of your cases", "/overview", "overview"),
    g("activity", "Recent Activity", "Latest audited actions across your cases", "/activity"),
    g("queue", "Investigation Work Queue", "What needs a human decision next", "/queue"),
    g("alerts", "Alerts and Notifications", "Contradictions, stale observations and expiring demo sessions", "/alerts"),
  ] },
  { key: "cases", num: "02", label: "Case Operations", icon: "cases", children: [
    g("registry", "Case Registry", "All cases you may access", "/cases", "cases"),
    g("new-case", "Create Case", "Open a new investigation", "/cases/new"),
    c("workspace", "Case Workspace", "Summary, next step and files of the selected case", "", "overview"),
    c("intake", "Evidence Intake", "Upload statements, complaints, scans, QR images, JSON", "/upload", "upload"),
    c("timeline", "Case Timeline", "Dated evidence with precision badges", "/timeline", "timeline"),
  ] },
  { key: "financial", num: "03", label: "Financial Intelligence", icon: "money", children: [
    c("transactions", "Transaction Explorer", "Every parsed row with raw text and warnings", "/transactions", "transactions"),
    c("money-trail", "Money-Trail Reconstruction", "Reconstructed paths with hop classes and unresolved ends", "/money-trail"),
    c("paths", "Multi-Hop Fund Path", "Path-by-path hop detail with proof export", "/paths"),
    c("accounts", "Account and Beneficiary Analysis", "Per-account features and triage cues", "/accounts"),
    c("splits", "Split and Merged Transfer Analysis", "Where amounts divide or combine", "/splits"),
    c("claims", "Financial Recovery Reconciliation", "Claimed, traced, held, restored, unresolved", "/claims", "claims"),
    c("bounded-flow", "Bounded Fund Provenance", "Feasible min/max attribution under balance constraints", "/bounded-flow"),
  ] },
  { key: "cyber", num: "04", label: "Cyber Infrastructure Intelligence", icon: "globe", children: [
    c("domains", "Domain Intelligence", "Domains named or observed in the case", "/infra/domains"),
    c("dns", "DNS Observations", "Dated resolutions with validity windows", "/infra/dns"),
    c("pdns", "Historical DNS / Passive DNS", "What is historical, what is current-only", "/infra/passive-dns"),
    c("ip", "IP and ASN Intelligence", "Addresses, classification and multi-tenancy", "/infra/ip"),
    c("hosting", "Hosting and Registrar Intelligence", "Providers and registration observations", "/infra/hosting"),
    g("threat-intel", "Threat-Intelligence Sources", "URLhaus, ThreatFox, MISP connector states", "/sources/threat-intel"),
    c("temporal", "Temporal Infrastructure Intelligence", "Interval compatibility of observations and events", "/infra/temporal"),
  ] },
  { key: "crosscase", num: "05", label: "Cross-Case and Graph Intelligence", icon: "link", children: [
    g("correlation", "Cross-Case Correlation", "Permission-aware correlation workspace", "/crosscase", "crosscase"),
    c("proof-graph", "Cross-Case Proof Graph", "Related cases with provenance per link", "/crosscase", "crosscase"),
    c("graph", "Graph Explorer", "Linked graph workbench with inspector, timeline and table", "/graph", "graph"),
    c("entities", "Entity and Identifier Resolution", "Aliases, same-identifier bridges, similar names", "/entities"),
    g("campaign", "Fraud Campaign Evolution", "Compare case fingerprints across rotated identifiers", "/campaign"),
    c("review", "Relationship Review", "Candidate and stale links awaiting a decision", "/review"),
    c("chokepoints", "Investigative Chokepoint Map", "Structural path dependencies (not guilt)", "/chokepoints"),
    g("privacy", "Privacy-Preserving Cross-Case Matching", "Keyed-token matching (enabled only with a server key)", "/privacy"),
  ] },
  { key: "operation", num: "06", label: "Fraud Operation Intelligence", icon: "radar", children: [
    c("twin", "Fraud Operation Digital Twin", "Layered, time-aware event model of the operation", "/twin"),
    c("journey", "Victim Journey Reconstruction", "Reported experience checked against records", "/journey"),
    c("bridge", "Payment Instruction Bridge", "QR / UPI instruction compared to transactions", "/payment-bridge"),
    c("dna", "Campaign DNA", "This case's structural fingerprint", "/campaign-dna"),
    c("op-timeline", "Operation Timeline", "Chronological twin events with replay cursor", "/operation-timeline"),
    c("lifecycle", "Operation Lifecycle and Dependencies", "FATF seven-stage map with evidence states", "/lifecycle"),
    c("resilience", "Network Adaptation Simulator", "What-if removal of accounts or functions", "/resilience"),
    c("intervention", "Intervention Impact", "Hypothetical blast radius of account-level scenarios", "/intervention"),
  ] },
  { key: "reasoning", num: "07", label: "Investigative Reasoning", icon: "scale", children: [
    c("counterproof", "CounterProof", "Attribution challenges with alternatives and counter-evidence", "/counterproof"),
    c("hypotheses", "Alternative Hypotheses", "Versioned hypotheses with recorded dissent", "/hypotheses"),
    c("ivoi", "Next-Best-Evidence / IVOI", "Transparent ranking of records to request", "/ivoi"),
    c("dependencies", "Missing Evidence Dependency Map", "Questions, required records, what remains unproven", "/dependencies"),
    c("completeness", "Investigation Completeness", "Checklist with component contributions", "/completeness"),
    c("roles", "Account Involvement vs Human Attribution", "Role propositions and account-control timeline", "/roles"),
    c("independent-review", "Independent Investigation Review", "Blind review workflow for supervisors", "/independent-review"),
  ] },
  { key: "evidence", num: "08", label: "Evidence and Digital Forensics", icon: "file", children: [
    c("vault", "Evidence Vault", "Original files, hashes, parse status", "/vault"),
    c("multilingual", "Multilingual Evidence Intake", "OCR engines and language coverage", "/intake-multilingual"),
    c("ocr-queue", "OCR Review Queue", "Low-confidence extractions needing verification", "/ocr-queue"),
    c("evidence-claims", "Evidence-to-Claim Mapping", "Every report assertion with its locator", "/evidence-claims"),
    c("integrity", "Evidence Integrity and Hashes", "Integrity, authenticity, arithmetic, extraction agreement", "/integrity"),
    c("package", "Evidence Package Builder", "Proof certificates and restitution packs", "/package"),
    c("preservation", "Evidence Preservation Priority", "Clock, volatility and verified retention only", "/preservation"),
  ] },
  { key: "history", num: "09", label: "Investigation History and Coordination", icon: "timeline", children: [
    c("replay", "Investigation Replay", "What was known at a point in time", "/replay"),
    c("audit", "Audit and Activity History", "Append-only case audit log", "/audit"),
    c("handoff", "Inter-State Investigation Handoff", "Cooperation pack with supervisor gate", "/cooperation", "cooperation"),
    c("pack-history", "Cooperation Package History", "Exported packs and endorsements", "/cooperation/history"),
    c("requests", "Outstanding Evidence Requests", "Evidence acquisition drafts and lifecycle", "/requests"),
  ] },
  { key: "simulation", num: "10", label: "Simulation and Quality", icon: "factory", children: [
    g("factory", "Synthetic Case Factory", "Generate sealed-truth synthetic cases", "/factory", "factory"),
    g("adversarial", "Adversarial Case Simulator", "Difficulty and decoy profiles", "/factory/adversarial"),
    c("lab", "Counterfactual Investigation Lab", "Stress-test findings on an analytical copy", "/lab"),
    g("benchmark", "Benchmark Centre", "Baselines, seeds and methodology", "/benchmark"),
    g("results", "Evaluation Results", "Measured synthetic metrics", "/benchmark/results"),
    g("models", "Model and Rules Performance", "Triage model card and rule compiler", "/benchmark/models"),
    c("challenge", "Blind Investigation Challenge", "Submit conclusions, then reveal sealed truth", "/challenge"),
  ] },
  { key: "output", num: "11", label: "Results and Reports", icon: "report", children: [
    c("case-results", "Investigation Results", "Findings, paths, uncertainty and limitations", "/results"),
    c("reports", "Reports", "PDF / JSON / CSV exports", "/reports", "reports"),
    c("findings", "Evidence-Linked Findings", "Relationship table with sources", "/findings"),
    c("export", "Export Centre", "All downloadable artefacts in one place", "/export"),
  ] },
  { key: "data", num: "12", label: "Data Sources and Settings", icon: "sources", children: [
    g("sources", "Data Source Registry", "Where evidence can come from and its status", "/sources", "sources"),
    g("connectors", "Connectors and Integrations", "RDAP, DNS, URLhaus, ThreatFox, MISP", "/sources/connectors"),
    g("health", "Integration Health", "Live health checks (supervisor)", "/sources/health"),
    g("settings", "User Settings", "Profile, session and preferences", "/settings"),
    g("app-audit", "Application Audit Log", "Your audited actions across cases", "/audit-log"),
  ] },
];

export const UTILITY: NavChild[] = [
  g("help", "How to Use PS05-X", "Guide to every module", "/guide", "guide"),
  g("walkthrough", "Guided Walkthrough", "Fifteen steps through a real investigation", "/guide/walkthrough"),
  g("shortcuts", "Keyboard Shortcuts / Help", "Keys and accessibility", "/guide/shortcuts"),
];

export function hrefFor(child: NavChild, caseId: string | null): string {
  if (!child.caseScoped) return child.path;
  if (!caseId) return `/cases?need=${encodeURIComponent(child.key)}`;
  return `/cases/${caseId}${child.path}`;
}

export function allChildren(): { group: NavGroup | null; child: NavChild }[] {
  return [...NAV.flatMap((gr) => gr.children.map((ch) => ({ group: gr, child: ch }))), ...UTILITY.map((ch) => ({ group: null, child: ch }))];
}

/** Resolve the active child for a pathname (longest matching path wins). */
export function matchRoute(pathname: string): { group: NavGroup | null; child: NavChild; caseId: string | null } | null {
  const m = pathname.match(/^\/cases\/([0-9a-f-]{36})(\/.*)?$/);
  const caseId = m ? m[1] : null;
  const rest = m ? (m[2] || "") : pathname;
  let best: { group: NavGroup | null; child: NavChild } | null = null;
  for (const item of allChildren()) {
    const p = item.child.caseScoped ? item.child.path : item.child.path;
    if (item.child.caseScoped !== !!m) continue;
    if (rest === p || (p && rest.startsWith(p + "/") && !(item.child.caseScoped && p === ""))) {
      if (!best || p.length > (best.child.path.length)) best = item;
    }
  }
  return best ? { ...best, caseId } : null;
}

/** Unique destinations check (used by scripts/check-nav.mjs and the dev-time assertion). */
export function duplicateDestinations(caseId = "00000000-0000-0000-0000-000000000000"): string[] {
  const seen = new Map<string, number>();
  for (const { child } of allChildren()) {
    const h = hrefFor(child, caseId);
    seen.set(h, (seen.get(h) || 0) + 1);
  }
  return [...seen.entries()].filter(([, n]) => n > 1).map(([h]) => h);
}

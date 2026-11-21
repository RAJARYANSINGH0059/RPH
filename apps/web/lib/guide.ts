/** Plain-language guidance shown in the Help drawer and on the Guide page. */
export type GuideSection = { title: string; purpose: string; inputs: string[]; outputs: string[]; tips: string[] };

export const GUIDE: Record<string, GuideSection> = {
  cases: {
    title: "Cases",
    purpose: "A case is one investigation. Everything you upload, every graph and every report belongs to a case. Start here.",
    inputs: ["A title (required), an internal reference and a short allegation summary for a real case", "Or nothing at all: generate a synthetic demo case in one click"],
    outputs: ["A case card with status, data type (synthetic or uploaded) and last activity", "Links to the case overview and its tools"],
    tips: ["New here? Use “Try a synthetic investigation”. It needs no files and no credentials.", "Cases you created are private to you; admins see all cases."],
  },
  factory: {
    title: "Synthetic Case Factory",
    purpose: "Creates a complete, fictional investigation with hidden ground truth so you can learn the tool and test it safely.",
    inputs: ["Scenario (phishing-to-mule, fake customer care, loan/job fee, investment, QR marketplace, multi-victim)", "Difficulty: clean → messy → high noise → adversarial (adds duplicates, ambiguous dates, OCR noise, decoy domains, stale DNS)", "Size (small/medium/large) and a seed number"],
    outputs: ["Bank statements (CSV/XLSX in different column layouts), a complaint PDF, a technical-observations JSON and a noisy screenshot", "The files are imported through the same upload pipeline as real files; the answer key is sealed away from the app"],
    tips: ["Same seed + same settings always produce identical files. Change the seed for a fresh case.", "Start with “messy / small / seed 42” for the demo."],
  },
  overview: {
    title: "Case overview",
    purpose: "Your dashboard for one case: what has been ingested, what needs attention, and the next recommended step.",
    inputs: ["Nothing to enter; it summarises the case"],
    outputs: ["Counts of files, transactions, indicators, relationships, warnings and findings awaiting review", "The investigation steps bar showing where you are"],
    tips: ["Follow the steps left to right: Upload → Check parsing → Fund flow → Graph → Review → Report."],
  },
  upload: {
    title: "Upload evidence",
    purpose: "Bring files into the case. Each file is hashed, type-checked by content and parsed with exact source positions.",
    inputs: ["Bank statements: CSV or XLSX (any column names; you can correct the mapping)", "Complaints and notes: PDF, DOCX, TXT", "Technical observations: JSON with DNS / hosting / URL / RDAP entries", "Screenshots: PNG/JPG (text is read only if an OCR engine is installed)"],
    outputs: ["A per-file preview: detected columns, first rows, warnings (ambiguous dates, duplicates, balance mismatch, unmapped columns)", "Transactions, indicators and observations added to the case"],
    tips: ["If a statement column was mapped wrongly, pick the right header in the mapping editor and press “Re-parse”. The original file is never changed.", "Warnings are information, not errors: the file is still usable."],
  },
  transactions: {
    title: "Transactions and fund flow",
    purpose: "See every parsed transaction with its raw text, and the money paths the system reconstructed across accounts.",
    inputs: ["Nothing to enter; use the filter box to search"],
    outputs: ["Reconstructed multi-hop paths (victim → first account → next account), time-ordered", "Balance reconciliation per statement", "Triage signals per account from transparent rules, plus an optional ML cue"],
    tips: ["Rows highlighted in amber are duplicate candidates; both copies are kept on purpose.", "“ambiguous” means the date could be dd/mm or mm/dd; the system never guesses silently.", "A triage signal is a reason to look, never a conclusion."],
  },
  graph: {
    title: "Investigation graph",
    purpose: "Entities (accounts, VPAs, domains, IPs, hosts) and the relationships between them, each labelled by how strong its evidence is.",
    inputs: ["Pick a focus preset: Money trail, Infrastructure or Full picture", "Search a name or number to centre on it", "Tick/untick entity types and evidence levels"],
    outputs: ["Lanes layout: sources on the left, accounts, identifiers, web, infrastructure on the right", "Click an edge → evidence panel: source file and cell/page, times, method, limitations, counter-evidence, review buttons", "Click a node → Entity 360"],
    tips: ["Solid lines are observed or derived facts; dashed lines are candidates or stale observations that need review.", "A shared IP between two domains appears as a dashed candidate with counter-evidence. The tool will not call them commonly owned.", "Use “Evidence-backed only” to hide every hypothesis at once."],
  },
  timeline: {
    title: "Timeline",
    purpose: "All dated evidence on one axis: transactions, DNS and hosting observations, URL mentions and registrations.",
    inputs: ["Toggle event families on/off"],
    outputs: ["Chronological list with UTC time, the raw source string and a precision badge when the time is uncertain"],
    tips: ["Items without a usable time are listed last, never dropped."],
  },
  reports: {
    title: "Reports and export",
    purpose: "Produce a source-backed report for review: PDF for reading, JSON for audit, CSV for spreadsheets.",
    inputs: ["Nothing to enter"],
    outputs: ["PDF with sources and hashes, parsing warnings, transaction trail, fund paths, infrastructure observations with times, relationship table with locators, counter-evidence, unresolved items and the disclaimer"],
    tips: ["The report separates observed facts, derived analysis, candidates and unresolved issues.", "It is an investigative aid; it never claims legal admissibility."],
  },
  crosscase: {
    title: "Cross-case correlation",
    purpose: "Finds exact, source-backed bridges between cases you are authorised to access: the same account, VPA, phone, email, reference, URL or domain; the same transaction reference and amount; shared infrastructure as a candidate only.",
    inputs: ["Two to twelve cases you can open (a case you cannot access is never searched or revealed)"],
    outputs: ["Links classed corroborated / exact / derived / candidate / stale with the source case, file hash, locator, method and counter-evidence", "A ‘not asserted’ list of similar names that were deliberately not linked", "A fingerprint so the same input and algorithm version give the same result"],
    tips: ["Shared hosting never becomes common ownership here either.", "Entities are never merged across cases; open each case to see the original records."],
  },
  claims: {
    title: "Victim claims & restitution readiness",
    purpose: "Prepares a reconciliation that a Money Restoration Module reviewer can check: what each victim claims, which transactions trace it, what is documented as held or restored, and what remains unresolved or competing.",
    inputs: ["Claims entered from complaint acknowledgements / FIR references", "Links from each claim to source transactions", "Hold or restoration records that cite a source document already in the case (statement rows are refused)"],
    outputs: ["Per-claim claimed / traced / unresolved amounts", "Per-account traced inflow vs documented held, with oversubscription flags", "Competing and duplicate claim warnings", "A PDF/JSON readiness pack with a manual review checklist"],
    tips: ["The tool never allocates funds or decides entitlement.", "Approval states: draft → investigator checked → supervisor checked → export ready.", "Simulated holds from synthetic cases are labelled as simulated."],
  },
  cooperation: {
    title: "Cross-state cooperation pack",
    purpose: "Assembles the fields and attachments the cooperation request process asks for, validates them, and exports a ZIP for manual submission.",
    inputs: ["Officer, jurisdiction, FIR and supervising-officer details", "FIR gist and assistance details (10–500 characters each)", "The authorised FIR PDF and a supervisor-signed endorsement, plus selected evidence"],
    outputs: ["A validation checklist that names missing fields", "Supervisor endorsement gate before export", "ZIP with manifest.json, a summary PDF, attachments with SHA-256 and the money/infrastructure trace"],
    tips: ["Nothing is submitted automatically; there is no portal login or CAPTCHA handling.", "Any edit after endorsement returns the pack to draft."],
  },
  sources: {
    title: "Data sources",
    purpose: "Shows which external look-ups (RDAP, DNS, URLhaus, ThreatFox, MISP) are configured, and their real status.",
    inputs: ["Operators configure keys through environment variables; nothing is entered here"],
    outputs: ["Status per connector: not configured, configured, unavailable, mock or live"],
    tips: ["“Live” appears only after a real authenticated request succeeded. Synthetic mode needs no connector."],
  },

  twin: { title: "Fraud Operation Digital Twin", purpose: "A layered, time-aware reconstruction of the suspected operation built only from persisted evidence, decoded instructions, observations and audited actions.", inputs: ["Nothing to enter; toggle layers, filter by evidence class, move the time cursor"], outputs: ["Events with evidence class (observed / reported / extracted / derived / candidate / stale / unresolved) and their locators", "Links such as PAYMENT_INSTRUCTION_MATCHES_TRANSACTION; REPORTED_BEFORE is chronology, not causation", "Supported facts and unresolved questions"], tips: ["Manual events you add are always `reported`.", "Use the replay cursor to see what was known at a point in time."] },
  bridge: { title: "Payment Instruction Bridge", purpose: "Decode a QR image or upi:// link and compare it field by field with recorded transactions.", inputs: ["A QR PNG/JPEG, or the raw upi:// text / payment link"], outputs: ["Match level: exact reference+identifier, exact identifier+amount, corroborated multi-field, candidate, conflicted, no match, unresolved", "Matched, missing and conflicting fields per candidate transaction"], tips: ["A match links the artefact to a payment record; it never identifies who controls the payee account.", "A one-character VPA difference is a different identifier."] },
  bounded: { title: "Bounded Fund Provenance", purpose: "Feasible minimum and maximum victim-origin amounts on each onward transfer, computed with a linear programme over the account's balance history.", inputs: ["Pick a reconstructed path; optionally run a FIFO/LIFO scenario (labelled as an assumption)"], outputs: ["[min, max] per hop, witnesses, invariant facts, inconsistencies, missing statements that would narrow the interval"], tips: ["Money is fungible after commingling: a range is the honest answer.", "UNDETERMINED means a statement is missing, not that nothing moved."] },
  counterproof: { title: "CounterProof / Evidence Adversary", purpose: "Adversarial testing of every material relationship: alternatives, counter-evidence, temporal compatibility and source reliability kept separate.", inputs: ["Pick a relationship; accept, reject, retain as candidate, add a competing hypothesis or record dissent"], outputs: ["Attribution Challenge Report with a state: supported, corroborated, contested, candidate, contradicted, unresolved, stale"], tips: ["Accepting a candidate needs a supervisor.", "Dissent is preserved as a hypothesis; nothing is rewritten."] },
  lifecycle: { title: "Operation Lifecycle & Dependencies", purpose: "FATF's seven-stage scam-operation lifecycle (5 Nov 2026 report) applied to this case's evidence, with functional dependencies.", inputs: ["Nothing to enter; request human review of candidate high-leverage dependencies"], outputs: ["Stage states: directly observed, corroborated, derived, candidate, contradicted, NOT SUPPLIED, partial, unassessed", "Dependency cards with benign alternatives and known unknowns"], tips: ["NOT SUPPLIED means no evidence was supplied, never that the stage did not happen.", "No bank, telecom, CDN or provider is labelled a criminal enabler for appearing here."] },
  roles: { title: "Account Involvement vs Human Attribution", purpose: "Keeps facts about an account apart from propositions about the human: holder, operator, controller, knowledge, intent, deception, compromise.", inputs: ["Evidence references for or against each proposition; role claims on the control timeline"], outputs: ["Proposition matrix, status (UNASSESSED → HUMAN_REVIEWED), open questions, swimlanes per role dimension"], tips: ["Knowing participation cannot be marked supported without evidence.", "Protected attributes are never inputs."] },
  ivoi: { title: "Next-Best-Evidence / IVOI", purpose: "Ranks records to request by how many open questions they could resolve, with a transparent component breakdown.", inputs: ["Nothing to enter; create a draft request from a suggestion"], outputs: ["Ranked list, catalogue record type, custodian type, scope, what it could and could not establish"], tips: ["The score is not a probability of success.", "Retention deadlines appear only with a verified policy source."] },
  requests: { title: "Evidence Acquisition", purpose: "Draft, review, authorise and track evidence requests. The system never sends anything.", inputs: ["Title, record type, custodian type, target, period, legal basis and requesting officer (validated by a supervisor)"], outputs: ["Lifecycle identified → draft → under review → authorised → sent (recorded manually) → received → reviewed → closed", "Draft PDF with fields marked for authorised completion"], tips: ["A draft does not mean a request was sent.", "Partial responses keep the remainder unresolved."] },
  lab: { title: "Counterfactual Investigation Lab", purpose: "Perturbs an analytical copy of the case (shared hosting, stale DNS, OCR substitution, missing statement…) and reports what survives.", inputs: ["A perturbation profile and a seed"], outputs: ["STABLE / FRAGILE / CHANGED / UNRESOLVED with the paths that stayed, weakened, disappeared or appeared"], tips: ["Source files and database records are never modified."] },
  resilience: { title: "Network Adaptation Simulator", purpose: "What-if removal of accounts or functions on a copy of the observed money network.", inputs: ["Accounts to remove, a function (collection / layering / exit), optional hypothetical substitutions"], outputs: ["Paths disconnected, observed alternatives, hypothetical-only routes, sensitivity to uncertain edges"], tips: ["Centrality is not culpability.", "Hypothetical replacement nodes are labelled and never evidence."] },
  intervention: { title: "Intervention Impact", purpose: "Hypothetical comparison of account-level scenarios with observed, bounded and unknown amounts kept apart.", inputs: ["Acknowledge that this is a simulation to see scenarios"], outputs: ["Ledger (balance, investigated inflows, other inflows, onward, withdrawals), unrelated activity, four scenarios"], tips: ["Nothing here freezes, liens or notifies anything.", "Unobserved customers are unknown, not zero."] },
  challenge: { title: "Blind Investigation Challenge", purpose: "Record your conclusions, lock them, then reveal the sealed truth and your measured scores.", inputs: ["Accounts you consider mule-pattern; domains you would assert share an operator"], outputs: ["Scores: recall, precision, innocent accounts flagged, decoy rejection — labelled synthetic evaluation"], tips: ["The reveal is unavailable until you submit."] },
};

export const WALKTHROUGH: { title: string; what: string; href: (caseId: string | null) => string }[] = [
  { title: "Enter the synthetic workspace", what: "One click, no credentials. Everything is fictional and isolated.", href: () => "/overview" },
  { title: "Generate Operation Desert Mirage", what: "Synthetic Case Factory → desert_mirage. Ground truth is sealed away.", href: () => "/factory" },
  { title: "Check what was parsed", what: "Evidence Intake shows hashes, parser warnings, OCR confidence and QR decodes.", href: (c) => (c ? `/cases/${c}/upload` : "/cases") },
  { title: "Follow the money", what: "Transaction Explorer and Money-Trail Reconstruction: hops, splits, unresolved ends.", href: (c) => (c ? `/cases/${c}/money-trail` : "/cases") },
  { title: "Inspect cyber infrastructure", what: "Domains, DNS observations and what is current-only versus historical.", href: (c) => (c ? `/cases/${c}/infra/domains` : "/cases") },
  { title: "Open the Digital Twin", what: "Layered, time-aware event model with an observed / reported / derived legend.", href: (c) => (c ? `/cases/${c}/twin` : "/cases") },
  { title: "Bridge a payment instruction", what: "Decode the QR / UPI link and compare it field by field with recorded transactions.", href: (c) => (c ? `/cases/${c}/payment-bridge` : "/cases") },
  { title: "Bound the fund attribution", what: "Minimum/maximum victim-origin amounts per hop under balance constraints; no false precision.", href: (c) => (c ? `/cases/${c}/bounded-flow` : "/cases") },
  { title: "Challenge a relationship", what: "CounterProof lists alternatives and counter-evidence; shared hosting stays a candidate.", href: (c) => (c ? `/cases/${c}/counterproof` : "/cases") },
  { title: "Map the operation lifecycle", what: "FATF-attributed seven stages with NOT SUPPLIED where evidence is absent.", href: (c) => (c ? `/cases/${c}/lifecycle` : "/cases") },
  { title: "Separate account from person", what: "Role propositions and the account-control timeline (holder ≠ controller).", href: (c) => (c ? `/cases/${c}/roles` : "/cases") },
  { title: "See what is missing and what to request", what: "Dependency map, IVOI ranking and evidence request drafts (never sent).", href: (c) => (c ? `/cases/${c}/ivoi` : "/cases") },
  { title: "Stress-test the conclusion", what: "Counterfactual Lab and Network Adaptation Simulator on an analytical copy.", href: (c) => (c ? `/cases/${c}/lab` : "/cases") },
  { title: "Reconcile and review", what: "Recovery reconciliation, completeness checklist and independent review with dissent.", href: (c) => (c ? `/cases/${c}/claims` : "/cases") },
  { title: "Replay, prove and export", what: "Investigation replay, proof certificate verified offline, reports and packs.", href: (c) => (c ? `/cases/${c}/export` : "/cases") },
];

export const STEPS = [
  { key: "upload", label: "Upload", href: (id: string) => `/cases/${id}/upload`, hint: "Add statements, complaints, observations" },
  { key: "parse", label: "Check parsing", href: (id: string) => `/cases/${id}/upload`, hint: "Fix column mapping, read warnings" },
  { key: "flow", label: "Fund flow", href: (id: string) => `/cases/${id}/transactions`, hint: "Follow the money across accounts" },
  { key: "graph", label: "Graph", href: (id: string) => `/cases/${id}/graph`, hint: "Inspect relationships and evidence" },
  { key: "review", label: "Review", href: (id: string) => `/cases/${id}/graph`, hint: "Support, reject or ask for more evidence" },
  { key: "report", label: "Report", href: (id: string) => `/cases/${id}/reports`, hint: "Export PDF / JSON / CSV" },
];

export const EVIDENCE_LEVEL_HELP: Record<string, string> = {
  directly_observed: "A source record states it directly (e.g. a statement row).",
  corroborated: "Two independent sources agree (e.g. both statements show the same transfer).",
  derived: "Computed deterministically from records (e.g. a VPA matched to an account by reference + amount).",
  candidate: "A possible link that needs a human decision; often shared infrastructure or similar names.",
  contradicted: "Counter-evidence weakens it.",
  stale: "Observed outside the time window of the events.",
  insufficient: "Not enough evidence either way.",
};

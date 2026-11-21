# Role-sensitive review safeguards

Implementation: `apps/api/app/services/roles.py`; API `GET/POST /api/cases/{id}/roles/{account}`, `/decision`, `/control-timeline`; UI *Investigative Reasoning → Account Involvement vs Human Attribution*.

## Why

An account receiving or moving money is a fact about records. Who operated it, what they knew and whether they were deceived, recruited, coerced or compromised are separate questions. Rajasthan's reported scale of suspected mule accounts and documented coerced-labour cases make this separation operationally important.

## Propositions (not mutually exclusive, none a legal finding)

P1 account received the transaction(s) · P2 a named individual is recorded as holder · P3 the named individual operated the account at the relevant time · P4 another person controlled/accessed it · P5 the individual understood the purpose · P6 the individual knowingly assisted · P7 indicators of deception/recruitment/coercion/trafficking (trained human review only) · P8 account or identity may have been compromised · P9 information insufficient or conflicting.

Statuses per proposition: `unassessed`, `supported`, `contradicts`, `conflicting`, `insufficient`. Review status: `UNASSESSED → REVIEW_REQUIRED / CONFLICTING_EVIDENCE / INDETERMINATE → HUMAN_REVIEWED` (decision by supervisor/admin with rationale).

## Guardrails enforced in code

- P1 is auto-populated from statement credits; every other proposition starts `unassessed`.
- P3–P8 cannot be marked `supported` without at least one supporting evidence item from the case ("account presence alone is not evidence").
- Notes that infer from poverty, caste, religion, ethnicity, sex, gender, age, disability, nationality, geography, a model score or centrality are rejected.
- A conflicting proposition sets `CONFLICTING_EVIDENCE`; it cannot be hidden by later edits (history is appended).
- No guilt/victim/trafficking score exists; the rules and ML triage are account-level cues shown separately.
- Every change is audited (`role_review.created/updated/decided`).

## Account-control timeline

Role dimensions: registered holder, KYC supplier, possessor of card/passbook/device, credential/device controller, transaction initiator, recruiter/intermediary, cash-out actor, beneficiary, suspected organiser/controller, unknown/disputed. Claim states: direct, corroborated, derived, alleged, unresolved, contradicted. Direct/corroborated claims require a source evidence item; alleged claims are `reported`. Debit rows appear in the initiator lane as "UNKNOWN (record shows the debit; the initiator is not recorded)". The timeline reports whether holder and controller differ and lists contradictions and empty dimensions.

## Prohibited

Automatic labels of criminal, innocent, trafficked or coerced; protected attributes as inputs; inference of trafficking from a job advert, travel or account activity alone.

## Tests

`test_role_review_guardrails`, `test_control_timeline_separates_holder_and_controller` in `apps/api/tests/test_lifecycle_roles_requests.py`; `knowing_participation_auto_asserted` is measured as 0 in benchmark v2.

# Operation lifecycle and dependency model

Implementation: `apps/api/app/services/lifecycle.py`; API `GET /api/cases/{id}/lifecycle`; UI *Fraud Operation Intelligence → Operation Lifecycle and Dependencies*.

## Attribution

The stage taxonomy is the seven-stage scam-operation lifecycle published by the FATF in *Combating End-to-End Illicit Financial Flows Linked to Scam Compounds* (5 November 2026), grouped upstream / payment window / downstream, together with its functional-dependency concept (54 dependencies, 14 potentially critical depending on the operation). PS05-X applies the framework to case evidence; it did not invent it. Stage labels paraphrase the report's grouping; the attribution block is returned with every response and shown in the UI and report metadata.

## Stages

| Key | Label | Group | Evidence that can support it in PS05-X |
|---|---|---|---|
| S1 | Establishing the operation | upstream | RDAP registration, hosting/DNS observations (dated) |
| S2 | Recruiting workers | upstream | Recruitment / job / travel terms in supplied documents — always CANDIDATE, human review only |
| S3 | Acquiring victims | upstream | Complaint narrative of first contact, URLs/domains named |
| S4 | Executing the scam | payment window | Complaint narrative of the deception, decoded payment instructions |
| S5 | Collecting payments | downstream | Victim-origin transfers (first hop of reconstructed paths) |
| S6 | Moving and laundering funds | downstream | Onward hops; unresolved ends name the missing statement |
| S7 | Cashing out and reinvesting | downstream | Cash withdrawals / exits; PARTIAL when paths end unresolved |

## Stage states

`DIRECTLY_OBSERVED`, `CORROBORATED`, `DERIVED`, `CANDIDATE`, `CONTRADICTED`, `NOT_SUPPLIED`, `PARTIAL`, `NOT_APPLICABLE`, `UNASSESSED`. A stage with no supplied evidence is `NOT_SUPPLIED`, never "did not happen". Each stage lists its evidence items (with locators and hashes), missing evidence and unresolved hypotheses.

## Dependency objects

Classes: recruitment/labour sourcing; victim acquisition/advertising; digital platform/domain/hosting; telecom/connectivity; payment collection; mule/intermediary accounts; financial institutions/payment intermediaries; specialist service providers; virtual assets/VASP/OTC; laundering/cash-out; corporate/legal/beneficial ownership; physical logistics; reinvestment/asset holding.

Each dependency stores role, stages, provider/account, status (`OBSERVED_USE`, `CANDIDATE_DEPENDENCY`, `CORROBORATED_DEPENDENCY`), repeat use, benign alternative, replaceability (usually unknown), known unknowns, review status and the authorised next step (always a draft request, never an action).

## Leverage

`IMPORTANCE_UNASSESSED` by default. `POTENTIALLY_HIGH_LEVERAGE_REQUIRES_REVIEW` is set only for a payment-collection account that receives corroborated first-hop transfers from at least two independent victim paths, and the reason is stated. Graph degree, repeated appearance, or shared CDN/hosting never produce it. Banks, telecoms, cloud/CDN providers, registrars and payment intermediaries are never labelled criminal dependencies for appearing in evidence.

## Tests

`apps/api/tests/test_lifecycle_roles_requests.py::test_lifecycle_attribution_states_and_no_criminal_providers`.

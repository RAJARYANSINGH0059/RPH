# Rajasthan operational fit

How PS05-X complements the systems Rajasthan Police and India already operate, and which local facts shaped the design. Figures are the government or press-reported numbers in the research register; they are context, not claims about this product.

## Existing ecosystem PS05-X must not imitate

| Existing system | What it already does | PS05-X relationship |
|---|---|---|
| CFCFRMS 2.0 / NCRP / 1930 | Complaint intake, bank coordination, holds and restoration (₹11,158 crore saved across 32.8 lakh complaints by 30 June 2026, per MHA/PIB) | Prepares source-linked evidence, reconciliation and cooperation packets; never a portal, never a hold |
| I4C Suspect Registry / MuleHunter.AI | Bank-side suspect identifiers and mule-account intelligence (32.08 lakh layer-1 mule accounts shared) | Consumes nothing live; triage is a cue, never a registry |
| Banks / payment intermediaries | Execute holds, releases, KYC | Drafts requests with scope and identifiers; an authorised officer validates and dispatches |
| Telecom / ISP / registrar | Subscriber and hosting records | Draft requests with narrow windows; a number or IP alone identifies nobody |
| MISP / OpenCTI / STIX | CTI exchange | Interoperate where appropriate; no general CTI platform rebuilt |

## Local facts that drove design choices

- **Scale of suspected mule accounts.** Rajasthan Police reported 82,407 mule accounts identified between 1 January and 12 July 2026 across 723 cases, with police commentary that some holders may have handed over details through naivety or financial pressure while others knowingly participated. Hence the Account Role & Context Review: nine propositions kept apart, no guilt score, protected attributes never used, human review mandatory.
- **Coerced scam-centre labour.** CBI/NIA 2026 cases describe Indians recruited on false job offers and forced into cyber-fraud abroad, with Rajasthan-linked cases. Hence the account-control timeline (holder, possessor, controller, initiator, recruiter, cash-out actor, beneficiary may differ) and recruitment indicators treated as candidates for trained review only.
- **National coordination exists.** Rapid response and restoration run through CFCFRMS and banks. Hence the Evidence Acquisition engine produces drafts with lifecycle tracking and a manual-dispatch record; nothing is transmitted.
- **Evidence arrives incomplete.** Investigators typically receive victim statements and perhaps one intermediary statement. Hence coverage states (NOT_SUPPLIED vs OBSERVED_ZERO), bounded attribution that goes UNDETERMINED beyond the last statement, and IVOI ranking of which record to ask for next.

## Districts and language

The synthetic Operation Desert Mirage uses fictional complaints from Jaipur, Jodhpur and Udaipur to exercise multi-district correlation. Hindi OCR is supported through the Tesseract `hin` trained data in the Docker image; the free-tier API runs with OCR off because the runtime exceeded its memory, which is documented rather than hidden.

## Handoff

A cooperation pack (manifest, hashes, summary PDF, attachments, supervisor endorsement) is a manually transferable bundle for inter-state or inter-agency use. It is never transmitted by the system and does not assert any legal authority.

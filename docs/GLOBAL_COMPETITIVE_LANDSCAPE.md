# Global competitive landscape and overlap analysis

Source register and overlap analysis for PS05-X, condensed from the supplied research cut-off of 21 November 2026. This is a structured review of representative public systems, not a survey of every vendor, repository or team. Vendor pages are evidence of advertised features, not independently verified performance. Nothing here is a claim of global uniqueness.

## 1. What is already common

| Capability | Status in the market | PS05-X position |
|---|---|---|
| Money-trail graph, bank/UPI parsing, QR decoding | Common (MuleMap, i2, Quantexa, NICE Actimize, many hackathon teams) | Baseline; correctness and provenance improved, not claimed as novel |
| Mule-account scoring | Common and bank-operated (RBI / I4C MuleHunter.AI, Suspect Registry) | Optional triage cue only; never a guilt finding |
| IP / DNS / hosting pivots | Common OSINT tooling (Maltego, OpenCTI, MISP) | Required; time-aware, source-labelled, current-only vs historical kept apart |
| Cross-case correlation, evidence packages, reports | Advertised by direct competitors | Baseline; permission-aware with locators, hashes and counter-evidence |
| Synthetic AML data | Established (IBM AMLSim, PaySim, Elliptic-related work) | Used for reproducible sealed-truth evaluation, not as novelty |
| CTI sharing / privacy-enhanced analytics | Established (MISP, OpenCTI, STIX/TAXII, BIS Project Aurora) | Interoperate; keyed-token matching labelled as equality-leaking, not anonymisation |

## 2. Where PS05-X concentrates its effort

The defensible combination this build implements and tests: proof-carrying money trails verified offline, bounded fund attribution under balance constraints, an evidence adversary that keeps supported/contested/candidate states apart, a FATF-attributed lifecycle and dependency map, role-sensitive account review with an account-control timeline, evidence coverage that never treats missing records as zero, evidence-acquisition drafting that never transmits, and a blind challenge scored against sealed truth. Each is an engineering hypothesis measured on synthetic cases (see `BENCHMARK_V2.md`).

## 3. Source register (representative)

**Official challenge and Indian systems**: Rajasthan Police Cyber Security Hackathon (https://rajasthanpolicehackathon.in/); MHA/PIB CFCFRMS 2.0 (https://www.pib.gov.in/PressReleasePage.aspx?PRID=2290377, https://www.pib.gov.in/PressReleasePage.aspx?PRID=2297626); I4C (https://i4c.mha.gov.in/); RBI Annual Report 2025–26; CBI (https://cbi.gov.in/); NIA (https://nia.gov.in/); Rajasthan mule-account reporting, Indian Express 20 Aug 2026; Rajasthan-linked cyber-slavery case reporting, Indian Express 5 Feb 2026; NIA Myanmar trafficking/cyber-fraud chargesheet 18 Feb 2026.

**International organisations**: FATF, *Combating End-to-End Illicit Financial Flows Linked to Scam Compounds* (5 Nov 2026) — seven-stage lifecycle, 54 functional dependencies, 14 potentially critical (https://www.fatf-gafi.org/en/publications/Methodsandtrends/combating-illicit-financial-flows-linked-to-scam-compounds.html); INTERPOL Global Financial Fraud Threat Assessment 2026 and Operation First Light 2026; UNODC; OSCE; Europol; BIS Project Aurora.

**National response systems**: Indonesia OJK IASC; Singapore Police Anti-Scam Centre (joint operation 11 Nov 2026); Malaysia NSRC / National Fraud Portal; Hong Kong ADCC; Brazil Pix MED; Australia National Anti-Scam Centre; UK National Fraud Portal.

**Commercial products** (advertised features only): MuleMap, NICE Actimize, Quantexa, i2 Analyst's Notebook, Maltego, TRM Labs, Chainalysis.

**Open source / data**: IBM AMLSim, PaySim mirror, Elliptic AML triage implementation, OpenCTI, MISP, Google Timesketch, Autopsy/Sleuth Kit, GraphSense, TheHive, STIX/TAXII.

**Comparable challenge**: Bihar Police / C-DAC Cyber Hackathon 2026 PS-01 (mule-account detection and fund-flow investigation; multiple finalist teams in that class).

## 4. Claims policy

Make: "every material money-trail derivation reproduces from a source-linked manifest"; "observed-zero is separated from not-supplied"; "attribution is a feasible range under explicit constraints"; "the lifecycle map applies FATF's published framework to supplied evidence".

Avoid: "world first", "100% accurate", "AI identifies criminals", "freezes accounts", "integrated with CFCFRMS/NCRP/banks", "a shared IP means common operator", "every rupee traced", "court admissible".

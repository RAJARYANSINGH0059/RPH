# Limitations and what is not claimed

## Not claimed

- Not "the world's first"; the category (statement ingestion + link analysis + infrastructure OSINT) exists (MuleMap, i2, Quantexa, Maltego, OpenCTI/MISP). The differentiator is the provenance/temporal/counter-evidence layer and its measured false-link behaviour on reproducible adversarial cases.
- Not integrated with NCRP, CFCFRMS, Rajasthan Police systems or any bank. The connector framework and file import are the integration boundary.
- Does not "support all Indian banks". Three synthetic statement layouts are covered by fixtures; a real bank format needs its own fixture and parser test before it can be claimed.
- Not court-proof or legally admissible. Hashes and an audit log provide integrity and traceability only.
- No accuracy figure applies to real data. All metrics are from synthetic, held-out scenarios.
- The ML output is a triage cue, never a decision; nothing is labelled "criminal".

## Technical limitations in this build

- **OCR**: PyMuPDF text extraction is implemented; the OCR fallback requires a Tesseract binary and `pytesseract`, which are not installed here. Scanned pages/images are stored, hashed and flagged `ocr_unavailable…manual review`.
- **Historical DNS**: only current DNS/RDAP lookups are implemented (optional). Passive-DNS history needs a licensed provider; current observations are labelled as such.
- **RDAP**: `rdap.org` redirects to registry servers; redirects are not followed outside the allowlist, so many domains return `redirect_not_followed`. Extending the allowlist per registry is a follow-up.
- **Durable uploads on Render free plan**: filesystem is ephemeral; synthetic cases regenerate, uploaded evidence does not persist across deploys unless a disk or S3 adapter is configured.
- **Entity resolution** is exact-key plus reference/amount bridging. Fuzzy name matching produces candidates only and never merges.
- **Path reconstruction** depends on time ordering; ambiguous dd/mm dates reduce path recall (measured: clean 0.70 F1 → adversarial 0.39 in the smoke benchmark).
- **Field extraction** in the benchmark counts exact reference+amount recovery; OCR-substituted references are counted as misses by design.
- **Benchmark size**: 4 seeds × 6 scenarios × 4 difficulties × 4 configurations = 384 runs (96 cases per configuration). Not yet 100+ *distinct* cases per difficulty.
- **Calibration**: the triage model is over-confident in the 0.4–0.6 band; scores are not probabilities.
- **Single-process connectors cache**: in-memory TTL cache and rate limiting are per process.
- **Auth**: single access token (8 h default), no refresh tokens, no MFA. Suitable for a demo, not for production policing use.
- **Supervisor membership**: supervisors must be added as case members (or be admin) to review a case; there is no UI for membership management yet (API-level only).
- **Frontend accessibility**: keyboard navigation and focus styles are implemented; the Cytoscape canvas itself is not screen-reader accessible, so the same edges are listed in an accessible table below it.

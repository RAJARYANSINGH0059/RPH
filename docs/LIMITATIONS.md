# Limitations and what is not claimed

## Not claimed

- Not "the world's first"; the category (statement ingestion + link analysis + infrastructure OSINT) exists (MuleMap, i2, Quantexa, Maltego, OpenCTI/MISP). The differentiator is the provenance/temporal/counter-evidence layer and its measured false-link behaviour on reproducible adversarial cases.
- Not integrated with NCRP, CFCFRMS, Rajasthan Police systems or any bank. The connector framework and file import are the integration boundary.
- Does not "support all Indian banks". Three synthetic statement layouts are covered by fixtures; a real bank format needs its own fixture and parser test before it can be claimed.
- Not court-proof or legally admissible. Hashes and an audit log provide integrity and traceability only.
- No accuracy figure applies to real data. All metrics are from synthetic, held-out scenarios.
- The ML output is a triage cue, never a decision; nothing is labelled "criminal".

## Technical limitations in this build

- **OCR**: PyMuPDF text layer first. Scanned pages/images go through an engine chain: Tesseract (English + Hindi, installed in the Dockerfile) → RapidOCR (pure Python, English/Latin; active on Render's native runtime) → explicit `ocr_unavailable` warning. OCR output carries engine, version, confidence, quality and boxes; low-confidence mentions enter the graph only as candidates. Hindi text is read only where Tesseract with `hin` data is present. **On the live Render free instance OCR is switched off** because the OCR runtime exceeds the 512 MiB memory limit (observed OOM kill); it needs a >=1 GB instance.
- **Historical DNS**: only current DNS/RDAP lookups are implemented (optional). Passive-DNS history needs a licensed provider; current observations are labelled as such.
- **RDAP**: `rdap.org` redirects to registry servers; redirects are not followed outside the allowlist, so many domains return `redirect_not_followed`. Extending the allowlist per registry is a follow-up.
- **Durable uploads**: an S3-compatible adapter (`STORAGE_BACKEND=s3`) with hash verification and signed URLs exists and is unit-tested, but the live Render service still runs with local (ephemeral) storage until a bucket and secrets are configured. The readiness endpoint reports which backend is active.
- **Entity resolution** is exact-key plus reference/amount bridging. Fuzzy name matching produces candidates only and never merges.
- **Path reconstruction (v2)** keeps unresolved hops explicit (with the statement that would resolve them), flags splits/merges and uncertain times, and never invents accounts; recall under noise is still limited by ambiguous dd/mm dates and missing second-layer statements. See docs/BENCHMARK.md for coverage, false-path rate, conservation and unresolved-hop rate.
- **Field extraction** in the benchmark counts exact reference+amount recovery; OCR-substituted references are counted as misses by design.
- **Benchmark size**: smoke 384 runs (96 cases per configuration) plus a frozen held-out range (seeds 700–703). Not yet 600 cases per configuration. Bootstrap 95% intervals are reported for path metrics.
- **Calibration**: the triage model is over-confident in the 0.4–0.6 band; scores are not probabilities.
- **Single-process connectors cache**: in-memory TTL cache and rate limiting are per process.
- **Auth**: single access token (8 h default), no refresh tokens, no MFA. Suitable for a demo, not for production policing use.
- **Membership management**: owners/admins add or remove members through the API (`/api/crosscase/cases/{id}/members`); there is no UI for it yet.
- **Frontend accessibility**: keyboard navigation and focus styles are implemented; the Cytoscape canvas itself is not screen-reader accessible, so the same edges are listed in an accessible table below it.

## Added in the gap-closure run

- **Cross-case correlation** is query-time and reads only cases the caller can access; it never merges entities and never asserts common ownership from shared hosting. It is not a global search across all users' cases.
- **Victim claims / restitution readiness** is a reconciliation aid. It does not allocate funds, decide entitlement or communicate with banks or the Money Restoration Module. Simulated holds in synthetic cases are labelled as simulated.
- **Cooperation pack** is a manual handoff bundle; there is no portal integration, login or submission.
- **Latency**: API responses are gzip-compressed and the frontend avoids waterfall requests, but a Render free-plan service sleeps when idle; the first request after a pause can take 30–60 s.

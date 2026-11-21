# Proof-carrying money trail: manifest and offline verifier

Implementation: `apps/api/app/services/proof.py` (builder), `scripts/verify_proof.py` (standalone, standard library only); API `GET /api/cases/{id}/paths/{index}/proof.json|proof.pdf`, `GET /api/cases/{id}/files/{file_id}/download`; UI *Financial Intelligence → Multi-Hop Fund Path* and *Export Centre*.

## Manifest schema (version 1.0.0)

```
manifest_version, generated_at, generator
case: {id, title, synthetic, data_status}
path: {index, accounts[], hop_count, status, unresolved_reason, path_class, alias_map_used{}}
hops[]: {hop, from_account, to_account, amount_minor, reference, event_time, time_precision, hop_class, flags[], corroborated,
         transaction_id, evidence_item_id, source_file_id, source_sha256, source_name, locator{}, raw_row{}, normalised{},
         column_mapping{}, parser{name,version,method}, statement_account_raw, direction, amount_raw, datetime_raw,
         relationship_id, relationship_level, contradictions[]}
source_files[]: {id, name, sha256, size_bytes, kind, synthetic}
rules: {path_algorithm_version, relationship_method_version, parser_version, alias_rule, money_representation, hop_chaining, amount_flags}
constraints: {conservation{entry_minor, exit_minor, ratio, flags, statement}, temporal{monotone_non_decreasing, known_times, uncertain_hops}}
contradictions[], limitations[]
integrity: {manifest_sha256, hmac_sha256|null, key_version|null, canonicalisation}
```

`manifest_sha256` is SHA-256 over the canonical JSON (sorted keys, compact separators, UTF-8) of every field except `integrity`. If `PROOF_SIGNING_KEY` is configured server-side, an HMAC-SHA256 of that digest is added with `PROOF_SIGNING_KEY_VERSION`; the key is never hard-coded.

## Verifier checks

1. Manifest hash recomputed and compared; HMAC when a key is supplied.
2. Rule versions match the verifier's expected versions (a changed algorithm fails).
3. SHA-256 of every cited source file found in `--files DIR` (by name or hash); a modified file fails (`MODIFIED`).
4. Locator validity: the cited CSV row (or workbook) contains the cited reference/amount.
5. Deterministic re-derivation: amount in paise re-parsed from the raw cell equals the manifest and the normalised value; reference cell equals the manifest.
6. Direction/account consistency through the alias map; temporal order for non-uncertain hops; split/merged flags consistent with amount changes; entry/exit amounts match first/last hop.

Exit code 0 = PASS, 1 = FAIL, 2 = usage error. `--json` writes the machine-readable result.

```
python scripts/verify_proof.py proof_path0.json --files ./originals --json result.json
```

## What it does and does not establish

PASS means the derivation reproduces from the cited files and no cited file changed. It does not establish authenticity of the source, the truth of its contents, who controlled any account, or legal admissibility. The certificate is integrity-protected, not an electronic signature or a legal certificate.

## Tests

`apps/api/tests/test_twin_coverage_proof.py::test_proof_manifest_verifies_offline_and_detects_tampering` (PASS on originals, FAIL on a modified file, FAIL on a modified manifest); benchmark v2 `proof_verify_pass` and `proof_tamper_detected`.

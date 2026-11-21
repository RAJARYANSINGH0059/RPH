# Synthetic sample case bundles

Public bundles produced by `app.synthetic.artifacts.build_bundle` for three seeds. Every file carries the
`SYNTHETIC DATA` watermark, uses `.test` domains, RFC 5737 documentation IPs and fictional banks/VPAs.
The sealed ground truth for these bundles is **not** included here; regenerate it with the same seed via
the API (`POST /api/synthetic/generate`) or `tests/benchmark/run_benchmark.py`.

Upload any bundle's files through *Upload Evidence* to exercise the parser exactly as the factory does.

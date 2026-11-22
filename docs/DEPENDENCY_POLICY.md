# Dependency security policy

Audits run in CI on every push: `npm audit` for the web application and `pip-audit` for the API.

## Severity policy

| Severity | Action |
|---|---|
| Critical, high | Fix before merge. The npm job fails the build at this level. |
| Moderate | Fix within the current increment, or record an exception below with an owner and a review date. |
| Low | Fix opportunistically, usually when the package is upgraded for another reason. |

An exception is only acceptable with a written reason, the real impact on this application, and a review date. "It is
only a development dependency" is a reason to record, not a reason to skip recording.

## Current state (2026-11-22)

**Web: zero advisories.** `postcss` was lifted to 8.5.23 and `@eslint/plugin-kit` to 0.4.0, both through a direct
dependency bump plus an `overrides` entry so the copy nested inside Next is lifted too. `npm audit --force` was not
used: it would have moved Next to a preview major.

**API: upgraded to the fixed versions available.**

| Package | Was | Now | Why |
|---|---|---|---|
| fastapi | 0.115.0 | 0.120.4 | 0.115 pins starlette below the patched line |
| starlette | 0.38.6 | 0.49.3 | several advisories fixed from 0.47.2 |
| PyJWT | 2.9.0 | 2.15.0 | token handling; this application's whole session model rests on it |
| Pillow | 10.4.0 | 13.0.0 | image decoding, reached by every uploaded screenshot |
| dnspython | 2.7.0 | 2.9.2 | used by the DNS connector |
| pytest-asyncio | 0.24.0 | 1.0.0 | required for a current pytest |

### Accepted, with reasons

| Package | Finding | Why it is accepted | Review |
|---|---|---|---|
| pytest | advisories fixed in 9.0.3 | pytest-asyncio 1.0.0 requires pytest below 9, so 8.4.2 is the highest compatible version. pytest is a test-only dependency and is never installed in the deployed API image. | When pytest-asyncio supports pytest 9 |

The Python audit is reported in CI but does not fail the build, because a Python fix frequently requires a framework
upgrade that needs its own testing pass. The result is uploaded as a build artefact so a reviewer sees it without
hunting through logs. The npm audit does fail the build at high and critical.

## How to check locally

```powershell
cd apps/web; npm audit --audit-level=high
```

```powershell
cd apps/api; pip install pip-audit; pip-audit -r requirements.txt
```

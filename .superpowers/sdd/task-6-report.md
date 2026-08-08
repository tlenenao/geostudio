# Task 6 report — `app.alerts.egress` SSRF guard for webhooks

## What I implemented

- `core/app/alerts/egress.py` (new): `assert_egress_allowed(url) -> None` raising
  `EgressBlockedError`, plus `build_guarded_session()` returning a `requests.Session`
  whose transport calls the guard before every send. Blocks non-http(s) schemes,
  unresolvable hosts, and IPs that are loopback/private/link-local/reserved/
  multicast/unspecified; optional allowlist via `CORE_ALERTS_EGRESS_ALLOWLIST`
  (comma-separated hostnames).
- `.env.example` (repo root): added the `CORE_ALERTS_EGRESS_ALLOWLIST` entry,
  placed directly after `CORE_PIPELINES_EGRESS_ALLOWLIST` per the brief.
- `core/tests/test_alert_egress.py` (new): 5 tests per the brief's intent
  (loopback block, private-range block, non-http scheme block, public-https
  allow, allowlist restriction) — see "Deviation from brief" below for one
  fix required in the test file.

This is a deliberate third instance of the SSRF-guard pattern already present
as `app.pipelines.egress` (SP-15f) and `app.harvest.egress`, per the task's
Global Constraints (webhook URLs are user-supplied per alert rule, unlike the
admin-configured SMTP secret, which is explicitly not egress-guarded).
Confirmed by direct diff against `app/pipelines/egress.py`: identical from the
module docstring's closing line onward except the allowlist env var name
(`CORE_ALERTS_EGRESS_ALLOWLIST` vs `CORE_PIPELINES_EGRESS_ALLOWLIST`) and one
explanatory comment line above `_ALLOWLIST_ENV` that `pipelines/egress.py`
carries and the brief's dictated code omits (the same explanation is present
instead in `alerts/egress.py`'s module docstring, so nothing is lost).

## Deviation from the brief: test file DNS dependency (fixed)

The brief's dictated `test_allows_a_public_https_url` and
`test_allowlist_restricts_to_named_hosts` use bare hostnames under the
`.test` TLD (`example.test`, `not-allowed.example.test`, `allowed.example.test`)
with no DNS mocking. `.test` is a TLD reserved by RFC 2606 specifically so it
*never* resolves in real DNS — confirmed locally
(`socket.getaddrinfo('example.test', None)` raises `gaierror` in this
environment). As dictated, `test_allows_a_public_https_url` would fail (it
asserts no exception, but `assert_egress_allowed` correctly raises
`EgressBlockedError` for "hôte non résoluble") — this is a bug in the plan's
test code, not the implementation.

The sibling guards' test suites (`tests/test_pipeline_egress.py`,
`tests/test_harvest_egress.py`) already solve exactly this by monkeypatching
`socket.getaddrinfo` to return a known-public IP, rather than depending on
live DNS. I applied the same fix here: both hostname-based tests now
monkeypatch `socket.getaddrinfo` to resolve to `93.184.216.34` (the same
public IP the sibling tests use), so `test_allows_a_public_https_url`
genuinely exercises the "public → allowed" path, and
`test_allowlist_restricts_to_named_hosts` genuinely exercises the allowlist
mismatch (not an incidental DNS failure that also happens to raise
`EgressBlockedError`). Test names, count (5), and coverage intent from the
brief are unchanged; only the DNS-resolution mechanics were fixed to match
the established, working pattern in this codebase.

## What I tested and results

- `PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_egress.py`
  → **RED** before implementation: `ModuleNotFoundError: No module named
  'app.alerts.egress'` (1 error during collection), as the brief predicted.
- After implementing `app/alerts/egress.py` with the brief's dictated test
  file verbatim: 4 passed, 1 failed
  (`test_allows_a_public_https_url` — the DNS issue above).
- After fixing the test file's DNS mocking: **GREEN** — `5 passed in 0.06s`.
- Cross-check: ran `test_alert_egress.py` alongside the two sibling suites
  (`test_pipeline_egress.py`, `test_harvest_egress.py`) together — `32 passed`,
  no interference between the three allowlist env vars.
- Confirmed `app.alerts.egress` imports cleanly standalone
  (`uv run python -c "import app.alerts.egress"`).
- `ruff` is not installed/configured in this project (no `ruff` binary, no
  ruff/black config in `pyproject.toml`) — skipped, not a project convention
  here.

## TDD evidence

RED:
```
ERROR tests/test_alert_egress.py
E   ModuleNotFoundError: No module named 'app.alerts.egress'
1 error in 0.10s
```

Intermediate (brief's test file verbatim, after implementation — caught the
DNS bug):
```
FAILED tests/test_alert_egress.py::test_allows_a_public_https_url
E   app.alerts.egress.EgressBlockedError: hôte non résoluble : 'example.test'
1 failed, 4 passed in 0.15s
```

GREEN (after fixing the test file's DNS mocking):
```
.....                                                                    [100%]
5 passed in 0.06s
```

## Files changed

- `core/app/alerts/egress.py` (new)
- `core/tests/test_alert_egress.py` (new)
- `.env.example` (repo root; +1 entry, `CORE_ALERTS_EGRESS_ALLOWLIST`)

Commit: `d744f0e feat(core): SP-16b — app.alerts.egress SSRF guard for webhook delivery`
(3 files changed, 127 insertions(+); only the three intended files staged —
verified `git status --short` showed no incidental `.superpowers/sdd/*`
tracking-file changes pulled into this commit).

## Self-review findings

- **Completeness**: 5/5 tests passing, matching the brief's required coverage
  (loopback, private range, non-http scheme, public allow, allowlist
  restriction).
- **Quality**: implementation is byte-for-byte identical to
  `app/pipelines/egress.py` from the docstring's end onward, except the
  allowlist env var name — verified via `diff`. French docstrings/comments
  preserved (`EgressBlockedError` docstring, module docstring, inline
  comments). English identifiers throughout, per repo convention.
- **Discipline**: no attempt to "improve" or share code across the
  `app.alerts`/`app.pipelines`/`app.harvest` boundary — duplication is
  intentional and preserved, per the task's explicit instruction. The only
  change from the brief's literal text is the test-file DNS-mocking fix
  described above, which was necessary for correctness, not a stylistic
  preference.
- **Testing depth**: `test_blocks_a_private_range_url` and
  `test_blocks_a_loopback_url` use IP literals directly (no DNS involved),
  so they genuinely exercise `_is_internal()`'s private/loopback branches,
  not just the scheme check. The two hostname-based tests now genuinely
  exercise the resolution + allowlist code paths via mocked
  `socket.getaddrinfo`, matching the rigor of the sibling test suites.
- **Import-linter contract**: `app.alerts` is already declared as a layer in
  `core/pyproject.toml`'s `[tool.importlinter]` contracts (line ~104,
  `"app.alerts"`); `egress.py` imports only stdlib + `requests`, so it
  introduces no new cross-layer dependency and needs no contract change.
- **Known residual risk, not re-flagged as new**: DNS-rebinding TOCTOU gap
  (resolve-then-connect race) applies here by construction, identically to
  the two sibling guards — already documented in `CLAUDE.md`'s "Suivis non
  bloquants ouverts" as accepted/deferred. Not raised as a new finding.

## Issues or concerns

None blocking. The one substantive finding — the brief's dictated test file
had a DNS-dependency bug (`.test` TLD never resolves) — was caught during RED
verification, root-caused against RFC 2606 and confirmed by direct
`getaddrinfo` reproduction, and fixed by adopting the exact mocking pattern
already used by the two sibling guard test suites in this same repo. No
change was needed to the brief's dictated implementation code
(`app/alerts/egress.py`) or to the `.env.example` entry — both were faithful
and correct as dictated.

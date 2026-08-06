# Task 4 Report — Repository (`core/app/secrets/repository.py`)

## What was implemented

Created `core/app/secrets/repository.py`, the CRUD + decrypt-on-demand
repository layer over `ConnectorSecret` (Task 3), tying together Task 1's
`crypto.encrypt`/`decrypt` and Task 2's `SECRET_PAYLOAD_ADAPTER`/`SecretPayload`.

Functions, exact signatures per brief (load-bearing for Task 5 and future
SP-15f):

- `get_secret(session, *, tenant_id, secret_id) -> ConnectorSecret | None`
- `get_secret_by_name(session, *, tenant_id, name) -> ConnectorSecret | None`
- `create_secret(session, *, tenant_id, created_by, name, kind, ciphertext, nonce) -> ConnectorSecret`
- `list_secrets(session, *, tenant_id) -> list[ConnectorSecret]`
- `delete_secret(session, secret) -> None`
- `get_secret_payload(session, *, tenant_id, name) -> SecretPayload | None`
  (fetches by name, decrypts via `crypto.decrypt`, validates via
  `SECRET_PAYLOAD_ADAPTER.validate_python`, returns `None` if no row)

All tenant-scoped queries filter by `tenant_id` (cross-tenant lookups
correctly return `None`/empty list). `create_secret` generates the id
(`uuid.uuid4().hex`) since the model has no server-side default.

Transcribed verbatim from the brief — confirmed via `diff` against the
brief's code block (only difference: the brief's trailing markdown fence
marker, not code content).

## TDD evidence

### RED

Wrote `core/tests/test_secrets_repository.py` exactly per brief (12 test
cases: 5 CRUD/isolation + 6 parametrized round-trip-per-kind + 1
missing-name case). Ran before implementing `repository.py`:

```
$ cd core && uv run pytest tests/test_secrets_repository.py -v
...
ERROR collecting tests/test_secrets_repository.py
ImportError: cannot import name 'repository' from 'app.secrets'
Interrupted: 1 error during collection
1 error in 0.10s
```

Matches expected failure mode from the brief (`ModuleNotFoundError`/
`ImportError` for the not-yet-created module).

### GREEN

After creating `repository.py`:

```
$ cd core && uv run pytest tests/test_secrets_repository.py -v
tests/test_secrets_repository.py::test_create_and_get_secret_by_name PASSED
tests/test_secrets_repository.py::test_create_secret_duplicate_name_per_tenant_raises PASSED
tests/test_secrets_repository.py::test_list_secrets_scoped_to_tenant PASSED
tests/test_secrets_repository.py::test_get_secret_cross_tenant_returns_none PASSED
tests/test_secrets_repository.py::test_delete_secret_removes_row PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload0] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload1] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload2] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload3] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload4] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_round_trip_for_every_kind[raw_payload5] PASSED
tests/test_secrets_repository.py::test_get_secret_payload_missing_name_returns_none PASSED

============================== 12 passed in 0.29s ==============================
```

12/12 passed, pristine (no warnings, no skips).

## Files changed

- Created: `core/app/secrets/repository.py`
- Created: `core/tests/test_secrets_repository.py`

Commit: `55d4da4` — `feat(core): secrets module — repository (CRUD +
decrypt-on-demand)`

## Self-review

- **Completeness**: all 5 brief steps done (write tests, verify RED,
  implement, verify GREEN, commit).
- **Quality**: `repository.py` content verified byte-for-byte identical
  to the brief's code block via `diff` (only delta is the brief's
  trailing markdown fence, not code). Function signatures match exactly
  as specified — no renames, no reordering, no added/removed parameters.
- **Discipline**: exactly the 2 files the brief asked for; nothing
  extra. No changes to Task 1-3 files.
- **Testing**: 12/12 passed, pristine output, matches the brief's
  expected count and breakdown exactly.
- **Git hygiene**: only `git add` on the two named files, no broad adds.
  Left the pre-existing modified `.superpowers/sdd/*` files (present in
  git status before I started) untouched, per the task's explicit
  instruction not to touch unrelated files or run resetting git
  commands.

## Issues or concerns

None. No blockers encountered; the brief's file contents matched the
actual state of Task 1-3's modules (`crypto.py`, `schemas.py`,
`models.py`) exactly, so this was a clean transcription task with no
surprises.

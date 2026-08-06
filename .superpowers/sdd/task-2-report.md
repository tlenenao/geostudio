# Task 2 Report: Payload schemas — `core/app/secrets/schemas.py`

**Date:** 2026-08-06  
**Session:** Task 2 of 5 (SP-15e)

## Implementation Summary

Task 2 successfully implemented the Pydantic discriminated-union payload schemas for the secrets module, following the brief's specification verbatim. Two files were created:

1. **`core/tests/test_secrets_schemas.py`** (test file, 9 tests)
2. **`core/app/secrets/schemas.py`** (implementation)

## TDD Evidence

### RED: Failing Tests (Step 2)
```
ERROR collecting tests/test_secrets_schemas.py
ModuleNotFoundError: No module named 'app.secrets.schemas'
```

All 9 tests failed at import as expected — the module did not exist.

### GREEN: Passing Tests (Step 4)
```
============================= test session starts ==============================
tests/test_secrets_schemas.py::test_api_key_header_placement_round_trips PASSED [ 11%]
tests/test_secrets_schemas.py::test_api_key_query_placement_round_trips PASSED [ 22%]
tests/test_secrets_schemas.py::test_bearer_token_round_trips PASSED       [ 33%]
tests/test_secrets_schemas.py::test_basic_auth_round_trips PASSED         [ 44%]
tests/test_secrets_schemas.py::test_oauth2_client_credentials_round_trips PASSED [ 55%]
tests/test_secrets_schemas.py::test_postgres_dsn_round_trips PASSED       [ 66%]
tests/test_secrets_schemas.py::test_unknown_kind_rejected PASSED          [ 77%]
tests/test_secrets_schemas.py::test_api_key_requires_location PASSED      [ 88%]
tests/test_secrets_schemas.py::test_secret_payload_adapter_decodes_decrypted_dict PASSED [100%]

============================== 9 passed in 0.11s ===============================
```

All 9 tests pass cleanly.

## Files Changed

- **Created:** `core/app/secrets/schemas.py`
  - 5 payload model classes (discriminated by `kind` field):
    - `ApiKeyPayload` (supports both `header` and `query` placement)
    - `BearerTokenPayload`
    - `BasicAuthPayload`
    - `OAuth2ClientCredentialsPayload`
    - `PostgresDsnPayload`
  - Type alias `SecretPayload` with `Field(discriminator="kind")`
  - `SECRET_PAYLOAD_ADAPTER: TypeAdapter[SecretPayload]` for runtime validation
  - `SecretCreate` model (name + payload)

- **Created:** `core/tests/test_secrets_schemas.py`
  - 9 comprehensive tests covering all payload kinds, validation rules, and adapter usage

## Self-Review Findings

✅ **Completeness:**
- All 5 steps from the brief executed in order
- All 9 tests pass
- Files match brief's specification exactly (verbatim transcription)
- No scope creep or extra work beyond the brief

✅ **Code Quality:**
- Discriminated union correctly implemented with Pydantic v2 `Annotated` + `Field(discriminator="kind")`
- Docstrings in French match project conventions (français for docs)
- All required fields and constraints present (e.g., `min_length=1, max_length=200` on name)
- SPDX header present on both files

✅ **Testing:**
- Tests cover all payload kinds
- Tests verify validation rules (required fields, unknown kinds rejected)
- Tests verify adapter usage pattern (post-decrypt validation)
- Edge cases like `location` field requirement tested

✅ **Discipline:**
- Only files specified in brief created (no extraneous files)
- Only git commands used were `git add <specific files>` and `git commit` (no reset/checkout)
- Commit message matches brief's exact specification

## Concerns

None. Task completed cleanly with all tests passing and commit successful.

## Commit

```
8d269c5 feat(core): secrets module — discriminated payload schemas
```

This commit is on the `dev` branch and ready for integration into the full SP-15e plan (Task 3+).

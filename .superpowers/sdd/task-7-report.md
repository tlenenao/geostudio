# Task 7 Report: SmtpCredentialsPayload Secret Kind

## What Was Implemented

Added a 6th variant to the `SecretPayload` discriminated union in `core/app/secrets/schemas.py`:

- **New class**: `SmtpCredentialsPayload` (lines 50–62 in schemas.py)
  - `kind: Literal["smtp"] = "smtp"`
  - Fields: `host`, `port`, `username`, `password`, `useTls` (default `True`), `fromAddress`
  - Docstring in French per file convention, explaining the trust model (admin-only secret, no egress guard needed)

- **Updated union**: `SecretPayload` now includes `SmtpCredentialsPayload` as the 6th variant (line 70 in schemas.py)

- **New test**: `test_smtp_credentials_payload_round_trips` in `core/tests/test_secrets_schemas.py`
  - Tests full serialization/deserialization through `SECRET_PAYLOAD_ADAPTER`
  - Verifies `dump_python()`, kind discriminator, and `validate_python()` restoration

## Test Results

### TDD Evidence: RED and GREEN

**RED (before implementation):**
```
ImportError: cannot import name 'SmtpCredentialsPayload' from 'app.secrets.schemas'
```

**GREEN (after implementation):**
```
test_smtp_credentials_payload_round_trips PASSED
All test_secrets_schemas.py: 10 passed in 0.08s
Full secrets suite (routes/repository/models): 28 passed in 3.14s
```

### Test Coverage

- `test_secrets_schemas.py`: All 10 tests pass (including new smtp test)
- `test_secrets_routes.py`: 6 tests pass (unchanged)
- `test_secrets_repository.py`: 12 tests pass (unchanged)
- `test_secrets_models.py`: 10 tests pass (unchanged)

No existing tests broken by the union addition.

## Files Changed

1. `core/app/secrets/schemas.py` (added SmtpCredentialsPayload class, updated SecretPayload union)
2. `core/tests/test_secrets_schemas.py` (added test_smtp_credentials_payload_round_trips)

## Self-Review Findings

✓ **Class Design**: Matches sibling classes exactly
  - `kind` field with `Literal` default
  - All fields match brief specification (host, port, username, password, useTls, fromAddress)
  - `useTls` correctly defaults to `True`
  - Docstring in French per file convention

✓ **Union Integration**: Cleanly additive
  - No migrations needed (by design of the union)
  - Discriminator="kind" correctly distinguishes "smtp" from other kinds
  - TypeAdapter continues to work correctly with new variant

✓ **Test Quality**: Full round-trip verification
  - Constructs instance with all fields
  - Uses `dump_python()` to serialize (not just construction)
  - Verifies `kind == "smtp"` discriminator
  - Uses `validate_python()` to deserialize (not just direct construction)
  - Checks instance type and field values after restoration
  - Follows existing test patterns in the file

✓ **Discipline**: Only added what the brief specified
  - No extra fields, no extra tests, no extra validation
  - Matches brief's exact field names and defaults

## Commit

```
5f15a75 feat(core): SP-16b — SmtpCredentialsPayload secret kind (additive)
```

## No Issues or Concerns

Implementation is complete, fully tested, and ready for Task 8 (AlertRule notification consumer).

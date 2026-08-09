# SP-17a — Task 4 report: jeton d'export HS256 + extension de `get_current_user`

## What was implemented

1. **`core/app/auth/export_tokens.py`** (new) — literal implementation from
   the brief: `ExportTokenError`, `ExportTokenClaims`, `mint_export_token`,
   `is_export_token`, `decode_export_token`. HS256 JWT, `typ="export"`
   discriminator, required claims `tenant_id`/`user_id`/`job_id`, secret
   read lazily from `CORE_EXPORT_TOKEN_SECRET` (fail-fast `os.environ[...]`,
   no silent default).
2. **`core/app/auth/dependency.py`** — one import line added (after existing
   imports), one new code block inserted in `get_current_user` exactly where
   the brief specified: after the `_mock_mode()` early-return block, before
   the RS256/JWKS `try:`. No other restructuring.
3. **`.env.example`** — `CORE_EXPORT_TOKEN_SECRET=` documented right after
   `CORE_EXPORT_ENABLED=false`, with the literal comment block from the brief.
4. Two new test files (see TDD evidence below).

## Deviation from the brief's literal test code (and why)

The brief's literal test fixtures use short HMAC secrets (`"test-export-secret"`,
18 bytes; `"a-different-secret"`, 19 bytes; `"irrelevant"`, 10 bytes for an
HS512 example). This repo's `core/pyproject.toml` sets
`filterwarnings = ["error", ...]` for pytest, which promotes PyJWT's
`InsecureKeyLengthWarning` (raised by `jwt.encode`/`jwt.decode` when the HMAC
key is below the algorithm's recommended minimum — 32 bytes for HS256, 64 for
HS512) into a hard test failure. Running the brief's literal test code failed
all 6 tests in `test_export_tokens.py` on this warning, not on the intended
assertions.

Fix applied (test files only, no production code or pytest config changed):
padded the secret literals to the recommended minimum length in both test
files (`test-export-secret-padding-01234` = 32 bytes for HS256 material,
`a-different-secret-padding-01234` = 32 bytes for the tamper test, a
64-byte padded string for the HS512 discriminator example). No test
semantics changed — same assertions, same code paths exercised, only the
secret string literals are longer. This did not touch `export_tokens.py`,
`dependency.py`, or any file outside the task's allowed scope. Confirmed
by re-reading `.env.example`'s own new comment: "chaîne quelconque, pas de
format base64 requis" — no length contract is implied for production
secrets, so this padding is purely a test-hygiene fix, not a behavior change.

## TDD evidence

### Step 1-4: `test_export_tokens.py`

RED (before `export_tokens.py` existed):
```
ModuleNotFoundError: No module named 'app.auth.export_tokens'
```

GREEN (after implementation, with the secret-padding fix applied):
```
tests/test_export_tokens.py::test_mint_and_decode_round_trip PASSED
tests/test_export_tokens.py::test_is_export_token_true_for_export_token_false_for_rs256 PASSED
tests/test_export_tokens.py::test_decode_rejects_expired_token PASSED
tests/test_export_tokens.py::test_decode_rejects_tampered_signature PASSED
tests/test_export_tokens.py::test_decode_rejects_wrong_typ_claim PASSED
tests/test_export_tokens.py::test_decode_rejects_missing_claim PASSED
6 passed in 0.05s
```

### Step 5-9: `test_auth_export_token.py`

RED (before `dependency.py` was extended — falls through to the RS256 path
and blows up on missing `CORE_OIDC_ISSUER` env var instead of being
recognized as an export token):
```
FAILED test_get_current_user_accepts_valid_export_token - KeyError: 'CORE_OIDC_ISSUER'
FAILED test_get_current_user_rejects_expired_export_token - KeyError: 'CORE_OIDC_ISSUER'
FAILED test_get_current_user_rejects_export_token_for_wrong_tenant - KeyError: 'CORE_OIDC_ISSUER'
FAILED test_get_current_user_rejects_export_token_for_deleted_user - KeyError: 'CORE_OIDC_ISSUER'
4 failed, 2 passed in 0.36s
```
(The 2 pre-existing passes are `test_get_current_user_rejects_missing_bearer`
and the fall-through test, both of which don't require the export-token path
to exist yet.)

GREEN (after inserting the new code path in `dependency.py`):
```
tests/test_auth_export_token.py::test_get_current_user_accepts_valid_export_token PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_expired_export_token PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_export_token_for_wrong_tenant PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_export_token_for_deleted_user PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_missing_bearer PASSED
tests/test_auth_export_token.py::test_get_current_user_falls_through_to_oidc_path_for_non_hs256_garbage PASSED
6 passed in 0.31s
```

### Full auth-related subset (`pytest tests/ -k auth -v`)

```
72 passed, 1362 deselected in 4.91s
```
Includes `test_auth.py` (mock mode, RS256/JWKS real path, wrong
audience/issuer, JWKS connection error, JWKS client memoization, analyst
subs) — all still green, zero regressions.

### Full core suite (`pytest tests/`)

```
1297 passed, 137 skipped in 86.71s
```
Zero failures.

### Import-linter contract (`lint-imports`)

```
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```
Confirms the placement rationale in the brief: `app.auth.export_tokens`
lives at the bottom of the layer stack, no upward import introduced.

## Files changed

- `core/app/auth/export_tokens.py` (new)
- `core/app/auth/dependency.py` (modified: 1 import line, 1 inserted block)
- `core/tests/test_export_tokens.py` (new)
- `core/tests/test_auth_export_token.py` (new)
- `.env.example` (modified: `CORE_EXPORT_TOKEN_SECRET` documented)

Note: `.superpowers/sdd/progress.md` shows as modified in `git status` but
was NOT staged or committed by this task — that file is being updated by
the parent/orchestrating process outside this task's scope, and is not in
the task's allowed file list.

## Self-review: auth-safety checks

Re-read the inserted block in `dependency.py` (lines 91-101) line by line:

```python
    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        user = session.get(User, claims.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid export token")
        return user
```

- **Expiry enforcement**: `decode_export_token` calls `jwt.decode(...,
  algorithms=["HS256"])` with no `options={"verify_exp": False}`, so PyJWT's
  default expiry check applies — an expired token raises
  `jwt.ExpiredSignatureError` (a `PyJWTError` subclass), caught and
  re-raised as `ExportTokenError`, caught here and turned into 401.
  Verified by both `test_decode_rejects_expired_token` (module level) and
  `test_get_current_user_rejects_expired_export_token` (dependency level).
- **Tampered signature rejection**: HS256 signature verification is
  symmetric — `jwt.decode` re-derives and checks the signature against
  `CORE_EXPORT_TOKEN_SECRET`; any tampering (payload or signature bytes)
  fails verification and raises `InvalidSignatureError`, caught the same
  way. Verified by `test_decode_rejects_tampered_signature`. No
  algorithm-confusion risk: `is_export_token` gates strictly on
  `header["alg"] == "HS256"` and `decode_export_token` passes
  `algorithms=["HS256"]` explicitly (never accepts `alg=none` or lets the
  token dictate the algorithm).
- **Tenant-mismatch rejection**: explicit `claims.tenant_id != tenant.id`
  check before any user lookup, independent of signature validity — a
  validly-signed token minted for a different tenant is still rejected.
  Verified by `test_get_current_user_rejects_export_token_for_wrong_tenant`.
- **Deleted/nonexistent-user rejection**: `session.get(User,
  claims.user_id)` returns `None` for a user id that doesn't exist in the
  DB (covers both "never existed" and "deleted after token was minted" —
  same code path, no separate soft-delete flag in this schema). Verified
  by `test_get_current_user_rejects_export_token_for_deleted_user`.
  `User.id` is a `str` primary key (`core/app/users/models.py:18`),
  matching `claims.user_id: str` — no type mismatch that could cause
  `session.get` to silently miss.
- **Clean fall-through for non-export bearer values**: `is_export_token`
  wraps `jwt.get_unverified_header` in a `try/except jwt.PyJWTError`
  returning `False` on any decode failure (garbage string, malformed JWT),
  and returns `False` whenever `header.get("alg") != "HS256"` (i.e. real
  RS256 OIDC tokens). Both cases fall through untouched to the pre-existing
  RS256/JWKS `try:` block below, preserving prior behavior exactly (401 on
  invalid token, 503 on JWKS unreachable). Verified by
  `test_get_current_user_falls_through_to_oidc_path_for_non_hs256_garbage`
  and by `test_is_export_token_true_for_export_token_false_for_rs256`
  (asserts `False` for both an HS512 token and a plain non-JWT string).
- **Ordering vs. mock mode**: the new block sits after the `_mock_mode()`
  early return, per the brief's exact placement instruction — in
  `CORE_AUTH_MODE=mock`, export tokens are never evaluated (mock identity
  wins). This matches existing test conventions (mock mode is
  dev/e2e-only) and is exercised correctly since `test_auth_export_token.py`
  explicitly `monkeypatch.delenv("CORE_AUTH_MODE")` to force non-mock mode.

No Critical/Important findings. One test-hygiene issue found and fixed (see
"Deviation" section above) — not a production code defect, purely a pytest
strict-warnings interaction with the brief's literal short test secrets.

## Concerns

None blocking. Worth flagging for whoever wires the export-worker consumer
(Task 13, `app.export` minting these tokens): production deployments should
be encouraged (not currently enforced) to use a `CORE_EXPORT_TOKEN_SECRET`
of at least 32 bytes, matching the `openssl rand -base64 32` generation
command already in the `.env.example` comment — PyJWT will emit (and, if a
future change tightens this repo's runtime warning filters, could even
error on) `InsecureKeyLengthWarning` for shorter secrets at mint/decode
time in production too, not just in tests.

## Fix round 1 (code review Critical)

### The finding

Code review on commit `3e46f0c` found: `_secret()` in
`core/app/auth/export_tokens.py` reads `os.environ["CORE_EXPORT_TOKEN_SECRET"]`
with no guard — a bare `KeyError` if unset. `decode_export_token` only caught
`jwt.PyJWTError`, not `KeyError`, so the exception propagated unhandled
through `get_current_user`'s `except ExportTokenError:` handler too (a plain
`KeyError` is neither).

**Net effect** (reproduced independently by the reviewer): on any instance
where `CORE_EXPORT_TOKEN_SECRET` is unset — every instance today, since the
export worker that would set it doesn't exist yet — an unauthenticated
attacker sending `Authorization: Bearer <any HS256 JWT signed with any
secret of their choosing>` to any endpoint behind `get_current_user` crashes
the process with an unhandled `KeyError`, surfacing as a bare Starlette 500
instead of a clean 401. No knowledge of the real secret is required to
trigger it — the attacker mints their own HS256 token.

### What changed

`core/app/auth/export_tokens.py`, `decode_export_token`: widened the except
clause from `except jwt.PyJWTError as exc:` to
`except (jwt.PyJWTError, KeyError) as exc:`, with a comment explaining the
`KeyError` case covers a missing `CORE_EXPORT_TOKEN_SECRET`. This makes a
missing secret raise `ExportTokenError`, which `get_current_user` already
correctly maps to `HTTPException(401)`. Chose this over guarding inside
`_secret()` because `decode_export_token` is the only caller that needs to
treat a missing secret as an *auth failure*; `mint_export_token` (the other
caller of `_secret()`) legitimately should keep crashing loudly if invoked
without the secret configured — that's a server misconfiguration at mint
time (worker-side), not an attacker-controlled input, and swallowing it
there was out of scope for this fix.

Considered and rejected the "no length enforcement" non-blocking note from
the same review: explicitly out of scope per the reviewer's own framing (the
original brief only specified "chaîne quelconque, pas de format base64
requis"), so left untouched.

### Regression tests added

1. `core/tests/test_export_tokens.py::test_decode_raises_export_token_error_when_secret_unset` —
   `monkeypatch.delenv("CORE_EXPORT_TOKEN_SECRET", raising=False)`, mints a
   forged HS256 token via bare `jwt.encode(..., "attacker-controlled-secret-of-their-choosing", algorithm="HS256")`
   (not `mint_export_token`, which would itself hit the missing-secret path),
   asserts `decode_export_token` raises `ExportTokenError`.
2. `core/tests/test_auth_export_token.py::test_get_current_user_rejects_forged_hs256_token_when_export_secret_unset` —
   same forged token, `CORE_EXPORT_TOKEN_SECRET` unset, asserts
   `get_current_user(...)` raises `HTTPException` with `status_code == 401`.

### RED (before fix — temporarily reverted `export_tokens.py` only, tests in place)

```
app/auth/export_tokens.py:54: in decode_export_token
    claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
app/auth/export_tokens.py:32: in _secret
    return os.environ["CORE_EXPORT_TOKEN_SECRET"]
E   KeyError: 'CORE_EXPORT_TOKEN_SECRET'
...
FAILED tests/test_export_tokens.py::test_decode_raises_export_token_error_when_secret_unset
FAILED tests/test_auth_export_token.py::test_get_current_user_rejects_forged_hs256_token_when_export_secret_unset
2 failed in 0.32s
```
Confirms the finding reproduces exactly as described: raw `KeyError`, not
`ExportTokenError`/`HTTPException`.

### GREEN (after fix)

```
tests/test_export_tokens.py::test_mint_and_decode_round_trip PASSED
tests/test_export_tokens.py::test_is_export_token_true_for_export_token_false_for_rs256 PASSED
tests/test_export_tokens.py::test_decode_rejects_expired_token PASSED
tests/test_export_tokens.py::test_decode_rejects_tampered_signature PASSED
tests/test_export_tokens.py::test_decode_rejects_wrong_typ_claim PASSED
tests/test_export_tokens.py::test_decode_rejects_missing_claim PASSED
tests/test_export_tokens.py::test_decode_raises_export_token_error_when_secret_unset PASSED
tests/test_auth_export_token.py::test_get_current_user_accepts_valid_export_token PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_expired_export_token PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_export_token_for_wrong_tenant PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_export_token_for_deleted_user PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_missing_bearer PASSED
tests/test_auth_export_token.py::test_get_current_user_rejects_forged_hs256_token_when_export_secret_unset PASSED
tests/test_auth_export_token.py::test_get_current_user_falls_through_to_oidc_path_for_non_hs256_garbage PASSED
14 passed in 0.35s
```

### Auth-subset regression (`pytest tests/ -k auth -v`)

```
73 passed, 1363 deselected in 5.07s
```
Zero regressions. One more test than the 72 in the original task-4 report:
of the 2 new regression tests, only
`test_get_current_user_rejects_forged_hs256_token_when_export_secret_unset`
(module `test_auth_export_token.py`, matches `-k auth` on module name) is
picked up by this filter — the other new test lives in
`test_export_tokens.py`, whose module/function names contain no "auth"
substring, so `-k auth` correctly excludes it (it's still covered by the
narrower run above and by the full suite).

### Commit

`ffa19a8` — `fix(core): SP-17a — jeton d'export : secret manquant ne doit
jamais crasher en 500`. Files: `core/app/auth/export_tokens.py`,
`core/tests/test_export_tokens.py`, `core/tests/test_auth_export_token.py`.
Did not touch `.superpowers/sdd/progress.md`, which was already modified in
the working tree by the parent orchestrating process before this fix task
started (out of scope, not staged/committed here — same convention noted in
the original task-4 report).

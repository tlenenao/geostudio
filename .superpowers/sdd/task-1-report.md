# Task 1 Report: Encryption primitive — `core/app/secrets/crypto.py`

## Summary

Task 1 complete. Implemented the encryption primitive module (`app.secrets.crypto`) providing AES-256-GCM encryption/decryption for connector secrets, with master key loading from environment variable. All 6 tests pass, layering contract held, commit created.

## What Was Implemented

1. **`core/app/secrets/__init__.py`** — Package marker with SPDX header
2. **`core/app/secrets/crypto.py`** — AES-256-GCM encryption primitive with three functions:
   - `load_master_key() -> bytes` — reads `CORE_SECRETS_MASTER_KEY` from environment, validates as 32-byte base64-encoded key; raises `KeyError` if missing, `RuntimeError` if malformed or wrong size
   - `encrypt(payload: dict) -> tuple[bytes, bytes]` — encrypts dict to JSON, returns (ciphertext, nonce) pair with random 12-byte nonce
   - `decrypt(ciphertext: bytes, nonce: bytes) -> dict` — decrypts ciphertext using matching nonce, returns original dict; raises `InvalidTag` if tampered or wrong key
3. **`core/pyproject.toml`** — Two changes:
   - Added `cryptography>=42.0` as direct dependency (was already present transitively via `pyjwt[crypto]`)
   - Added `"app.secrets"` to import-linter layers list (between `"app.pipelines"` and `"app.ingestion"`)
4. **`core/tests/test_secrets_crypto.py`** — 6 comprehensive test cases covering encrypt/decrypt round-trip, tampered ciphertext rejection, wrong-key rejection, and key validation (missing, malformed base64, wrong length)

## TDD Evidence

### RED Phase (Before Implementation)
```
$ cd core && uv run pytest tests/test_secrets_crypto.py -v
...
ERROR tests/test_secrets_crypto.py
ModuleNotFoundError: No module named 'app.secrets'
```
Test collection failed as expected before module creation.

### GREEN Phase (After Implementation)
```
$ cd core && uv run pytest tests/test_secrets_crypto.py -v
============================= test session starts ==============================
tests/test_secrets_crypto.py::test_encrypt_decrypt_round_trip PASSED     [ 16%]
tests/test_secrets_crypto.py::test_decrypt_rejects_tampered_ciphertext PASSED [ 33%]
tests/test_secrets_crypto.py::test_decrypt_rejects_wrong_key PASSED      [ 50%]
tests/test_secrets_crypto.py::test_load_master_key_missing_raises PASSED [ 66%]
tests/test_secrets_crypto.py::test_load_master_key_malformed_base64_raises PASSED [ 83%]
tests/test_secrets_crypto.py::test_load_master_key_wrong_length_raises PASSED [100%]

============================== 6 passed in 0.05s ===============================
```
All 6 tests pass.

## Files Changed

- **Created:** `core/app/secrets/__init__.py`
- **Created:** `core/app/secrets/crypto.py`
- **Created:** `core/tests/test_secrets_crypto.py`
- **Modified:** `core/pyproject.toml` (dependencies + import-linter layers)
- **Modified:** `core/uv.lock` (auto-generated, no cryptography version change)

## Layering Contract Verification

```
$ cd core && uv run lint-imports
...
Contracts: 1 kept, 0 broken.
```
Import-linter contract verified clean. No cross-module imports in `crypto.py`; only stdlib (`base64`, `json`, `os`) and external (`cryptography`). Layer insertion `"app.secrets"` is syntactically valid.

## Self-Review Against Brief

✅ **Step 1:** Test file content matches brief exactly (lines 21–73)  
✅ **Step 2:** Tests fail with expected `ModuleNotFoundError` before implementation  
✅ **Step 3:** `cryptography>=42.0` added correctly after `pyjwt[crypto]>=2.8`, with full comment  
✅ **Step 4:** `"app.secrets"` inserted in layers list between `"app.pipelines"` and `"app.ingestion"`  
✅ **Step 5:** Module implementation matches brief exactly:
  - `__init__.py` is single SPDX header line
  - `crypto.py` docstring, constants, three functions, all verbatim  
  - No extra scope, no modifications
✅ **Step 6:** Layering contract holds (1 kept, 0 broken)  
✅ **Step 7:** All 6 tests pass  
✅ **Step 8:** Commit message exact: `"feat(core): secrets module — AES-GCM encryption primitive"`  

## Code Quality

- **Encryption:** AES-256-GCM per spec, AESGCM from `cryptography.hazmat.primitives.ciphers.aead`, random 12-byte nonce per operation
- **Key Management:** Strict validation — 32-byte requirement, base64 decode with `validate=True`, fail-fast on missing/malformed key, never logged (docstring warning in place)
- **JSON Roundtrip:** Plaintext serialized as JSON UTF-8, decrypted plaintext parsed back to dict
- **Error Handling:** `KeyError` for missing env var (not caught), `RuntimeError` for malformed key with clear message, `InvalidTag` from cryptography library for tampered ciphertext or wrong key
- **Test Coverage:** All three public functions covered; error paths (missing key, malformed base64, wrong length, tampering, wrong key) all tested
- **Documentation:** Docstrings in French per CLAUDE.md, referencing SP-15e design doc

## Issues or Concerns

None. Task is complete and correct per brief:
- No ambiguities encountered
- No dependencies on other tasks (crypto.py is standalone)
- All steps followed verbatim
- All verification gates passed
- Ready for Task 2 and beyond

## Commit

- **SHA:** `2b3f202`
- **Message:** `feat(core): secrets module — AES-GCM encryption primitive`
- **Date:** 2026-08-06

---

**Status:** DONE  
**Report written:** 2026-08-06

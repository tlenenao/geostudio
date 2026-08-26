# Task 3: OpenAPI + TS Regeneration — Report

**Date:** 2026-08-23

## Summary
Regenerated `core/openapi.json` and `shell/src/api/generated/core-schema.d.ts` following changes to `AggregateRequestBody` (added `sample` field) and `MapLayer` (added `symbology` field) from SP-25 tasks 1–2.

## Execution

### Step 1: Regenerate OpenAPI and TS types

**OpenAPI regeneration:**
```bash
cd /home/lenen/projets/geostudio/core && \
  PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY=$(openssl rand -base64 32) \
  uv run python scripts/export_openapi.py openapi.json
```
✓ Completed successfully

**TypeScript types regeneration:**
```bash
cd /home/lenen/projets/geostudio/shell && npm run gen:api-types
```
Output:
```
✨ openapi-typescript 7.13.0
🚀 ../core/openapi.json → src/api/generated/core-schema.d.ts [212.8ms]
```
✓ Completed successfully

### Step 2: Verify the diff

**OpenAPI changes in `core/openapi.json`:**
- Added `sample` field to `AggregateRequestBody` schema (integer or null)
- Added `symbology` field to `MapLayer` schema (object or null)

**TypeScript changes in `shell/src/api/generated/core-schema.d.ts`:**
- Added `sample?: number | null;` to AggregateRequestBody interface
- Added `symbology?: { [key: string]: unknown; } | null;` to MapLayer interface

**Diff verification:**
```
git diff --stat
 core/openapi.json                        |  23 ++
 shell/src/api/generated/core-schema.d.ts |   6 +
```

**Detailed inspection:** ✓ Confirmed only the two expected schemas changed. No unrelated fields moved or modified.

**Untracked/unstaged files:**
- `.superpowers/sdd/` files had staged changes from previous work — reset to working tree only
- `deploy/postgis/pg_hba.conf` — untracked, left untouched
- Only committed: `core/openapi.json` and `shell/src/api/generated/core-schema.d.ts`

### Step 3: Test suites

**Core tests:**
```bash
cd /home/lenen/projets/geostudio/core && \
  CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@localhost:5433/gis_test" \
  uv run pytest -q
```
Result: **1878 passed, 5 skipped** (matches expected reference exactly)
- ✓ No regression
- Exit code: 0

**Shell build:**
```bash
cd /home/lenen/projets/geostudio/shell && npm run build
```
Result: **✓ built in 16.63s**
- ✓ TypeScript type checking passed (no errors)
- ✓ Vite bundle successful
- Exit code: 0

### Step 4: Commit

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore(api): régénère OpenAPI et les types TS (sample, symbology)"
```

**Commit created:**
- SHA: `6fc47cd`
- Subject: `chore(api): régénère OpenAPI et les types TS (sample, symbology)`
- Files changed: 2 (29 insertions)
- Pre-commit hooks: ✓ All passed (eslint, prettier, commitlint)

## Verification Summary

| Check | Status | Evidence |
|-------|--------|----------|
| OpenAPI regenerated | ✓ PASS | Script executed, output written to `core/openapi.json` |
| TS types regenerated | ✓ PASS | `openapi-typescript` completed successfully |
| Diff is clean | ✓ PASS | Only `sample` and `symbology` fields added, no unrelated changes |
| Core tests green | ✓ PASS | 1878 passed, 5 skipped (exact reference match) |
| Shell build green | ✓ PASS | Built successfully in 16.63s |
| Commit created | ✓ PASS | Conventional message, pre-commit hooks passed |

## Concerns
None. All checks passed. The regeneration is clean and complete.

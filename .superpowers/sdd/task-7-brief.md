### Task 7: Regenerate OpenAPI spec and shell generated types

**Files:**
- Modify: `core/openapi.json` (regenerated, not hand-edited)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)

**Interfaces:** none (mechanical regeneration — CLAUDE.md flags forgetting this step as a recurring, multi-occurrence mistake on this repo).

- [ ] **Step 1: Enable the capability flag and regenerate `openapi.json`**

Run:

```bash
cd core && CORE_TILESET3D_ENABLED=true CORE_EXPORT_ENABLED=false CORE_ETL_ENABLED=false uv run python scripts/export_openapi.py openapi.json
```

Expected: `core/openapi.json` changes, purely additively (new `/tileset3d/...` paths and `Tileset3DPayload`/`Tileset3DUploadCreate`/etc. schemas appear; nothing existing is removed or changed in an incompatible way).

- [ ] **Step 2: Verify the diff is additive**

Run: `cd core && git diff --stat openapi.json`
Expected: only additions (new lines), review with `git diff openapi.json` that no existing path/schema was modified or removed.

**Important:** this repo's CI generates `openapi.json` with `CORE_TILESET3D_ENABLED` (and `CORE_ETL_ENABLED`/`CORE_EXPORT_ENABLED`) **unset** (matching the established precedent documented in CLAUDE.md for `app.pipelines`/`app.export` — the committed `openapi.json` reflects the default-disabled surface, not every capability flag turned on at once). Re-run Step 1 **without** setting `CORE_TILESET3D_ENABLED=true` before committing, so the checked-in file matches what CI regenerates:

```bash
cd core && uv run python scripts/export_openapi.py openapi.json
git diff --stat openapi.json
```

Expected: this second run shows **no diff** relative to the pre-Task-7 committed file — the new `/tileset3d/...` routes are gated behind the flag and CI never enables it, exactly like `/pipelines/...` and `/export/...` already aren't in the committed spec today. Confirm with `grep -c tileset3d openapi.json` — expect `0`.

- [ ] **Step 3: Regenerate the shell's generated TypeScript types**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` is unchanged (since `openapi.json` itself is unchanged after Step 2 — the flag-gated routes never reach the committed spec). Confirm with `git status --short shell/src/api/generated/core-schema.d.ts` — expect no output.

- [ ] **Step 4: Confirm nothing needs committing**

Run: `git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: no output — this task is a verification step (proving the capability-flag discipline holds) rather than a code change. If either file *does* show a diff at this point, stop and investigate before continuing to Task 8 — it means something in Task 4–6 leaked into the always-on route surface.

- [ ] **Step 5: No commit needed**

This task intentionally produces no diff to commit — it exists to catch the exact class of mistake CLAUDE.md flags repeatedly on this repo (forgetting to regenerate, or regenerating with the wrong flags on). If Step 4 found a diff and you fixed the root cause, commit that fix under its own message; otherwise move on to Task 8.

---


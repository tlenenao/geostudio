## Task 3: OpenAPI + TS regeneration

**Files:**
- Modify: `core/openapi.json` (or wherever it's exported — check
  `scripts/export_openapi.py`'s output path)
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:** none new — mechanical regeneration task.

- [ ] **Step 1: Regenerate**

Run (per CLAUDE.md/SP-23 precedent, the bare script command fails):

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY=$(openssl rand -base64 32) uv run python scripts/export_openapi.py
```

Then regenerate the TS side per whatever `npm` script does it (check
`shell/package.json` for a `generate:api`/`openapi` script) and run it.

- [ ] **Step 2: Verify the diff is non-empty and sane**

Run: `git diff --stat`
Expected: `AggregateRequestBody`'s schema gains `sample`; `MapLayer`'s schema
gains `symbology`. No unrelated fields move — if anything else changed,
investigate before committing (a stray unrelated diff here has burned this
project before, per the SP-23/SP-24 "classe d'oubli la plus récurrente"
notes — regenerating late is the usual failure, not regenerating wrong, but
verify anyway).

- [ ] **Step 3: Run both suites to confirm nothing broke**

Run: `cd core && uv run pytest -q` and `cd shell && npm run build`
Expected: both green.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
chore(api): régénère OpenAPI et les types TS (sample, symbology)
EOF
)"
```

---


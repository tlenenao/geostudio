## Task 13: Final validation gate

**Files:** none (verification only).

- [ ] **Step 1: Core suite**

Run: `cd core && uv run pytest -v`
Expected: PASS, no drop from 1868 passed / 5 skipped + this plan's ~16 new
tests (Tasks 1-2).

- [ ] **Step 2: Core lint/type/import gates**

Run: `cd core && ruff check . && ruff format --check . && uv run mypy --strict app/auth app/secrets app/analytics app/copilot && lint-imports`
Expected: all green.

- [ ] **Step 3: Core coverage**

Run: `cd core && uv run pytest --cov=app --cov-report=term-missing -q | tail -5`
Expected: ≥ 85 (per `core/.coverage-threshold`).

- [ ] **Step 4: Shell suite**

Run: `cd shell && npx vitest run`
Expected: PASS, no drop from 159 files / 1387 tests + this plan's new tests
(Tasks 4, 6, 7, 8, 9, 10, 11).

- [ ] **Step 5: Shell lint/format/build**

Run: `cd shell && npm run lint && npm run format:check && npm run build`
Expected: all green.

- [ ] **Step 6: Shell coverage**

Run: `rm -rf shell/dist shell/dist-export && cd shell && npx vitest run --coverage | tail -20`
Expected: ≥ 88 (per `shell/.coverage-threshold`) — measured after removing
build artifacts, per the documented SP-22/23/24 trap.

- [ ] **Step 7: Shell E2E**

Run: `cd shell && npm run e2e`
Expected: PASS, no regression (baseline 107 passed / 4 skipped at end of
SP-24, plus this plan's new spec).

- [ ] **Step 8: Deployability guard**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: all green — this plan adds no new env var, no new service, no new
bucket, so this should be a no-op confirmation, not a fix.

- [ ] **Step 9: pre-commit**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 hooks green.

- [ ] **Step 10: Confirm OpenAPI/TS sync**

Run: `git status --porcelain -- core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: empty (already committed in Task 3, nothing drifted since).

- [ ] **Step 11: Update CLAUDE.md**

Add an SP-25 entry to `### Fait` (and remove/adjust the SP-25 forward
references currently in `### À venir`), following this repo's own
established format (one bullet per SP, cross-references to the spec file,
notable deviations from plan/spec called out explicitly — see the SP-24
entry as the immediate template). This is a documentation task, not a code
task — no test/build steps apply, just accuracy against what was actually
built (re-read the final diffs of Tasks 1-12 before writing it, don't
describe intentions from this plan as if they were unconditionally true —
Task 11 in particular narrowed the widget's Jenks support versus the
spec's original assumption, and that narrowing must show up here).

- [ ] **Step 12: Final commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs(sp25): consigne la symbologie de l'éditeur de cartes
EOF
)"
```

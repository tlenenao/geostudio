## Task 10: Revue finale de branche et clôture

**Files:** none created/modified directly by this task's steps — it's a verification + CLAUDE.md documentation task.

**Interfaces:**
- Consumes: the combined state of Tasks 1-9.
- Produces: the CLAUDE.md entry documenting SP-26 (per this repo's established convention — every closed SP gets a `### Fait` bullet).

- [ ] **Step 1: Run the complete non-regression suite, both sides**

```bash
cd core
uv run pytest -q  # PostGIS réel — confirmer CORE_TEST_DATABASE_URL pointe vers un conteneur postgis-test up
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run mypy app/ || true
uv run lint-imports
uv run pytest --cov=app --cov-report=xml:coverage.xml -q
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell
npx vitest run --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run lint && npm run format:check && npm run build
npm run e2e
cd ..
uvx pre-commit run --all-files
```

Record the exact counts (test totals, coverage percentages) — compare against the Global Constraints baseline (1878/5/93%/108-2-0/161-1461/89.64%) and confirm growth is consistent with what each task added, no unexplained drop.

- [ ] **Step 2: Dispatch a fresh code-reviewer pass over the full branch diff**

Use this repo's established branch-final-review discipline (see CLAUDE.md's many `### Fait` entries: "revue finale de branche", 2-3 rounds until 0 Critical/Important). Diff the whole SP-26 range:

```bash
git log --oneline dev -- . | grep -c "SP-26\|feat(core)\|feat(deploy)\|test(shell)" # sanity check on commit count, adjust range below
git diff <first-sp26-commit>^..HEAD --stat
```

Focus areas specifically flagged by the spec's §7 as cross-task integration risks — check these explicitly, not just per-task correctness:
- Does Task 4's rate limiter's 429 response actually go through Task 3's `HTTPException` handler correctly (i.e., is the `application/problem+json` content-type really present on a live 429, not just asserted in the unit test)?
- Does Task 1's non-root `core`/`export-worker` still pass Task 3/4's new tests (`TestClient(create_app())`-based tests don't touch Docker at all, so this is really: does the *built image* still boot with the new middleware/handlers registered)? Run `docker run --rm geostudio-core-test python -c "from app.main import create_app; create_app()"` with `CORE_AUTH_MODE=mock` and `CORE_ENV=development` set, to confirm the non-root image boots with all of Tasks 2-4's changes present.
- Does Task 7's CSP, once enforcing, still allow whatever Task 6's `AppErrorBoundary` fallback UI needs to render (inline styles, if any — check the Tailwind classes used don't rely on injected `<style>` tags CSP would block)?

- [ ] **Step 3: Fix any findings, re-verify, then update `CLAUDE.md`**

Follow this repo's established pattern for a closed SP entry (see the SP-25 entry in the current `CLAUDE.md` for the exact level of detail/style expected: chantier-by-chantier summary, real defects found in review with their fix, exact final proof-of-exit numbers). Add the entry under `### Fait`, and update `### À venir` to remove Vague 3 as a pending item (note that Vague 4's remaining chantiers or Vague 5 become the next candidate — do not decide that here, just record SP-26 as closed).

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: consigne la clôture de SP-26 (durcissement avant v0.1 publique)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

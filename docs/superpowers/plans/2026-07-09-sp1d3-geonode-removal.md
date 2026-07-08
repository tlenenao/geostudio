# SP-1d.3 — Retrait GeoNode/Superset/Redis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove GeoNode, Superset, and Redis from the dev stack and the codebase — they've been dead weight since SP-1b/1c/1d.1 (the shell no longer calls GeoNode once `sp1d1-core-item-client` lands; nothing in this repo has ever called Superset or Redis from application code). Reach the roadmap's M1 "GeoNode-free" milestone.

**Architecture:** Pure removal — no new code. `docker-compose.yml` loses the `geonode`/`superset`/`redis` service blocks and the `redis-data` volume. `core/app/geonode.py` (and its two test files) are deleted — it has zero importers anywhere in `core/app/` today, confirmed by grep; it became dead code the moment SP-1b made item creation a local DB transaction instead of a GeoNode API call, and nothing has referenced it since. `.env.example`/README are updated to match reality.

**Tech Stack:** No change — this plan only deletes.

## Global Constraints

- **Prerequisite:** `sp1d1-core-item-client` must be merged first (or at least its GeoNode-calling code must already be gone from `shell/src/api/itemClient.ts`) — otherwise removing the `geonode` service would break the shell mid-flight. Verify with `grep -rn "geonodeUrl\|VITE_GEONODE_URL" shell/src shell/*.config.ts` returning empty before starting Task 1.
- **Spec discrepancy, flagged not silently resolved:** the SP-1d design spec's acceptance criterion (§7) lists the exact expected service set after removal as "shell, core, postgis, minio, martin, titiler, keycloak, traefik, pgbouncer" (9 services) — this omits `pg-featureserv`, which is very much alive and actively used (the shell's `listLayerSources`/`queryDataSource`/`featuresUrl` — see `sp1d1-core-item-client`'s plan — talk to it directly for feature-layer data, unrelated to GeoNode). Removing it would break working functionality the same SP-1d sub-phase depends on. This plan treats the spec's 9-service list as an incomplete enumeration (an oversight, not a deliberate exclusion) and verifies **10** services remain: the 9 listed plus `pg-featureserv`. Flag this discrepancy explicitly in the final report rather than silently matching the spec's literal count.
- No backfill/migration concern — `redis`/`superset`/`geonode` never held any data this repo's own code reads back (GeoNode was an external item registry SP-1b already fully replaced; Superset/Redis were never wired to anything in `core/`or `shell/`).
- `MARTIN_SECRET` in `.env.example` is a pre-existing orphaned variable (not referenced anywhere in `docker-compose.yml` today) — this is unrelated pre-existing drift, not introduced by GeoNode/Superset/Redis, and out of scope for this plan. Do not touch it.

---

### Task 1: Remove GeoNode/Superset/Redis from `docker-compose.yml` and `.env.example`

**Files:**
- Modify: `docker-compose.yml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nothing.
- Produces: `docker compose config --services` lists exactly 10 services (see Global Constraints): `postgis`, `pgbouncer`, `minio`, `martin`, `titiler`, `pg-featureserv`, `core`, `keycloak`, `shell`, `traefik`.

- [ ] **Step 1: Verify the prerequisite — no shell code still references GeoNode**

Run: `grep -rn "geonodeUrl\|VITE_GEONODE_URL\|VITE_BUILDER_URL" shell/src shell/*.config.ts shell/Dockerfile 2>/dev/null`
Expected: no output. If this finds anything, **stop** — `sp1d1-core-item-client` hasn't fully landed yet; removing the `geonode`/GeoNode-adjacent service now would break the running shell.

- [ ] **Step 2: Remove the `redis`, `superset`, `geonode` service blocks and the `redis-data` volume**

In `docker-compose.yml`:
- Delete the `redis-data:` line from the top-level `volumes:` block.
- Delete the entire `# ─── Cache ─────...` comment header and `redis:` service block (lines defining `redis`).
- Delete the entire `superset:` service block.
- Delete the entire `geonode:` service block.
- Delete the stale comment directly above the `core:` service block (it references `GEONODE_BASE_URL`/`GEONODE_TOKEN`/`GeoNodeItemClient`, none of which exist anywhere in `core/app/` — confirmed by grep in this plan's research):
  ```
  # Cœur GeoStudio (ex builder-service, renommé — arbitrage A14 de la feuille
  # de route). Set GEONODE_BASE_URL and GEONODE_TOKEN env vars to enable real
  # GeoNode item creation via GeoNodeItemClient; without them the in-memory
  # stub is used.
  ```
  Replace it with a one-line comment reflecting current reality:
  ```
  # Cœur GeoStudio (ex builder-service, renommé — arbitrage A14 de la feuille de route).
  ```
- In the `superset:` service's `depends_on`, note it referenced `redis: condition: service_healthy` — this entire block is being deleted anyway, so no dangling reference is left elsewhere (double-check with Step 4's grep).

- [ ] **Step 3: Remove Superset's env var from `.env.example`**

Delete this block from `.env.example`:
```
# ─── Apache Superset (BI spatiale) ───────────────────────
# Générer avec : openssl rand -base64 48
SUPERSET_SECRET=remplacez-par-une-cle-aleatoire-de-64-caracteres
```

- [ ] **Step 4: Verify no dangling reference remains**

Run: `grep -n "redis\|superset\|geonode" docker-compose.yml .env.example`
Expected: no output (case-insensitive check too: `grep -ni "redis\|superset\|geonode" docker-compose.yml .env.example` should also be empty).

- [ ] **Step 5: Validate the compose file and service list**

Run:
```bash
docker compose config --services | sort
```
Expected output (exactly these 10 lines, per this plan's Global Constraints discrepancy note):
```
core
keycloak
martin
minio
pg-featureserv
pgbouncer
postgis
shell
titiler
traefik
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "chore: remove GeoNode, Superset, and Redis from the dev stack"
```

---

### Task 2: Delete dead `core/app/geonode.py` and its tests

**Files:**
- Delete: `core/app/geonode.py`
- Delete: `core/tests/test_geonode.py`
- Delete: `core/tests/test_geonode_http.py`

**Interfaces:**
- Consumes: nothing (confirmed zero importers via `grep -rln "app.geonode\|from app import geonode\|import geonode" core/ --include="*.py"` returning empty except the module and its own tests).
- Produces: nothing — pure deletion.

- [ ] **Step 1: Confirm zero importers one more time (defensive re-check before deleting)**

Run: `cd core && grep -rln "geonode" app/ --include="*.py" | grep -v "app/geonode.py"`
Expected: no output. If this finds a real importer that wasn't there when this plan was written, **stop** and investigate — something changed since this plan's research and blind deletion would break it.

- [ ] **Step 2: Delete the files**

```bash
git rm core/app/geonode.py core/tests/test_geonode.py core/tests/test_geonode_http.py
```

- [ ] **Step 3: Run the full core test suite**

Run: `cd core && uv run pytest`
Expected: PASS, test count drops by exactly the number of tests that were in `test_geonode.py`/`test_geonode_http.py` (nothing else references them).

- [ ] **Step 4: Run import-linter**

Run: `cd core && uv run lint-imports`
Expected: PASS, contract unaffected (the layering contract's `app.*` list never included `app.geonode` as a named layer — it was always outside the layered contract, a leaf utility module).

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(core): delete dead app/geonode.py (no importers since SP-1b)"
```

---

### Task 3: Update README to match the reduced stack

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing.
- Produces: README's service list and M1 milestone description reflect the actual current state (GeoNode/Superset/Redis gone, not "en sursis").

- [ ] **Step 1: Update the "Ce qui existe aujourd'hui" stack bullet**

Change:
```markdown
- **`docker-compose.yml`** — la stack de dev : PostGIS, PgBouncer, MinIO, Martin,
  TiTiler, pg_featureserv, Keycloak, Traefik, cœur, shell — plus GeoNode, Superset
  et Redis, **en sursis** (retirés au jalon M1 de la feuille de route).
```
to:
```markdown
- **`docker-compose.yml`** — la stack de dev : PostGIS, PgBouncer, MinIO, Martin,
  TiTiler, pg_featureserv, Keycloak, Traefik, cœur, shell. GeoNode, Superset et
  Redis sont sortis (jalon M1).
```

- [ ] **Step 2: Update the M1 milestone row**

Change:
```markdown
| **M1 GeoNode-free** | Items/partage/publication dans le cœur ; GeoNode, Superset, Redis sortent |
```
to:
```markdown
| **M1 GeoNode-free** ✅ | Items/partage/publication dans le cœur ; GeoNode, Superset, Redis sortis |
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for the GeoNode-free stack (M1)"
```

---

### Task 4: Full stack smoke test

**Files:** none (verification only).

- [ ] **Step 1: Bring up the full reduced stack**

Run:
```bash
docker compose up -d
docker compose ps
```
Expected: exactly 10 services running (per Task 1's list), no `geonode`/`superset`/`redis` container appears at all.

- [ ] **Step 2: Run the shell's full test suite and e2e against the reduced stack's assumptions**

Run:
```bash
cd shell && npm test && npm run e2e
```
Expected: PASS — the e2e specs never talked to a real `geonode`/`superset`/`redis` container anyway (they run against Playwright's `page.route()` interception, per `sp1d1-core-item-client`'s Task 4), so removing these services from `docker-compose.yml` has no effect on them; this step exists to catch any accidental regression, not because it specifically exercises the removal.

- [ ] **Step 3: Run the core's full test suite**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: PASS.

- [ ] **Step 4: Tear down**

Run: `docker compose down`

- [ ] **Step 5: Final grep for any remaining GeoNode/Superset/Redis reference anywhere in the repo**

Run: `grep -rniL "node_modules\|\.git" -e "geonode\|superset" . 2>/dev/null; grep -rni "geonode\|superset" --include="*.md" --include="*.yml" --include="*.py" --include="*.ts" --include="*.tsx" . 2>/dev/null | grep -v node_modules | grep -v "docs/vision\|docs/archive\|docs/superpowers"`
Expected: no output (excluding historical docs under `docs/vision`/`docs/archive`/`docs/superpowers`, which are dated records of past decisions and legitimately still mention GeoNode as prior context — those are not code and not in scope for this cleanup).

No commit for this task — it's verification only, folding into the prior three tasks' commits.

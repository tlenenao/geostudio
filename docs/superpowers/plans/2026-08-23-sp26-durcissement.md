# Durcissement avant v0.1 publique (SP-26) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the 7 open chantiers of Vague 3 ("durcissement avant v0.1 publique") from `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, per the design in `docs/superpowers/specs/2026-08-23-sp26-durcissement-design.md`.

**Architecture:** No new subsystem — each chantier is a narrow, mostly independent hardening change to existing modules: a boot-time guard (`core/app/main.py`), a global FastAPI exception handler + one new shared exception class (`core/app/errors.py`), an in-memory rate-limit middleware (`core/app/ratelimit/`), a `SIGTERM` handler in the CDC worker's own entrypoint, a root-level React `ErrorBoundary`, `USER` directives across 7 of 8 Dockerfiles (`postgis` verified, not forced), Traefik/nginx security headers, Grafana alerting provisioning files, and one new CI job exercising real OIDC end-to-end.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy (core), React/TypeScript/Vite (shell), Playwright (E2E), Traefik v3 (prod ingress), Grafana (via `grafana/otel-lgtm`), Docker/docker-compose, GitHub Actions.

## Global Constraints

- **3.2 (clé maître au démarrage, in the source plan d'action document's own numbering) is already done** — do not touch `core/app/main.py:101`'s `secrets_crypto.load_master_key()` call or `core/app/secrets/crypto.py`. Not a task in this plan. **Numbering note:** the spec renumbers the remaining 7 chantiers as 3.1, 3.3, 3.4, 3.5a/3.5b/3.5c, 3.6, 3.7, 3.8 — the source document's own "3.5" bundles three independent mechanisms (RFC 7807 error format / `cdc-worker` graceful shutdown / `ErrorBoundary`) under one line, split here into 3.5a/3.5b/3.5c. Task titles below use this spec numbering, not sequential 3.1-3.9.
- **RFC 7807 shape, locked in the spec (§3.5a/§4.4):** `{type, title, status, detail}` at the top level; structured validation errors move to a new top-level `errors` extension member (list of `{field, code, message}`), never nested under `detail`. `detail` stays a plain string everywhere.
- **CSP `script-src` stays `'self'`, no per-extension-origin allowlist.** Do not build dynamic CSP generation from `GET /extensions`. Out of scope, explicitly (spec §2).
- **Rate limiting is per-process, in-memory, keyed by the raw `Authorization` header value** (not a verified user id — avoids re-implementing JWT/DB user resolution inside a low-level ASGI middleware that runs before FastAPI dependency injection). Documented limitation: does not survive multiple `core` replicas. No Redis, no new infra dependency.
- **DuckDB/QGIS profile directories must survive the switch to a non-root container user.** Any Dockerfile that runs `duckdb`'s `INSTALL`/`LOAD` or `qgis_process` at build time must pin `ENV HOME=<fixed path>` **before** that build step, and must not change `HOME` when switching to the runtime `USER` — same directory, readable (not necessarily writable) by the runtime user.
- **`postgis`'s Dockerfile is not touched by default.** Task 1 verifies empirically whether the official Postgres image drops privileges from its own entrypoint; only add `USER postgres` if that verification shows it's actually needed and safe.
- **Every new environment variable this plan introduces (`CORE_ENV`, `GRAFANA_ALERT_WEBHOOK_URL`) must be wired into at least one service's `environment:` block in `docker-compose.yml` AND documented in `.env.example`** — `core/tests/test_deployability.py::test_every_core_env_var_is_wired_to_a_service` and `::test_every_compose_substitution_is_documented` enforce this and must stay green throughout.
- **Non-regression baseline to preserve at every task boundary** (measured 2026-08-23, end of SP-25): core `uv run pytest` (PostGIS real, `postgis-test` container) → 1878 passed, 5 skipped, 0 failed, coverage ≥93% (threshold in `core/.coverage-threshold` is 85); `ruff check`/`ruff format --check`/`mypy --strict app/auth app/secrets app/analytics app/copilot`/`lint-imports` green; shell `npx vitest run` → 161 files / 1461 tests, coverage ≥89.64% (threshold in `shell/.coverage-threshold` is 88); `npm run lint`/`format:check`/`build` green; `npm run e2e` → 108 passed, 4 skipped, 0 failed; `core/tests/test_deployability.py` → 31/31; `uvx pre-commit run --all-files` → 5/5.
- **Every task that touches a route response shape, an env var, a Dockerfile `CMD`/`ENTRYPOINT`, or `docker-compose.yml` must be verified against the *running* artifact** (a real `docker run`/`docker compose up`/`TestClient` call), not just read from source — this repo's CLAUDE.md documents four prior incidents (SP-17a, SP-17b, tileset3d, `CORE_ETL_ENABLED`) where a capability was implemented and tested but never actually reachable in the packaged stack.
- **Commits are conventional** (`feat(core): …`, `fix(shell): …`, `test(core): …`), one subject each, in French prose for comments/commit bodies per this repo's convention — code identifiers stay in English.
- **Regenerate OpenAPI + TS types** (`core/scripts/export_openapi.py` via the CI incantation: `PYTHONPATH=. CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= uv run python scripts/export_openapi.py openapi.json` from `core/`, then `npm run gen:api-types` from `shell/`) whenever an HTTP response shape changes (Task 3's RFC 7807 handler changes the error body shape for every route — this WILL show a diff, unlike capabilities gated behind a disabled flag).

---

## Task 1: Conteneurs non-root (3.6)

**Files:**
- Modify: `core/Dockerfile`
- Modify: `deploy/export-worker/Dockerfile`
- Modify: `deploy/appexport-runtime-builder/Dockerfile`
- Modify: `deploy/appexport-standalone/Dockerfile`
- Modify: `deploy/qgis-worker/Dockerfile`
- Modify: `deploy/backup/Dockerfile`
- Modify: `shell/Dockerfile`
- Test: manual `docker build`/`docker run` verification (no pytest/vitest — these are Dockerfile-only changes; `core/tests/test_deployability.py` doesn't inspect Dockerfile internals, only compose wiring)

**Interfaces:**
- Consumes: nothing from other tasks (this task is first per the spec's risk-ordered sequencing, §5).
- Produces: nothing consumed by later tasks — Task 2 onward touch application code, not Dockerfiles.

**Context:** `core/Dockerfile:17-24` bakes DuckDB extensions (`httpfs`, `spatial`, `h3`) into `~/.duckdb/extensions` at build time specifically so `core/app/analytics/duckdb_conn.py`'s `INSTALL`/`LOAD` calls at every connection never hit the network at runtime. The file's own comment says this only works because build and runtime currently share the same user (root), hence the same `$HOME`. Switching to a non-root runtime user without addressing this breaks offline/egress-restricted deployments — verify this doesn't regress before moving on. `deploy/qgis-worker/Dockerfile:16` has the same shape of problem for the GRASS plugin profile (`qgis_process plugins enable grassprovider` writes into a profile directory keyed by `$HOME`).

- [ ] **Step 1: Pin `HOME` in `core/Dockerfile` before the DuckDB install step, create a non-root user, verify extensions survive**

Edit `core/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

# Utilisateur non-root (SP-26/3.6) — créé avant l'installation des
# extensions DuckDB : HOME doit être fixé ET rester identique entre le
# build (encore root ici) et l'exécution (USER app plus bas), sinon DuckDB
# ne retrouve plus ~/.duckdb/extensions à l'exécution et retente un
# INSTALL réseau — cf. commentaire historique juste en dessous.
RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home

COPY pyproject.toml ./
# Installe directement depuis [project.dependencies] de pyproject.toml (pas
# de [build-system] dans ce fichier, donc `uv pip install -r pyproject.toml`
# ne fait qu'installer les dépendances listées, sans tenter de construire/
# installer le paquet geostudio-core lui-même). Remplace une liste dupliquée
# à la main qui avait dérivé à plusieurs reprises (alembic/pyjwt/boto3/
# python-multipart/mcp puis defusedxml, chacun crash-loopant le conteneur au
# premier import manquant) — une seule source de vérité désormais.
RUN uv pip install --system --no-cache -r pyproject.toml

# Pré-installe les extensions DuckDB httpfs/spatial (SP-11b, module
# app/analytics/duckdb_conn.py) sur le disque de l'image, au build — sans
# quoi le premier POST /collections/{id}/aggregate en runtime déclencherait
# un INSTALL réseau vers extensions.duckdb.org, qui échoue en déploiement
# à égress restreint/air-gapped. Toujours root ici (HOME fixé ci-dessus,
# écrit dans /opt/geostudio-home) ; USER app plus bas réutilise le même
# HOME, donc le même répertoire d'extensions (~/.duckdb/extensions).
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

RUN chown -R app:app /opt/geostudio-home /app
USER app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

- [ ] **Step 2: Build and verify `core` runs non-root and DuckDB works offline**

```bash
cd core
docker build -t geostudio-core-test .
docker run --rm geostudio-core-test id -u
# Expected: a non-zero uid (the `app` system user's assigned uid)
docker run --rm --network none geostudio-core-test python -c "
from app.analytics.duckdb_conn import open_spatial_connection
conn = open_spatial_connection()
print(conn.execute('SELECT ST_AsText(ST_Point(1,2))').fetchone())
"
# Expected: prints the WKT point, no network error — proves the spatial
# extension was found locally under /opt/geostudio-home, not re-downloaded.
```

If the second command fails with a network/download error, the `HOME`/ownership wiring is wrong — fix before continuing (do not skip this check; this is exactly the deployment-breaking regression the spec flags in §3.6).

- [ ] **Step 3: Apply the identical `HOME`-pinning + non-root pattern to `deploy/export-worker/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -r pyproject.toml
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL httpfs'); c.execute('INSTALL spatial'); c.execute('INSTALL h3 FROM community')"
RUN python -m playwright install --with-deps chromium

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

# Playwright/Chromium écrit son cache sous $HOME/.cache par défaut au
# premier lancement si absent — installé ci-dessus alors que HOME est déjà
# fixé, donc déjà sous /opt/geostudio-home. chown après tous les COPY/RUN
# précédents pour couvrir le cache Chromium en plus des extensions DuckDB.
RUN chown -R app:app /opt/geostudio-home /app
USER app

CMD ["python", "-m", "procrastinate", "--app", "app.jobs.app", "worker", "-q", "export"]
```

Verify:

```bash
cd deploy/export-worker
docker build -t geostudio-export-worker-test -f Dockerfile ../../core
docker run --rm geostudio-export-worker-test id -u
# Expected: non-zero uid
```

(If the build context needs to be the repo root rather than `core/` — check the actual `build:` context declared for `export-worker` in `docker-compose.yml` first with `grep -A3 "export-worker:" docker-compose.yml` and match it; do not guess the context path.)

- [ ] **Step 4: Non-root for `deploy/appexport-standalone/Dockerfile` (python stage) — same DuckDB pattern, single extension**

Edit the second (`python:3.12-slim`) stage:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --home-dir /opt/geostudio-home --create-home app
ENV HOME=/opt/geostudio-home
RUN pip install --no-cache-dir fastapi 'uvicorn[standard]' pydantic duckdb sqlalchemy
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL spatial')"
COPY core/app ./app
COPY --from=shell-runtime /build/dist-export /runtime
ENV APPEXPORT_STANDALONE_DATA_DIR=/data
ENV APPEXPORT_STANDALONE_RUNTIME_DIR=/runtime
RUN mkdir -p /data && chown -R app:app /opt/geostudio-home /app /data
USER app
EXPOSE 8000
CMD ["uvicorn", "app.appexport.miniserver.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`/data` is created and chowned explicitly because it's normally supplied as a mounted volume at runtime (per the file's own comment: "montées au runtime via le volume /data") — a bind mount can arrive owned by the host uid, but the `mkdir -p /data` here only matters for the image-baked default; document this as a known limitation if a real volume mount ends up owned differently (verify in Step 7 below).

- [ ] **Step 5: Non-root for `deploy/appexport-runtime-builder/Dockerfile` (one-shot build container, no listening service, still worth hardening)**

```dockerfile
FROM node:20-slim
WORKDIR /build
RUN groupadd --system builder && useradd --system --gid builder --create-home builder
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
RUN mkdir -p /export-runtime && chown -R builder:builder /build /export-runtime
USER builder
CMD ["sh", "-c", "mkdir -p /export-runtime && cp -r dist-export/* /export-runtime/ && echo 'export runtime built'"]
```

This container writes into a shared Docker volume mounted at `/export-runtime` (per `docker-compose.yml`'s `appexport-runtime-builder` service) — if that volume is fresh (no prior owner), the non-root `builder` user can write to it; if it was previously populated by a root-run container, the `chown` in the `CMD` step (already `mkdir -p` + no explicit chown in the runtime command) may fail on permission. Verify in Step 7.

- [ ] **Step 6: Non-root for `deploy/qgis-worker/Dockerfile` — pin `HOME` before the GRASS plugin enable step**

```dockerfile
# qgis/qgis:release-3_34 = QGIS 3.34.5 "Prizren" (LTR) — PAS :latest, qui
# pointe vers un build 4.3.0-Master instable (vérifié en design, §2).
FROM qgis/qgis:release-3_34

ENV QT_QPA_PLATFORM=offscreen

# HOME fixé avant l'activation du plugin GRASS (SP-26/3.6) : qgis_process
# écrit l'état "grassprovider activé" dans un profil sous $HOME/.local/
# share/QGIS/QGIS3/profiles/default — un HOME différent à l'exécution
# (non-root) le verrait désactivé, cassant silencieusement tous les
# grass7:* de l'allowlist figée (core/app/pipelines/ops/
# qgis_algorithms.json). Même mécanisme que core/Dockerfile pour DuckDB.
RUN groupadd --system qgis && useradd --system --gid qgis --home-dir /opt/qgis-home --create-home qgis
ENV HOME=/opt/qgis-home

RUN qgis_process plugins enable grassprovider

COPY server.py /app/server.py
COPY allowlist.txt /app/allowlist.txt

COPY LICENSE-QGIS.md /LICENSE-QGIS.md
LABEL org.opencontainers.image.licenses="GPL-2.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Sidecar QGIS Processing pour GeoStudio — contient QGIS et GRASS (GPL). Voir /LICENSE-QGIS.md."

RUN mkdir -p /scratch && chown -R qgis:qgis /opt/qgis-home /app /scratch
USER qgis

CMD ["python3", "/app/server.py"]
```

`/scratch` is created explicitly: `runtime.py` (core side) materializes GeoPackages into a `/scratch` volume shared with this container (per CLAUDE.md's SP-15d entry: "`/scratch` inscriptible"). Verify the mount point name against the actual compose service definition (`grep -A10 "qgis-worker:" docker-compose.yml`) before assuming `/scratch` is correct — adjust if the real mount path differs.

Verify: `docker build -t geostudio-qgis-worker-test deploy/qgis-worker && docker run --rm geostudio-qgis-worker-test qgis_process plugins list 2>&1 | grep -i grass` — expect the grass provider listed as enabled, proving the profile survived the `USER` switch (this check runs at the default `USER qgis`, exactly the runtime condition).

- [ ] **Step 7: Non-root for `deploy/backup/Dockerfile` (Alpine, no Python/DuckDB concerns) and `shell/Dockerfile` (nginx)**

`deploy/backup/Dockerfile`:

```dockerfile
# SPDX-License-Identifier: Apache-2.0
FROM alpine:3.20

RUN apk add --no-cache postgresql16-client age curl jq bash tzdata python3 \
  && curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
  && chmod +x /usr/local/bin/mc

COPY backup.sh /usr/local/bin/backup.sh
COPY retention.py /usr/local/bin/retention.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh

COPY LICENSE-BACKUP.md /LICENSE-BACKUP.md
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Image de sauvegarde GeoStudio (pg_dump chiffré age + rétention -> S3/MinIO) — contient le client MinIO mc (AGPL). Voir /LICENSE-BACKUP.md."

RUN addgroup -S backup && adduser -S -G backup -h /home/backup backup

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

Do **not** add `USER backup` here yet — check first whether `backup.sh`/`entrypoint.sh` write to paths owned by root (e.g. `/tmp` dump staging, `age` key files mounted read-only, `mc` config under `$HOME/.mc`). Run:

```bash
docker build -t geostudio-backup-test deploy/backup
docker run --rm --entrypoint sh geostudio-backup-test -c "grep -n 'mkdir\|>.*\.mc\|HOME' /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh"
```

If it writes under `$HOME`, add `ENV HOME=/home/backup` before `USER backup` (same pattern as above) and `RUN chown -R backup:backup /home/backup`; if it writes under `/tmp` only, `/tmp` is world-writable by default in most base images (verify with `docker run --rm alpine:3.20 sh -c "stat -c %a /tmp"` — expect `1777`) and no extra chown is needed. Then add `USER backup` before `ENTRYPOINT`. Rebuild and run `docker run --rm geostudio-backup-test id -u` (via `--entrypoint id -u`, since the image's own entrypoint isn't `id`) to confirm non-zero.

`shell/Dockerfile`:

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_CORE_URL=http://localhost:8200
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/geostudio
ARG VITE_OIDC_CLIENT_ID=geostudio-shell
ARG VITE_OIDC_REDIRECT_URI=http://localhost:8300/
ENV VITE_CORE_URL=$VITE_CORE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY env-config.template.js /usr/share/nginx/html/env-config.template.js
COPY docker-entrypoint.d/40-render-runtime-config.sh /docker-entrypoint.d/40-render-runtime-config.sh
# nginx:alpine crée déjà un utilisateur système `nginx` (uid/gid 101) pour
# ses workers — réutilisé directement plutôt qu'un nouvel utilisateur.
# /usr/share/nginx/html doit rester inscriptible par cet utilisateur :
# 40-render-runtime-config.sh y écrit env-config.js à CHAQUE démarrage de
# conteneur (docker-entrypoint.d tourne avant que nginx ne serve), et ce
# script s'exécute désormais lui aussi sous USER nginx (plus root).
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx
USER nginx
EXPOSE 8300
```

Verify:

```bash
cd shell
docker build -t geostudio-shell-test .
docker run --rm -e VITE_CORE_URL=http://example.test -p 18300:8300 -d --name shell-nonroot-test geostudio-shell-test
sleep 2
docker exec shell-nonroot-test id -u
# Expected: 101 (nginx uid), not 0
curl -s http://localhost:18300/env-config.js | grep example.test
# Expected: the substituted value present — proves 40-render-runtime-config.sh
# succeeded as non-root (wrote env-config.js into the html dir)
docker logs shell-nonroot-test
# Expected: no permission-denied errors in the entrypoint log
docker rm -f shell-nonroot-test
```

If `nginx.conf`'s `listen 8300;` triggers a "permission denied" (some alpine base images still restrict certain low port ranges even >1024 depending on kernel `net.ipv4.ip_unprivileged_port_start` on the host, unlikely at 8300 but verify empirically rather than assume) — fall back to setting `net.ipv4.ip_unprivileged_port_start=0` is a host-level concern, not a Dockerfile fix; if this occurs, document it as a known limitation rather than silently reverting to root.

- [ ] **Step 8: Verify whether `postgis`'s official image actually needs root — do not blindly add `USER`**

```bash
docker build -t geostudio-postgis-test deploy/postgis
docker run -d --name postgis-nonroot-check -e POSTGRES_PASSWORD=test geostudio-postgis-test
sleep 5
docker exec postgis-nonroot-check ps aux | grep postgres
docker logs postgis-nonroot-check 2>&1 | tail -30
docker rm -f postgis-nonroot-check
```

Read the `ps aux` output: if the `postgres` server process itself (not just the entrypoint wrapper) runs under the `postgres` uid already (the official image's entrypoint does this via its own internal `gosu`/gosu-equivalent mechanism after fixing volume ownership as root), this chantier is **already satisfied for `postgis` without any Dockerfile change** — the *container* starts as root (uid 0 visible via `docker run --rm <image> id -u` on the raw image before any custom command overrides it), but the actual long-running server process drops to `postgres`. Document this precisely in the commit message and in the plan's final report: `docker run --rm geostudio-postgis-test id -u` will show `0`, but that's the entrypoint wrapper, not the server — the meaningful process-level check is the `ps aux` output above. Do **not** add a Dockerfile `USER postgres` directive; doing so removes the entrypoint's ability to `chown`-fix a fresh `PGDATA` volume on first run, which is a real regression (first-boot failure on an empty volume).

- [ ] **Step 9: Commit**

```bash
git add core/Dockerfile deploy/export-worker/Dockerfile deploy/appexport-runtime-builder/Dockerfile deploy/appexport-standalone/Dockerfile deploy/qgis-worker/Dockerfile deploy/backup/Dockerfile shell/Dockerfile
git commit -m "$(cat <<'EOF'
feat(deploy): fait tourner 7 des 8 conteneurs en utilisateur non-root

core/export-worker/appexport-standalone pinnent HOME avant l'installation
des extensions DuckDB pour ne pas perdre le cache local à l'exécution ;
qgis-worker fait de même pour le profil GRASS ; shell réutilise
l'utilisateur nginx existant ; postgis vérifié déjà non-root au niveau
process serveur (entrypoint officiel), non modifié.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Interdire le mode mock hors développement (3.1)

**Files:**
- Modify: `core/app/main.py` (add boot guard call in `create_app()`)
- Modify: `core/app/auth/dependency.py` (add `_reject_mock_outside_development()` next to `_mock_mode()`)
- Modify: `core/tests/conftest.py` (add `CORE_ENV` default, mirroring the existing `CORE_SECRETS_MASTER_KEY` default)
- Modify: `docker-compose.yml` (add `CORE_ENV: ${CORE_ENV:-development}` to the `core` service)
- Modify: `.env.example` (document `CORE_ENV`)
- Test: `core/tests/test_mock_mode_guard.py` (new)

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: nothing consumed by later tasks in this plan (Task 3's RFC 7807 handler and Task 4's rate limiter don't depend on this guard).

**Context:** `core/app/auth/dependency.py:16-17` defines `_mock_mode()`, read per-request by `get_current_user`. `core/app/main.py:99-101` is `create_app()`'s first two lines — `observability.setup()` then the existing `secrets_crypto.load_master_key()` fail-fast call. The new guard goes immediately after, same style. `core/tests/conftest.py:19` already does `os.environ.setdefault("CORE_SECRETS_MASTER_KEY", ...)` specifically so every test calling `create_app()` doesn't need to set it explicitly — `CORE_ENV` needs the identical treatment or every one of the dozens of `env()`-fixture test files across the suite that call `create_app()` with `CORE_AUTH_MODE=mock` (the default when unset) will start failing at collection/setup time.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_mock_mode_guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.main import create_app


def test_mock_mode_without_development_marker_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.delenv("CORE_ENV", raising=False)
    with pytest.raises(RuntimeError, match="CORE_AUTH_MODE=mock requires CORE_ENV=development"):
        create_app()


def test_mock_mode_with_development_marker_boots(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ENV", "development")
    create_app()  # doit ne pas lever


def test_oidc_mode_boots_regardless_of_core_env(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.delenv("CORE_ENV", raising=False)
    create_app()  # doit ne pas lever : la garde ne concerne que le mode mock
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd core
uv run pytest tests/test_mock_mode_guard.py -v
```

Expected: `test_mock_mode_without_development_marker_refuses_to_boot` FAILS (no `RuntimeError` raised — `create_app()` currently boots fine in mock mode with no `CORE_ENV` check). The other two currently PASS already (nothing to break yet), which is fine — only the first assertion is new behavior.

- [ ] **Step 3: Implement the guard**

Edit `core/app/auth/dependency.py`, immediately after `_mock_mode()`:

```python
def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def reject_mock_outside_development() -> None:
    """Appelée une fois au démarrage (create_app()), pas par requête —
    contrairement à _mock_mode() ci-dessus. C6 (revue de projet 2026-08-20) :
    CORE_AUTH_MODE=mock donne bootstrap_admin=True à quiconque présente un
    Bearer non vide (cf. get_current_user plus bas), sans aucune vérification
    d'environnement jusqu'ici. CORE_ENV=development est un marqueur explicite,
    pas une valeur par défaut sûre — un déploiement qui omet CORE_ENV ET met
    CORE_AUTH_MODE=mock est traité comme une erreur de configuration,
    jamais comme "sans doute du dev"."""
    if _mock_mode() and os.environ.get("CORE_ENV") != "development":
        raise RuntimeError("CORE_AUTH_MODE=mock requires CORE_ENV=development")
```

Edit `core/app/main.py`:

```python
def create_app() -> FastAPI:
    observability.setup()
    secrets_crypto.load_master_key()  # échec rapide si absente/mal formée (design SP-15e §4/§8)
    reject_mock_outside_development()  # échec rapide si mock hors dev (design SP-26 §3.1)
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
```

Add the import near the existing `from app.auth.dependency import (...)` block in `main.py`:

```python
from app.auth.dependency import (
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
    reject_mock_outside_development,
)
```

- [ ] **Step 4: Add the conftest default so the rest of the suite doesn't break**

Edit `core/tests/conftest.py`, right after the existing `CORE_SECRETS_MASTER_KEY` default:

```python
os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
# Même raison, même patron (SP-26/3.1) : create_app() refuse désormais de
# démarrer en CORE_AUTH_MODE=mock (le défaut de _mock_mode() quand la
# variable est absente) sans CORE_ENV=development. setdefault() : un test
# qui monkeypatch.setenv("CORE_ENV", ...) explicitement reste maître de sa
# propre valeur (ex. test_mock_mode_guard.py ci-dessus).
os.environ.setdefault("CORE_ENV", "development")
```

- [ ] **Step 5: Run the new test file and the full suite**

```bash
cd core
uv run pytest tests/test_mock_mode_guard.py -v
# Expected: 3 passed
uv run pytest -x -q
# Expected: 1878+3 passed (1881), 5 skipped, 0 failed — no regression
# elsewhere from the conftest.py change
```

If any pre-existing test fails, it's calling `create_app()` after an explicit `monkeypatch.delenv("CORE_ENV", ...)` or in a fixture that clears the environment wholesale — find that fixture and add `monkeypatch.setenv("CORE_ENV", "development")` there rather than weakening the guard.

- [ ] **Step 6: Wire `CORE_ENV` into the dev compose and document it**

Edit `docker-compose.yml`, in the `core` service's `environment:` block, right after `CORE_AUTH_MODE`:

```yaml
      CORE_AUTH_MODE: ${CORE_AUTH_MODE:-mock}
      # Marqueur explicite requis par la garde de démarrage SP-26/3.1 :
      # CORE_AUTH_MODE=mock sans CORE_ENV=development refuse de démarrer.
      # docker-compose.prod.yml force déjà CORE_AUTH_MODE=oidc sans
      # indirection par variable — cette garde n'y a donc jamais l'occasion
      # de se déclencher, c'est un filet pour tout déploiement du fichier
      # de base seul, sans l'overlay prod.
      CORE_ENV: ${CORE_ENV:-development}
```

Edit `.env.example`, right after the existing `CORE_AUTH_MODE` block:

```
# ─── Cœur : mode d'authentification ──────────────────────
# "mock" pour dev/e2e (aucun accès réseau à Keycloak requis) ; "oidc" en usage réel.
CORE_AUTH_MODE=mock
# Marqueur explicite requis quand CORE_AUTH_MODE=mock (SP-26/3.1) — le
# cœur refuse de démarrer sinon. Ne jamais mettre "development" sur une
# instance exposée publiquement.
CORE_ENV=development
CORE_OIDC_ISSUER=http://localhost:8180/realms/geostudio
```

- [ ] **Step 7: Verify the deployability guard still passes**

```bash
cd core
uv run pytest tests/test_deployability.py -v
```

Expected: 31 passed (`CORE_ENV` is now both wired to `core` and documented in `.env.example` — neither rule should regress).

- [ ] **Step 8: Commit**

```bash
git add core/app/main.py core/app/auth/dependency.py core/tests/conftest.py core/tests/test_mock_mode_guard.py docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(core): refuse de démarrer en mode mock hors CORE_ENV=development

CORE_AUTH_MODE=mock donnait bootstrap_admin=True à tout Bearer non vide
sans aucune vérification d'environnement (C6, revue de projet
2026-08-20). Garde fail-fast au boot, même emplacement/patron que
load_master_key().

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Format d'erreur unique RFC 7807 (3.5a)

**Files:**
- Create: `core/app/errors.py`
- Modify: `core/app/main.py` (register 3 exception handlers)
- Modify: `core/app/features/routes.py:107-108` (`_validation_error` reuses the new exception class)
- Modify: `core/app/harvest/routes.py` (6 inline `HTTPException(status_code=400, detail={"errors": [...]})` sites)
- Modify: `shell/src/api/itemClient.ts` (2 call sites: `requestFeatureWrite`, `requestAnalyticsSql`)
- Modify: `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` (regenerated)
- Test: `core/tests/test_error_format.py` (new), `core/tests/test_features_routes_write.py` (existing — verify still green with the new `errors` top-level shape), `shell/src/api/itemClient.test.ts` (existing — update 2 assertions)

**Interfaces:**
- Consumes: nothing from Tasks 1-2.
- Produces: `ValidationHTTPException(errors: list[dict], status_code: int = 400)` from `core/app/errors.py`, used by Task 4 (rate limiter) for its 429 responses.

**Context:** `core/app/features/routes.py:107-108` defines the single helper `_validation_error` used by 11 call sites in that file; `core/app/harvest/routes.py` has 6 more sites constructing the identical `HTTPException(status_code=400, detail={"errors": [...]})` shape inline (`live_query.ArcgisQueryError` handling). `core/app/errors.py` is a new standalone module, following the precedent of `core/app/db.py`/`core/app/observability.py` — top-level modules **not** listed in `[tool.importlinter]`'s `layers` in `core/pyproject.toml`, so both `app.features` and `app.harvest` (different, non-adjacent layers) can import it without any layer-contract change.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_error_format.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def test_unhandled_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()

    @app.get("/__boom")
    def boom():
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == 500
    assert body["title"]
    assert body["detail"] == "internal server error"
    assert "kaboom" not in response.text  # jamais fuiter le message interne


def test_plain_http_exception_returns_problem_json(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app())
    response = client.get("/collections/does-not-exist/items/does-not-exist")
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["status"] == response.status_code
    assert isinstance(body["detail"], str)
    assert "errors" not in body  # pas de validation structurée sur ce chemin


def test_validation_exception_carries_top_level_errors(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app())
    response = client.post("/analytics/sql", json={"sql": "not valid sql at all"})
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert isinstance(body["detail"], str)  # jamais un dict désormais
    assert isinstance(body["errors"], list)
    assert body["errors"][0]["field"] == "sql"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd core
uv run pytest tests/test_error_format.py -v
```

Expected: all 3 FAIL — no `application/problem+json` content-type exists yet, and `/analytics/sql`'s current error body nests `errors` under `detail`, not at the top level.

- [ ] **Step 3: Create the shared exception class**

Create `core/app/errors.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Module bas de la pile (hors du contrat de couches import-linter, même
précédent que app.db/app.observability) : ValidationHTTPException est
importée à la fois par app.features et app.harvest, deux couches non
adjacentes du contrat — un module de contrat aurait dû se placer entre les
deux sans raison métier, donc il reste en dehors, comme app.db."""

from fastapi import HTTPException


class ValidationHTTPException(HTTPException):
    """HTTPException porteuse d'erreurs de validation structurées. Le corps
    RFC 7807 (main.py) les expose sous un membre d'extension `errors` au
    premier niveau — jamais imbriqué sous `detail`, qui reste une chaîne
    (design SP-26 §3.5a/§4.4, changement cassant assumé vis-à-vis de la
    forme précédente {"errors": [...]} nichée sous detail)."""

    def __init__(self, errors: list[dict], status_code: int = 400) -> None:
        super().__init__(status_code=status_code, detail="validation failed")
        self.errors = errors
```

- [ ] **Step 4: Register the three exception handlers in `main.py`**

Add near the top of `core/app/main.py`, after the existing imports:

```python
from http import HTTPStatus

from app.errors import ValidationHTTPException
```

Inside `create_app()`, after `app = FastAPI(...)` and `observability.instrument_app(app)` (before the existing `read_only_guard` middleware definition, order doesn't matter for exception handlers vs. middleware — FastAPI registers them independently):

```python
    @app.exception_handler(ValidationHTTPException)
    async def _validation_exception_handler(request: Request, exc: ValidationHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail,
                "errors": exc.errors,
            },
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail if isinstance(exc.detail, str) else "request failed",
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        observability.record_unhandled_exception(exc)  # cf. Step 4b ci-dessous
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
                "status": 500,
                "detail": "internal server error",
            },
        )
```

- [ ] **Step 4b: Check whether `observability.record_unhandled_exception` already exists before calling it**

```bash
cd core
grep -n "def record_unhandled_exception\|def.*exception" app/observability.py
```

If nothing matches, the unhandled-exception handler should NOT invent a new observability function speculatively — instead just log via the standard library and rely on OTel's existing FastAPI auto-instrumentation (`observability.instrument_app(app)`, already called, typically captures unhandled exceptions as span events automatically for `opentelemetry-instrumentation-fastapi`). Replace the call with:

```python
    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        import logging

        logging.getLogger("app.errors").exception("unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
                "status": 500,
                "detail": "internal server error",
            },
        )
```

Use whichever of the two forms matches what actually exists in `app/observability.py` — don't leave a call to a function you haven't confirmed exists.

- [ ] **Step 5: Convert `_validation_error` in `features/routes.py`**

Edit `core/app/features/routes.py:107-108`:

```python
def _validation_error(errors: list[dict], status: int = 400):
    return ValidationHTTPException(errors=errors, status_code=status)
```

Add the import near the top of the file:

```python
from app.errors import ValidationHTTPException
```

- [ ] **Step 6: Convert the 6 inline sites in `harvest/routes.py`**

For each of the 6 occurrences found by `grep -n '"errors":' core/app/harvest/routes.py` (lines 313, 363, 396, 425, 477, 524 as of this writing — re-check with the grep since line numbers shift as earlier steps land), replace the pattern:

```python
raise HTTPException(
    status_code=400,
    detail={
        "errors": [{"field": exc.field, "code": "invalid_filter", "message": exc.message}]
    },
) from exc
```

with:

```python
raise ValidationHTTPException(
    errors=[{"field": exc.field, "code": "invalid_filter", "message": exc.message}],
    status_code=400,
) from exc
```

Preserve each site's exact `errors` list content (some of the 6 have different shapes — check each one individually with `sed -n '<line>,<line+10>p' core/app/harvest/routes.py` before editing, don't assume they're identical to the one shown above). Add `from app.errors import ValidationHTTPException` to the file's imports; the plain `HTTPException` import stays if used elsewhere in the file (check with `grep -c "HTTPException(" core/app/harvest/routes.py` before removing the import).

- [ ] **Step 7: Run the new tests and the two existing route test files**

```bash
cd core
uv run pytest tests/test_error_format.py tests/test_features_routes_write.py tests/test_analytics_sql_routes.py tests/test_harvest_routes.py -v
```

Expected: all pass. If `test_features_routes_write.py` or `test_harvest_routes.py` has an existing assertion checking `response.json()["detail"]["errors"]` (the old nested shape), update it to `response.json()["errors"]` — grep first: `grep -n '\["detail"\]\["errors"\]\|detail.*errors' core/tests/test_features_routes_write.py core/tests/test_harvest_*.py` and fix each hit found.

- [ ] **Step 8: Update the shell's two call sites**

Edit `shell/src/api/itemClient.ts`'s `requestFeatureWrite` (around line 236 as of this writing — re-check with `grep -n "data?.detail?.errors" shell/src/api/itemClient.ts`):

```typescript
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { errors?: FieldError[] } | null;
    throw new FeatureValidationError(data?.errors ?? []);
  }
```

And `requestAnalyticsSql` (around line 290):

```typescript
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as {
      errors?: FieldError[];
    } | null;
    throw new SqlQueryError(data?.errors?.[0]?.message ?? "Requête SQL invalide.");
  }
```

The generic `!res.ok` branch in `requestFeatureWrite` (reading `data?.detail` as a string) stays unchanged — `detail` is still a plain string for every non-validation error path.

- [ ] **Step 9: Update the shell test file**

```bash
cd shell
grep -n "detail.*errors\|errors.*detail" src/api/itemClient.test.ts
```

Update any mock response fixture in that file from `{ detail: { errors: [...] } }` to `{ errors: [...] }` to match the new server shape. Run:

```bash
npx vitest run src/api/itemClient.test.ts
```

Expected: all pass.

- [ ] **Step 10: Regenerate OpenAPI + TS types**

```bash
cd core
PYTHONPATH=. CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8= uv run python scripts/export_openapi.py openapi.json
cd ../shell
npm run gen:api-types
git diff --stat -- ../core/openapi.json src/api/generated/core-schema.d.ts
```

Expected this time: a **non-empty** diff (unlike capability flags gated off in CI) — the global exception handler changes the documented error response shape for every route. Review the diff briefly to confirm it's limited to error-response schemas, not an unrelated drift.

- [ ] **Step 11: Run the full non-regression suite**

```bash
cd core
uv run pytest -x -q
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
cd ../shell
npx vitest run
npm run lint && npm run format:check && npm run build
```

Expected: no regressions vs. the Global Constraints baseline (core count grows by 3 new tests in `test_error_format.py`; shell count unchanged unless `itemClient.test.ts` gained assertions).

- [ ] **Step 12: Commit**

```bash
git add core/app/errors.py core/app/main.py core/app/features/routes.py core/app/harvest/routes.py core/tests/test_error_format.py core/openapi.json
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): format d'erreur RFC 7807 unique sur toute l'API

Handler d'exception global (application/problem+json) sur
HTTPException/Exception non gérée. Les erreurs de validation
structurées migrent vers un membre d'extension `errors` au premier
niveau, plus imbriquées sous `detail` — changement cassant scopé à 2
sites d'appel shell (ARC-04, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Rate limiting différencié (3.4)

**Files:**
- Create: `core/app/ratelimit/__init__.py`
- Create: `core/app/ratelimit/limiter.py`
- Modify: `core/app/main.py` (mount the middleware, define the 4 route-group regexes)
- Test: `core/tests/test_ratelimit.py` (new)

**Interfaces:**
- Consumes: `ValidationHTTPException`-style RFC 7807 shape from Task 3 for the 429 body (reuses the plain `HTTPException` path — a 429 isn't a validation error, so it goes through the `HTTPException` handler registered in Task 3, not `ValidationHTTPException`).
- Produces: nothing consumed by later tasks.

**Context:** `core/app/main.py`'s existing `read_only_guard` (defined via `@app.middleware("http")` inside `create_app()`) proves the pattern needed here: a `@app.middleware("http")` function sees every request, including the `/mcp` ASGI mount (`app.mount("/", mcp_server.streamable_http_app())`), because Starlette middleware wraps the whole app before routing/mounting dispatch. `_EXPORT_PATH_RE` (`core/app/main.py:53-55`) already matches `/export`, `/app-exports`, `/collections/{id}/export(/items)?`, `/datasets/{id}/arcgis/export` — reuse it directly rather than redefining. Confirmed route literals: `/analytics/sql` (`features/routes.py:420`), `/copilot/turn` (`copilot/routes.py:183`), `/mcp` (mount root, matched exactly by `read_only_guard`'s own check), `/harvest/*` (6+ distinct literal paths in `harvest/routes.py`, no shared router prefix — match by `^/harvest/` prefix).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_ratelimit.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.main import create_app


def _client(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    return TestClient(create_app())


def test_sql_route_rate_limited_after_budget_exhausted(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    assert response.status_code == 429
    assert "retry-after" in {k.lower() for k in response.headers.keys()}
    assert response.headers["content-type"] == "application/problem+json"


def test_different_callers_have_independent_budgets(monkeypatch):
    client = _client(monkeypatch)
    for _ in range(10):
        client.post(
            "/analytics/sql",
            json={"sql": "select 1"},
            headers={"Authorization": "Bearer caller-a"},
        )
    # caller-a est épuisé, mais caller-b démarre avec un budget frais
    response = client.post(
        "/analytics/sql", json={"sql": "select 1"}, headers={"Authorization": "Bearer caller-b"}
    )
    assert response.status_code != 429


def test_health_endpoint_not_rate_limited_by_sql_budget(monkeypatch):
    client = _client(monkeypatch)
    headers = {"Authorization": "Bearer same-caller-token"}
    for _ in range(10):
        client.post("/analytics/sql", json={"sql": "select 1"}, headers=headers)
    response = client.get("/health", headers=headers)
    assert response.status_code != 429
```

(Check `GET /health` actually exists first: `grep -n '"/health"' core/app/main.py` — if the route is named differently, use the real path.)

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd core
uv run pytest tests/test_ratelimit.py -v
```

Expected: `test_sql_route_rate_limited_after_budget_exhausted` FAILS (no 429 ever returned — no rate limiting exists yet). The other two currently pass vacuously (nothing to break).

- [ ] **Step 3: Implement the limiter**

Create `core/app/ratelimit/__init__.py` (empty, just makes it a package).

Create `core/app/ratelimit/limiter.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Rate limiting en mémoire process, par (clé d'appelant, groupe de route)
— design SP-26 §3.4. Clé d'appelant = l'en-tête Authorization brut, pas un
user_id résolu : ce middleware tourne AVANT l'injection de dépendances
FastAPI (donc avant get_current_user), et /mcp est un mount ASGI brut sans
dépendances du tout — décoder/vérifier le JWT ici dupliquerait toute la
logique de app.auth.dependency pour un usage qui n'a besoin que d'une clé
stable, pas d'une identité vérifiée. Limite assumée : ne tient pas
multi-process (pas de --workers aujourd'hui côté uvicorn, cf. C2/vague 0)."""

import re
import time
from collections import defaultdict, deque

_SQL_RE = re.compile(r"^/analytics/sql$")
_LLM_RE = re.compile(r"^/mcp$|^/copilot/turn$")
_HARVEST_RE = re.compile(r"^/harvest/")

# Budgets par groupe de coût réel (requêtes / 60s). Réutilise _EXPORT_PATH_RE
# de app.main pour le groupe "jobs" plutôt que de le redéfinir ici.
_BUDGETS = {
    "sql": 10,
    "llm": 20,
    "jobs": 15,
    "harvest": 10,
}
_WINDOW_SECONDS = 60.0


def route_group(path: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if _HARVEST_RE.match(path):
        return "harvest"
    return None


class RateLimiter:
    """Compteur glissant par (clé, groupe) — deque d'horodatages, purgée à
    chaque appel. Pas de nettoyage périodique en arrière-plan : une clé
    inactive garde une deque vide en mémoire indéfiniment, coût négligeable
    face au volume de callers distincts attendu (limite documentée, pas un
    bug — cf. design §7)."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, key: str, group: str) -> bool:
        budget = _BUDGETS[group]
        now = time.monotonic()
        bucket = self._hits[(key, group)]
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= budget:
            return False
        bucket.append(now)
        return True
```

- [ ] **Step 4: Mount the middleware in `main.py`**

Add the import near the top of `core/app/main.py`:

```python
from app.ratelimit.limiter import RateLimiter, route_group
```

Inside `create_app()`, after `app = FastAPI(...)` / `observability.instrument_app(app)` and before (or after — independent of) the `read_only_guard` middleware, add a new middleware and a module-level-per-app limiter instance:

```python
    rate_limiter = RateLimiter()

    @app.middleware("http")
    async def rate_limit_guard(request: Request, call_next):
        group = route_group(request.url.path, _EXPORT_PATH_RE)
        if group is not None:
            caller_key = request.headers.get("authorization", "")
            if not rate_limiter.allow(caller_key, group):
                return JSONResponse(
                    status_code=429,
                    media_type="application/problem+json",
                    headers={"Retry-After": "60"},
                    content={
                        "type": "about:blank",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": f"rate limit exceeded for {group}",
                    },
                )
        return await call_next(request)
```

`rate_limiter = RateLimiter()` is created inside `create_app()`, not at module level — matches the existing pattern where per-app state (like `mcp_server`) is scoped to one `create_app()` call, since the test suite calls `create_app()` repeatedly per test and a module-level singleton would leak rate-limit state across unrelated tests (the exact same reasoning already documented in `main.py`'s comment about `mcp_server` not being memoized process-wide).

- [ ] **Step 5: Run the new tests and the full suite**

```bash
cd core
uv run pytest tests/test_ratelimit.py -v
uv run pytest -x -q
```

Expected: 3 new tests pass; full suite count grows by 3, no other regressions.

- [ ] **Step 6: Verify `/mcp` is actually covered (the reason this had to be middleware, not a route dependency)**

```bash
cd core
uv run python -c "
from app.ratelimit.limiter import route_group
import re
export_re = re.compile(r'^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?\$|^/export\$|^/app-exports\$')
assert route_group('/mcp', export_re) == 'llm'
assert route_group('/copilot/turn', export_re) == 'llm'
assert route_group('/analytics/sql', export_re) == 'sql'
assert route_group('/export', export_re) == 'jobs'
assert route_group('/app-exports', export_re) == 'jobs'
assert route_group('/harvest/sources', export_re) == 'harvest'
assert route_group('/health', export_re) is None
print('all route groups correct')
"
```

- [ ] **Step 7: Commit**

```bash
git add core/app/ratelimit/ core/app/main.py core/tests/test_ratelimit.py
git commit -m "$(cat <<'EOF'
feat(core): rate limiting différencié par route sensible

Middleware ASGI (couvre /mcp, un mount brut hors du routage FastAPI,
comme le fait déjà read_only_guard) — compteur en mémoire par (en-tête
Authorization, groupe de route), budgets distincts sql/llm/jobs/harvest
(I4, revue de projet 2026-08-20). Limite assumée : par process, pas de
Redis.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Arrêt propre `cdc-worker` (3.5b)

**Files:**
- Modify: `core/app/cdc/main.py` (`run()` gains a `should_stop` flag + `SIGTERM` handler + final flush)
- Test: `core/tests/test_cdc_main.py` (new, or extend an existing `test_cdc_*.py` if one already exercises `run()`-adjacent helpers — check first)

**Interfaces:**
- Consumes: nothing from Tasks 1-4.
- Produces: nothing consumed by later tasks.

**Context:** `core/app/cdc/consumer.py:227-235`'s `stream_changes(...)` already accepts a `should_stop: Callable[[], bool] = lambda: False` parameter and a `poll_timeout_s` — this is the hook. `core/app/cdc/main.py:97-205`'s `run()` currently calls `stream_changes(raw_dsn, on_message=_on_message, is_flush_due=..., do_flush=_do_flush)` without passing `should_stop`, so the loop never exits on its own. `_do_flush` (a closure inside `run()`, `main.py:148-151`) is exactly the function to call once more after the loop exits, to flush any buffered-but-unflushed rows before the process dies.

- [ ] **Step 1: Check for existing `cdc/main.py` test coverage**

```bash
cd core
find tests -iname "*cdc_main*" -o -iname "*test_cdc*"
grep -l "cdc.main\|cdc\.main" tests/*.py
```

If a `test_cdc_main.py` exists, read it fully before writing new tests — extend it rather than creating a duplicate file. If nothing tests `main.py`'s `run()` function or its helpers directly (likely, since `run()` requires a real `CDC_DATABASE_URL`/S3 client per its docstring/`_write_and_upload`'s own comment "extrait de _flush_table pour rester testable indépendamment de run() (qui exige DB/S3 réels)"), create a new file testing only the signal-handling mechanism in isolation — not `run()` itself.

- [ ] **Step 2: Write the failing test**

Create `core/tests/test_cdc_shutdown.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Teste uniquement le mécanisme d'arrêt (signal -> flag -> should_stop),
pas run() en entier — qui exige un DSN CDC_DATABASE_URL et un client S3
réels (cf. main.py::_write_and_upload, testée séparément pour la même
raison)."""
import signal

from app.cdc import main as cdc_main


def test_sigterm_sets_the_stop_flag():
    state = cdc_main._ShutdownState()
    assert state.should_stop() is False
    state.handle_sigterm(signal.SIGTERM, None)
    assert state.should_stop() is True
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd core
uv run pytest tests/test_cdc_shutdown.py -v
```

Expected: FAILS with `AttributeError: module 'app.cdc.main' has no attribute '_ShutdownState'`.

- [ ] **Step 4: Implement the shutdown state + wire it into `run()`**

Edit `core/app/cdc/main.py`, add near the top (after the `_WorkerState` class, before `build_s3_key`):

```python
class _ShutdownState:
    """État du signal SIGTERM (SP-26/3.5b) — séparé de _WorkerState (données
    métier) : ce flag n'a qu'un rôle, dire à stream_changes() de sortir de
    sa boucle proprement (cf. consumer.stream_changes's `should_stop`
    param, déjà prévu pour ça mais jamais branché avant ce chantier)."""

    def __init__(self) -> None:
        self._stop = False

    def should_stop(self) -> bool:
        return self._stop

    def handle_sigterm(self, signum, frame) -> None:
        self._stop = True
```

Edit `run()` — add the import (`import signal` at the top of the file, next to the existing `import os`/`import threading`/etc.), instantiate the state, register the handler, and pass `should_stop` + do a final flush after the loop returns:

```python
def run() -> None:
    raw_dsn = os.environ["CDC_DATABASE_URL"]
    engine = make_engine(raw_dsn.replace("postgresql://", "postgresql+psycopg://"))
    session_factory = make_session_factory(engine)
    s3_bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    s3_client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(s3_client, s3_bucket)

    state = _WorkerState()
    shutdown = _ShutdownState()
    signal.signal(signal.SIGTERM, shutdown.handle_sigterm)
    observability.register_cdc_lag_gauge(state.get_lag_seconds)

    consumer.ensure_replication_slot(raw_dsn)

    # ... (backfill loop unchanged) ...

    # ... (_flush_table, _do_flush, _on_message closures unchanged) ...

    consumer.stream_changes(
        raw_dsn,
        on_message=_on_message,
        is_flush_due=lambda: bool(buffer.tables_due_for_flush()),
        do_flush=_do_flush,
        should_stop=shutdown.should_stop,
    )
    # stream_changes() ne flushe que quand is_flush_due() est vrai PENDANT
    # la boucle — un SIGTERM peut arriver avec des lignes déjà bufferisées
    # mais pas encore dues à l'âge (30s). Flush final explicite avant
    # sortie, même mécanisme que _do_flush, appelé une dernière fois.
    _do_flush()
```

Do not restructure the closures (`_flush_table`, `_do_flush`, `_on_message`, the backfill loop) — only add the 3 lines shown (`shutdown = _ShutdownState()`, `signal.signal(...)`, `should_stop=shutdown.should_stop` in the `stream_changes` call) and the final `_do_flush()` call after it returns. Leave everything else in `run()` exactly as-is.

- [ ] **Step 5: Run the new test and the full suite**

```bash
cd core
uv run pytest tests/test_cdc_shutdown.py -v
uv run pytest -x -q
```

Expected: new test passes; full suite unaffected (no existing test calls `run()` directly, confirmed in Step 1).

- [ ] **Step 6: Commit**

```bash
git add core/app/cdc/main.py core/tests/test_cdc_shutdown.py
git commit -m "$(cat <<'EOF'
feat(core): arrêt propre du cdc-worker sur SIGTERM

stream_changes() acceptait déjà un paramètre should_stop, jamais
branché — SIGTERM positionne un flag vérifié à chaque itération, puis
un flush final avant sortie pour ne pas perdre les lignes bufferisées
non encore dues à l'âge (I11, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `ErrorBoundary` applicatif (3.5c)

**Files:**
- Create: `shell/src/AppErrorBoundary.tsx`
- Create: `shell/src/AppErrorBoundary.test.tsx`
- Modify: `shell/src/App.tsx`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed by later tasks.

**Context:** `shell/src/builder/WidgetHost.tsx:14-30` already has `WidgetErrorBoundary`, a per-widget class component — that one stays untouched (it's scoped intentionally to isolate one widget crash from the rest of a page). `shell/src/App.tsx` is the actual root: `App()` renders `<AuthProvider><QueryClientProvider><AppShell /></QueryClientProvider></AuthProvider>`, and `AppShell()` renders `<ItemClientProvider><BrowserRouter><AppRoutes /></BrowserRouter></ItemClientProvider>`. The new boundary wraps `<AppShell />` (inside the providers, so it still has query client / auth context for its own fallback UI if needed, but outside the router so it also catches any router-level crash).

- [ ] **Step 1: Write the failing test**

Create `shell/src/AppErrorBoundary.test.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppErrorBoundary } from "./AppErrorBoundary";

function Boom(): never {
  throw new Error("kaboom");
}

describe("AppErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <AppErrorBoundary>
        <div>hello</div>
      </AppErrorBoundary>,
    );
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("renders a fallback instead of crashing when a child throws", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <AppErrorBoundary>
        <Boom />
      </AppErrorBoundary>,
    );
    expect(screen.queryByText("hello")).not.toBeInTheDocument();
    expect(screen.getByText(/une erreur est survenue/i)).toBeInTheDocument();
    consoleError.mockRestore();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd shell
npx vitest run src/AppErrorBoundary.test.tsx
```

Expected: FAILS — `./AppErrorBoundary` doesn't exist yet.

- [ ] **Step 3: Implement**

Create `shell/src/AppErrorBoundary.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

// Distinct de WidgetErrorBoundary (builder/WidgetHost.tsx), qui isole un
// widget individuel — celui-ci est au niveau racine de l'app (App.tsx) et
// attrape tout ce qui n'est PAS un widget : chrome du builder, pages,
// panneaux (I12, revue de projet 2026-08-20 — un seul ErrorBoundary
// existait, scopé par widget, donc toute exception de rendu ailleurs
// produisait un écran blanc).
export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(err: unknown) {
    console.error("AppErrorBoundary: unhandled render error", err);
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="flex h-screen flex-col items-center justify-center gap-4 bg-slate-50 text-center">
          <p className="text-lg font-medium text-slate-800">Une erreur est survenue.</p>
          <p className="text-sm text-slate-500">
            Rechargez la page ; si le problème persiste, contactez votre administrateur.
          </p>
          <button
            type="button"
            className="rounded bg-slate-800 px-4 py-2 text-sm text-white"
            onClick={() => window.location.reload()}
          >
            Recharger
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

- [ ] **Step 4: Wire it into `App.tsx`**

Edit `shell/src/App.tsx`:

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { buildExportAwareToken } from "./auth/exportAwareToken";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppRoutes } from "./shell/routes";
import { AppErrorBoundary } from "./AppErrorBoundary";

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
const queryClient = new QueryClient();

function AppShell() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: config.coreUrl,
        getToken: buildExportAwareToken(getAccessToken),
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <AppErrorBoundary>
      <AuthProvider config={config}>
        <QueryClientProvider client={queryClient}>
          <AppShell />
        </QueryClientProvider>
      </AuthProvider>
    </AppErrorBoundary>
  );
}
```

(Placed outside `AuthProvider` rather than inside `AppShell`, so it also catches a crash in `AuthProvider`/`QueryClientProvider` setup itself, not just inside the router tree.)

- [ ] **Step 5: Run the new test and the existing `App.test.tsx`**

```bash
cd shell
npx vitest run src/AppErrorBoundary.test.tsx src/App.test.tsx
```

Expected: all pass. If `App.test.tsx` snapshot-tests the exact render tree structure, it may need a small update to account for the new wrapper — check its content first with `cat src/App.test.tsx` before assuming no change is needed.

- [ ] **Step 6: Run the full shell suite**

```bash
cd shell
npx vitest run
npm run lint && npm run format:check && npm run build
```

Expected: 161+2 = 163 files (2 new: `AppErrorBoundary.tsx` isn't a test file itself, only `AppErrorBoundary.test.tsx` counts — verify the exact delta against the vitest summary rather than assuming), no regressions.

- [ ] **Step 7: Commit**

```bash
git add shell/src/AppErrorBoundary.tsx shell/src/AppErrorBoundary.test.tsx shell/src/App.tsx
git commit -m "$(cat <<'EOF'
feat(shell): ErrorBoundary applicatif à la racine

Le seul ErrorBoundary existant est scopé par widget (WidgetHost.tsx) —
toute exception de rendu ailleurs (chrome builder, pages, panneaux)
produisait un écran blanc (I12, revue de projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: CSP, Permissions-Policy, compression (3.3)

**Files:**
- Modify: `docker-compose.prod.yml` (extend the existing `security-headers` Traefik middleware, add a `compress` middleware)
- Modify: `shell/nginx.conf` (add the same headers + gzip, for the dev-served/standalone paths that bypass Traefik)
- Test: manual verification against a real running stack (browser or `curl`) — no automated unit test framework covers Traefik label config or nginx directives in this repo

**Interfaces:**
- Consumes: nothing from other tasks structurally, but benefits from Tasks 1-6 being done first (per the spec's ordering rationale: verify the CSP against every new surface this SP adds in one pass, rather than twice).
- Produces: nothing consumed by later tasks.

**Context:** `docker-compose.prod.yml:104-109` already defines a `security-headers` Traefik middleware (`stsSeconds`, `contentTypeNosniff`, `frameDeny`, `referrerPolicy`) chained into both the `core` router (line 101) and the `shell` router (line 153) via `traefik.http.routers.<name>.middlewares=security-headers@docker,rate-limit@docker[,strip-api@docker]`. Extend this same middleware rather than creating a new one — CSP/Permissions-Policy are just more `headers` middleware options. Traefik v3's `headers` middleware exposes arbitrary response headers via `customResponseHeaders.<HeaderName>=<value>` labels (used for headers with no dedicated named option, like `Content-Security-Policy`).

- [ ] **Step 1: Add CSP + Permissions-Policy labels to the existing `security-headers` middleware, in Report-Only form first**

Edit `docker-compose.prod.yml`, extending the block at (current) lines 104-109:

```yaml
      - traefik.http.middlewares.security-headers.headers.stsSeconds=31536000
      - traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true
      - traefik.http.middlewares.security-headers.headers.frameDeny=true
      - traefik.http.middlewares.security-headers.headers.referrerPolicy=strict-origin-when-cross-origin
      # CSP en Report-Only pendant la vérification empirique (Step 3-4
      # ci-dessous) contre MapLibre/deck.gl/Keycloak/une extension tierce —
      # bascule en enforcing (Step 5) une fois confirmée (SP-26/3.3). Les
      # valeurs ${GEOSTUDIO_PUBLIC_HOST}/keycloak reprennent les mêmes
      # variables que le reste de ce fichier.
      - traefik.http.middlewares.security-headers.headers.customResponseHeaders.Content-Security-Policy-Report-Only=default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://${GEOSTUDIO_PUBLIC_HOST}; img-src 'self' data: blob: https://${GEOSTUDIO_PUBLIC_HOST}; worker-src 'self' blob:; frame-src https://${GEOSTUDIO_PUBLIC_HOST}; object-src 'none'
      - traefik.http.middlewares.security-headers.headers.customResponseHeaders.Permissions-Policy=camera=(), microphone=(), payment=(), usb=()
      - traefik.http.middlewares.rate-limit.ratelimit.average=100
      - traefik.http.middlewares.rate-limit.ratelimit.burst=200
      - traefik.http.middlewares.compress.compress=true
```

`connect-src`/`img-src`/`frame-src` all point at `${GEOSTUDIO_PUBLIC_HOST}` since, per the CDC/C3 fix from Vague 0, Traefik fronts both `core` (`/api` path prefix) and `keycloak` (`/auth` path prefix) on the SAME public host — verify this is still true by re-reading the router rules at (current) lines 67 and 98 before assuming; if Keycloak is on a different host in some deployments, this directive needs a second variable.

- [ ] **Step 2: Chain the new `compress` middleware into both routers**

Edit the `core` and `shell` router middleware lists (current lines 101 and 153):

```yaml
      - traefik.http.routers.core.middlewares=security-headers@docker,rate-limit@docker,compress@docker,strip-api@docker
```

```yaml
      - traefik.http.routers.shell.middlewares=security-headers@docker,rate-limit@docker,compress@docker
```

- [ ] **Step 3: Add the equivalent headers + gzip to `shell/nginx.conf`**

Edit `shell/nginx.conf`:

```nginx
server {
  listen 8300;
  root /usr/share/nginx/html;
  index index.html;

  gzip on;
  gzip_types text/css application/javascript application/json image/svg+xml;
  gzip_min_length 1024;

  add_header X-Content-Type-Options nosniff always;
  add_header Referrer-Policy strict-origin-when-cross-origin always;
  add_header Permissions-Policy "camera=(), microphone=(), payment=(), usb=()" always;
  add_header Content-Security-Policy-Report-Only "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; object-src 'none'" always;

  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

`connect-src`/`img-src` here stay `'self'` without a hardcoded host: `nginx.conf` also serves the export/standalone bundles (SP-18a/c), which target whatever core URL is baked in at build/runtime via `env-config.js` — a fixed hostname would break those. Leave the widening to `connect-src 'self' <core-origin>` for Step 5 if empirical testing shows the mock/dev flow calling a cross-origin `core` needs it (check `VITE_CORE_URL` usage in dev — if `core` is same-origin behind Traefik in the deployments this file matters for, `'self'` may already suffice for `shell/nginx.conf`, unlike the Traefik-fronted `security-headers` middleware which explicitly needs the public host).

- [ ] **Step 4: Bring up a real stack and manually verify the 4 surfaces named in the spec**

```bash
docker compose up -d --build
```

Wait for `core`/`shell` healthy (`docker compose ps`), then in a browser at `http://localhost:8300`:

1. Open the map editor, add a vector layer, confirm it renders (MapLibre canvas visible, no CSP violations in DevTools console — since this is Report-Only, violations appear as console warnings, not blocked resources).
2. Open the builder, add a map widget to an app/dashboard, confirm the widget carte renders identically.
3. If an extension widget is registered (check `AdminExtensionsPage` — `shell/e2e/extension-widget.spec.ts` shows how one gets registered for tests, may need a real one registered manually via the admin UI for this manual check), confirm it still loads its JS and renders.
4. Trigger a Keycloak silent-SSO check (if `VITE_AUTH_MODE=oidc` is configured for this manual run) — confirm the iframe isn't blocked.

Record in the task's commit message or a scratch note exactly which console warnings appeared (if any) — these tell you which directive needs loosening before Step 5 flips to enforcing.

- [ ] **Step 5: Flip Report-Only to enforcing once Step 4 shows no unexpected violations**

Replace `Content-Security-Policy-Report-Only` with `Content-Security-Policy` in both `docker-compose.prod.yml` and `shell/nginx.conf` (same directive values, unless Step 4 required changes — apply those changes here, not by inventing new values speculatively).

```bash
docker compose up -d --build
```

Repeat the 4 manual checks from Step 4 — this time a real violation would actually block the resource (broken map, missing widget), not just warn. If anything breaks, loosen only the specific directive that Chrome/Firefox DevTools' console names as the blocker, don't broaden the whole policy.

- [ ] **Step 6: Verify compression is actually applied**

```bash
curl -sI -H 'Accept-Encoding: gzip' http://localhost:8300/ | grep -i content-encoding
```

Expected: `content-encoding: gzip`. For the Traefik-fronted path, this needs the prod overlay running (not the dev compose alone) — if not feasible to stand up prod overlay locally, verify by reading `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` and confirming the `compress@docker` middleware label resolves onto both routers, and note in the commit that live verification of the Traefik path specifically was config-only, not a live `curl` against Traefik (be honest about what was and wasn't actually run, per this repo's established discipline).

- [ ] **Step 7: Run the deployability guard and full non-regression suite**

```bash
cd core
uv run pytest tests/test_deployability.py -v
cd ..
docker compose down
```

Expected: 31/31 still green (no new env var substitution introduced by this task — CSP values are hardcoded except `${GEOSTUDIO_PUBLIC_HOST}`, already documented/wired from prior SPs).

- [ ] **Step 8: Commit**

```bash
git add docker-compose.prod.yml shell/nginx.conf
git commit -m "$(cat <<'EOF'
feat(deploy): CSP, Permissions-Policy et compression

Étend le middleware security-headers Traefik existant (Report-Only
vérifié empiriquement contre MapLibre/deck.gl/Keycloak/une extension
avant bascule en enforcing) + mêmes en-têtes sur shell/nginx.conf, qui
sert aussi les exports statiques/autoportés hors Traefik (I3, revue de
projet 2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Notifier les alertes SLO (3.7)

**Files:**
- Create: `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml`
- Create: `deploy/observability/grafana/provisioning/alerting/policies.yaml`
- Modify: `docker-compose.yml` (wire `GRAFANA_ALERT_WEBHOOK_URL` to the `otel-lgtm` service, add an envsubst step if native `${VAR}` expansion isn't supported — determined empirically in Step 1)
- Modify: `.env.example` (document `GRAFANA_ALERT_WEBHOOK_URL`)
- Test: manual verification via the existing `test-alert-do-not-keep-in-prod` rule already in `rules.yaml`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing consumed by later tasks.

**Context:** `deploy/observability/grafana/provisioning/alerting/rules.yaml` is bind-mounted wholesale into `grafana/otel-lgtm:0.11.4`'s Grafana provisioning path (`docker-compose.yml`'s `otel-lgtm` service, `./deploy/observability/grafana/provisioning/alerting:/otel-lgtm/grafana/conf/provisioning/alerting`) — any file added to the local directory appears in the container automatically, no compose change needed for the files themselves, only for the env var they reference. The file already contains a `test-alert-do-not-keep-in-prod` group with `isPaused: true`, built specifically to prove the notification pipeline end-to-end without depending on real traffic.

- [ ] **Step 1: Determine whether this Grafana version supports native `${VAR}` expansion in provisioning files**

```bash
docker run --rm grafana/otel-lgtm:0.11.4 grafana-server -v 2>&1 | head -5
```

Note the Grafana version. Check Grafana's changelog/docs for when `${...}` expansion in provisioning files landed (this requires either checking Grafana's actual behavior in a running container, or consulting docs — do not guess). Pragmatic empirical check instead of reading changelogs:

```bash
mkdir -p /tmp/grafana-envtest/provisioning/alerting
cat > /tmp/grafana-envtest/provisioning/alerting/contactpoints.yaml <<'EOF'
apiVersion: 1
contactPoints:
  - orgId: 1
    name: test-cp
    receivers:
      - uid: test-cp-webhook
        type: webhook
        settings:
          url: ${TEST_WEBHOOK_URL}
EOF
docker run --rm -e TEST_WEBHOOK_URL=https://example.test/hook \
  -v /tmp/grafana-envtest/provisioning/alerting:/otel-lgtm/grafana/conf/provisioning/alerting \
  -p 13000:3000 -d --name grafana-envtest grafana/otel-lgtm:0.11.4
sleep 15
docker exec grafana-envtest grep -r "url" /otel-lgtm/grafana/conf/provisioning/alerting/ 2>/dev/null
# Si le fichier monté est relu tel quel par ce grep (normal, c'est un bind
# mount côté fichier) — le vrai test est de savoir si GRAFANA a résolu
# ${TEST_WEBHOOK_URL} en interne. Interroger l'API de contact points :
curl -s -u admin:admin http://localhost:13000/api/v1/provisioning/contact-points | grep -o '"url":"[^"]*"'
docker rm -f grafana-envtest
rm -rf /tmp/grafana-envtest
```

If the API response shows the literal string `example.test` (resolved), native expansion works — proceed to Step 2a. If it shows the literal unexpanded `${TEST_WEBHOOK_URL}` string, native expansion is NOT supported at this version — proceed to Step 2b instead.

- [ ] **Step 2a: (if native expansion works) Create the contact point and policy files directly with `${GRAFANA_ALERT_WEBHOOK_URL}`**

Create `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml`:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: geostudio-webhook
    receivers:
      - uid: geostudio-webhook-receiver
        type: webhook
        settings:
          url: ${GRAFANA_ALERT_WEBHOOK_URL}
```

Create `deploy/observability/grafana/provisioning/alerting/policies.yaml`:

```yaml
apiVersion: 1
policies:
  - orgId: 1
    receiver: geostudio-webhook
    routes:
      - receiver: geostudio-webhook
        object_matchers:
          - ["slo", "=~", ".+"]
        continue: false
```

Edit `docker-compose.yml`'s `otel-lgtm` service to pass the variable through:

```yaml
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    environment:
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-}
    ports:
```

- [ ] **Step 2b: (if native expansion does NOT work) Use an envsubst wrapper via a custom entrypoint override**

Create `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml.template`:

```yaml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: geostudio-webhook
    receivers:
      - uid: geostudio-webhook-receiver
        type: webhook
        settings:
          url: ${GRAFANA_ALERT_WEBHOOK_URL}
```

Create `deploy/observability/grafana/provisioning/alerting/policies.yaml` (no substitution needed, static content — same as Step 2a's version).

Edit `docker-compose.yml`'s `otel-lgtm` service to render the template before Grafana starts, overriding its default entrypoint:

```yaml
  otel-lgtm:
    image: grafana/otel-lgtm:0.11.4
    profiles: ["observability"]
    environment:
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-}
    entrypoint:
      - sh
      - -c
      - |
        apk add --no-cache gettext 2>/dev/null || true
        envsubst < /otel-lgtm/grafana/conf/provisioning/alerting/contactpoints.yaml.template > /otel-lgtm/grafana/conf/provisioning/alerting/contactpoints.yaml
        exec /run-all.sh
    ports:
```

Check the image's real default entrypoint/startup script first — `docker run --rm --entrypoint sh grafana/otel-lgtm:0.11.4 -c "cat /run-all.sh 2>/dev/null || find / -maxdepth 2 -iname '*run*' -o -iname '*entrypoint*' 2>/dev/null"` — replace `/run-all.sh` above with whatever the actual startup script is named; do not guess it blindly, this determines whether the container starts at all.

Do NOT create `contactpoints.yaml` (final, non-template) directly in git in this branch — only the `.yaml.template` is committed; the rendered `.yaml` is generated at container start and should be added to `.gitignore` if it would otherwise land in the bind-mounted host directory (check: does the entrypoint write into the bind-mounted path, meaning the rendered file appears on the host too? If so, add `deploy/observability/grafana/provisioning/alerting/contactpoints.yaml` to `.gitignore`).

- [ ] **Step 3: Document the new variable**

Edit `.env.example`, near the existing observability section (find it with `grep -n "OTEL\|observability" .env.example`):

```
# Point de contact webhook pour les alertes SLO Grafana (SP-26/3.7) — vide
# par défaut, aucune notification tant que l'opérateur ne le renseigne pas.
# Voir deploy/observability/grafana/provisioning/alerting/rules.yaml.
GRAFANA_ALERT_WEBHOOK_URL=
```

- [ ] **Step 4: Verify the deployability guard**

```bash
cd core
uv run pytest tests/test_deployability.py -v
```

Expected: 31/31 still green — `GRAFANA_ALERT_WEBHOOK_URL` is now both a `${...}` substitution in `docker-compose.yml` and documented in `.env.example`.

- [ ] **Step 5: Prove end-to-end delivery using the existing test-alert rule**

```bash
export GRAFANA_ALERT_WEBHOOK_URL=https://webhook.site/<get-a-real-test-url-first>
docker compose --profile observability up -d otel-lgtm
```

Get a real disposable webhook URL first (e.g. from `webhook.site` or `requestbin`, or run a trivial local HTTP listener `python3 -m http.server 9999` and use `http://host.docker.internal:9999` if the CI/dev environment supports host networking — pick whichever is actually reachable in this environment; don't fabricate a URL you can't observe).

Edit `deploy/observability/grafana/provisioning/alerting/rules.yaml`'s `test-alert-do-not-keep-in-prod` group, flip `isPaused: true` to `isPaused: false` **temporarily** (do not commit this flip):

```bash
docker compose --profile observability restart otel-lgtm
sleep 15
# Observe the webhook receiver — expect one delivered notification within ~10-20s
```

Confirm a notification actually arrived at the webhook target. Then revert `isPaused` back to `true` in the file (it must never ship as `false`) and restart again to confirm it stops firing.

```bash
git diff deploy/observability/grafana/provisioning/alerting/rules.yaml
# Expected: empty — isPaused restored to true, no unintended change committed
docker compose --profile observability down
```

- [ ] **Step 6: Commit**

```bash
git add deploy/observability/grafana/provisioning/alerting/ docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(deploy): notifie les alertes SLO Grafana par webhook

Point de contact + politique de routage pour le dossier SLO, URL
fournie par l'opérateur (vide par défaut = pas de notification). Preuve
de bout en bout via la règle test-alert-do-not-keep-in-prod déjà
présente dans rules.yaml pour cet usage (I9, revue de projet
2026-08-20).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: E2E sur OIDC réel (3.8)

**Files:**
- Create: `shell/e2e/auth-oidc.spec.ts`
- Create: `shell/playwright.oidc.config.ts`
- Modify: `shell/package.json` (add an `e2e:oidc` script)
- Modify: `.github/workflows/ci.yml` (add a new `shell-e2e-oidc` job)

**Interfaces:**
- Consumes: nothing structurally, but exercises Task 2's guard and Task 4's rate limiter under real OIDC conditions (per the spec's ordering rationale — placed last).
- Produces: nothing consumed by later tasks (last task before Task 10's final validation).

**Context:** The existing `shell` E2E suite (108 specs, `shell/playwright.config.ts`) runs entirely against `VITE_AUTH_MODE=mock` with `VITE_CORE_URL: "https://core.test"` — a fake domain, all network calls intercepted client-side via Playwright route mocking, no real `core`/Postgres/Keycloak process involved at all. This task needs the opposite: real `postgis` + `keycloak` (importing the already-existing `deploy/keycloak/geostudio-realm.json`, which provisions a `geostudio-shell` public client with redirect URI `http://localhost:8300/` and two test users `alice`/`bob`, both password `Demo1234!`) + real `core` in `CORE_AUTH_MODE=oidc` + real `shell` built with `VITE_AUTH_MODE=oidc`, all via `docker compose up`, with Playwright pointed at the live `http://localhost:8300`.

- [ ] **Step 1: Write the Playwright config for this suite**

Create `shell/playwright.oidc.config.ts`:

```typescript
import { defineConfig } from "@playwright/test";

// Suite séparée de playwright.config.ts (mock) : celle-ci suppose une
// stack docker compose déjà démarrée (postgis+keycloak+core+shell réels,
// CORE_AUTH_MODE=oidc) — pas de webServer local, pas de mock réseau
// (SP-26/3.8, I13 revue de projet 2026-08-20).
export default defineConfig({
  testDir: "./e2e-oidc",
  use: { baseURL: "http://localhost:8300" },
  retries: process.env.CI ? 2 : 0,
  timeout: 30_000,
});
```

- [ ] **Step 2: Write the spec**

Create the directory `shell/e2e-oidc/` and `shell/e2e-oidc/auth-oidc.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

const ALICE = { username: "alice", password: "Demo1234!" };

test.describe("authentification OIDC réelle (Keycloak)", () => {
  test("connexion redirige vers Keycloak puis revient authentifié", async ({ page }) => {
    await page.goto("/");
    // Non authentifié : oidc-client-ts redirige vers Keycloak.
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
    await page.fill('input[name="username"]', ALICE.username);
    await page.fill('input[name="password"]', ALICE.password);
    await page.click('input[type="submit"], button[type="submit"]');
    // Retour sur le shell, authentifié.
    await page.waitForURL("http://localhost:8300/**");
    await expect(page.getByText(/catalogue|catalog/i)).toBeVisible({ timeout: 15_000 });
  });

  test("déconnexion efface la session", async ({ page }) => {
    await page.goto("/");
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth/);
    await page.fill('input[name="username"]', ALICE.username);
    await page.fill('input[name="password"]', ALICE.password);
    await page.click('input[type="submit"], button[type="submit"]');
    await page.waitForURL("http://localhost:8300/**");

    // Trouver le contrôle de déconnexion réel du shell avant d'écrire ce
    // clic — grep "logout\|signout\|déconnexion" shell/src/**/*.tsx pour
    // le sélecteur exact plutôt que de le deviner ici.
    await page.getByRole("button", { name: /déconnexion|logout/i }).click();
    await page.waitForURL(/\/realms\/geostudio\/protocol\/openid-connect\/auth|localhost:8300\/?$/);
  });
});
```

Before finalizing this spec, grep the real logout control:

```bash
cd shell
grep -rn "logout\|signout\|déconnexion" src --include="*.tsx" -il
```

Read whichever file matches, find its exact visible label/role, and correct the `getByRole` call above to match — don't ship a guessed selector.

- [ ] **Step 3: Add the npm script**

Edit `shell/package.json`, near the existing `"e2e": "playwright test"` line:

```json
    "e2e:oidc": "playwright test --config=playwright.oidc.config.ts",
```

- [ ] **Step 4: Add the CI job**

Edit `.github/workflows/ci.yml`, add a new job after `shell`:

```yaml
  shell-e2e-oidc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build postgis+pgvector image
        run: docker build -t geostudio-postgis-ci:latest deploy/postgis
      - name: Bring up postgis, keycloak, core, shell (real OIDC)
        run: |
          cat > .env <<EOF
          PG_PASSWORD=ci-postgres-password
          KC_PASSWORD=ci-keycloak-password
          CORE_AUTH_MODE=oidc
          CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
          VITE_OIDC_AUTHORITY=http://localhost:8180/realms/geostudio
          VITE_OIDC_CLIENT_ID=geostudio-shell
          VITE_OIDC_REDIRECT_URI=http://localhost:8300/
          VITE_AUTH_MODE=oidc
          EOF
          docker compose build core shell
          docker compose up -d postgis keycloak core shell
      - name: Wait for shell to be reachable
        run: |
          for i in $(seq 1 60); do
            curl -sf http://localhost:8300/ > /dev/null && break
            sleep 5
          done
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
        working-directory: shell
      - run: npx playwright install --with-deps chromium
        working-directory: shell
      - run: npm run e2e:oidc
        working-directory: shell
      - name: Dump service logs on failure
        if: failure()
        run: docker compose logs core keycloak shell
```

`docker build -t geostudio-postgis-ci:latest deploy/postgis` mirrors the `core`/`migrations` jobs' own image-naming convention exactly, so `docker compose`'s own `postgis` service (which does `build: ./deploy/postgis` per `docker-compose.yml`, check with `grep -A2 "^  postgis:" docker-compose.yml` to confirm the exact build context) resolves without rebuilding from scratch — if `docker compose build` conflicts with the pre-tagged image, drop the standalone `docker build` line and let `docker compose build postgis core shell` build everything itself instead; verify by running it once and reading the output.

- [ ] **Step 5: Verify the job runs and passes — do not skip this, per the spec's explicit requirement**

Since this can't be run via GitHub Actions from a local session, verify the equivalent sequence manually against a real local Docker environment:

```bash
cd /home/lenen/projets/geostudio
cat >> .env <<'EOF'
CORE_AUTH_MODE=oidc
EOF
docker compose build core shell
docker compose up -d postgis keycloak core shell
for i in $(seq 1 60); do curl -sf http://localhost:8300/ > /dev/null && break; sleep 5; done
cd shell
npx playwright install --with-deps chromium
npm run e2e:oidc
```

Expected: both specs in `auth-oidc.spec.ts` PASS against the real stack. If either fails, debug against real Keycloak/core logs (`docker compose logs keycloak core`) — do not weaken the spec's assertions to make it pass; fix the actual redirect URI, client config, or selector mismatch. This mirrors the SP-17a Task 6 precedent explicitly cited in the spec: a `@pytest.mark.playwright`-style test that's only ever claimed to work, never actually run, is exactly the failure mode this task exists to close (SP-15d's un-run qgis tests are the cautionary counter-example).

```bash
docker compose down
git checkout .env  # ou rm .env si créé pour l'occasion — ne pas committer de secrets de test
```

- [ ] **Step 6: Confirm the existing mock E2E suite is unaffected**

```bash
cd shell
npm run e2e
```

Expected: still 108 passed, 4 skipped, 0 failed — the new spec lives in a separate `e2e-oidc/` directory with its own config, untouched by `playwright.config.ts`'s `testDir: "./e2e"`.

- [ ] **Step 7: Commit**

```bash
git add shell/playwright.oidc.config.ts shell/e2e-oidc/ shell/package.json .github/workflows/ci.yml
git commit -m "$(cat <<'EOF'
test(shell): E2E réelle contre Keycloak (login/logout OIDC)

Nouveau job CI dédié, stack réelle (postgis+keycloak+core en
CORE_AUTH_MODE=oidc+shell), séparé de la suite mock existante (I13,
revue de projet 2026-08-20) — referme le suivi non bloquant SP-20 sur
l'absence de preuve bout-en-bout navigateur+iframe+Keycloak.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

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

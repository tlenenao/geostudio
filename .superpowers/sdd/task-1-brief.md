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


# Task 7 report — Docker Compose wiring

## What was implemented

`docker-compose.yml` only, exactly per the brief:

1. **Step 1** — added `etl-scratch:` to the top-level `volumes:` section
   (alongside the pre-existing `pg-data:`, `minio-data:`, `keycloak-data:`).
2. **Step 2** — added the `qgis-worker` service block (after `worker:`,
   before the `cdc-worker:` comment): `build: ./deploy/qgis-worker`,
   `profiles: ["etl"]`, `QT_QPA_PLATFORM: offscreen`, `etl-scratch:/scratch`
   mount, `gis-net` network, `restart: unless-stopped`, plus the French
   comment block from the brief (SP-15d / A39 rationale).
3. **Step 3** — added to `worker:`'s `environment:` block:
   `QGIS_WORKER_URL: http://qgis-worker:8000` and
   `QGIS_WORKER_TIMEOUT_SECONDS: "600"`; added a new `volumes:` key
   (`- etl-scratch:/scratch`) right after `environment:` and before
   `networks: [gis-net]`, since `worker:` had no `volumes:` key before.

No other service, no other file, was touched.

## Validation evidence

### `docker compose config --quiet`
Exit code: `0`. No output beyond the expected `level=warning` lines for
unset `.env` variables (PG_PASSWORD, MINIO_USER, etc. — pre-existing,
unrelated to this change; there is no `.env` file in this environment).
Confirms valid YAML + valid compose schema.

### `docker compose --profile etl config --services`
```
postgis
pgbouncer
martin
minio
qgis-worker
titiler
keycloak
shell
traefik
worker
cdc-worker
core
```
`qgis-worker` is present.

### `docker compose config --services` (no `--profile etl`)
```
postgis
pgbouncer
martin
minio
titiler
traefik
cdc-worker
shell
worker
core
```
`qgis-worker` is absent — confirms the profile gate works.

### Smoke test transcript

```
$ docker compose --profile etl build qgis-worker
... (build steps, all CACHED from Task 4's image) ...
 Image geostudio-qgis-worker Built
```
Compose built its own tagged image `geostudio-qgis-worker:latest` from
`./deploy/qgis-worker`'s `build:` key (all layers cached from Task 4's
earlier manual build, so this was fast — expected, not a shortcut taken).

```
$ docker compose --profile etl up -d qgis-worker
 Network geostudio_gis-net Creating
 Network geostudio_gis-net Created
 Volume geostudio_etl-scratch Creating
 Volume geostudio_etl-scratch Created
 Container geostudio-qgis-worker-1 Creating
 Container geostudio-qgis-worker-1 Created
 Container geostudio-qgis-worker-1 Starting
 Container geostudio-qgis-worker-1 Started
```

```
$ sleep 5 && docker compose --profile etl ps qgis-worker
NAME                      IMAGE                   COMMAND                  SERVICE       CREATED          STATUS          PORTS
geostudio-qgis-worker-1   geostudio-qgis-worker   "python3 /app/server…"   qgis-worker   13 seconds ago   Up 12 seconds

$ docker compose --profile etl logs qgis-worker
(no output)
```
Container status `Up`, no crash-loop, no log output — matches the expected
success signal for the `ThreadingHTTPServer.serve_forever()` blocking call
from Task 4.

```
$ docker compose --profile etl down
 Container geostudio-qgis-worker-1 Stopping
 Container geostudio-qgis-worker-1 Stopped
 Container geostudio-qgis-worker-1 Removing
 Container geostudio-qgis-worker-1 Removed
 Network geostudio_gis-net Removing
 Network geostudio_gis-net Removed
```
Clean teardown. (The `etl-scratch` named volume itself persists across
`down`, which is normal compose behavior — it is not removed by `down`
without `-v`.)

## Files changed

- `docker-compose.yml` (only file touched; +21/-0 lines)

Full diff:
```diff
--- a/docker-compose.yml
+++ b/docker-compose.yml
@@ -6,6 +6,7 @@ volumes:
   pg-data:
   minio-data:
   keycloak-data:
+  etl-scratch:
 
 services:
 
@@ -173,10 +174,30 @@ services:
       CORE_BASE_URL: ${CORE_BASE_URL:-http://localhost:8200}
       OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-lgtm:4318
       OTEL_SERVICE_NAME: geostudio-worker
+      QGIS_WORKER_URL: http://qgis-worker:8000
+      QGIS_WORKER_TIMEOUT_SECONDS: "600"
+    volumes:
+      - etl-scratch:/scratch
     networks: [gis-net]
     depends_on: [pgbouncer, minio]
     restart: unless-stopped
 
+  # Sidecar QGIS Processing étage 2 (SP-15d, arbitrage A39 — GPL en
+  # sous-processus isolé, cœur Apache-2.0 intact). Profil `etl` : un
+  # `docker compose up` par défaut ne le démarre pas, même porte que
+  # CORE_ETL_ENABLED. Aucune credential DB, aucun accès réseau externe —
+  # ne voit que le volume scratch partagé avec `worker` (garde
+  # anti-confused-deputy, patron SP-6a).
+  qgis-worker:
+    build: ./deploy/qgis-worker
+    profiles: ["etl"]
+    environment:
+      QT_QPA_PLATFORM: offscreen
+    volumes:
+      - etl-scratch:/scratch
+    networks: [gis-net]
+    restart: unless-stopped
+
   # Worker CDC (SP-11a) — même image que le cœur, process séparé (arbitrage
   # A16). Connexion DIRECTE à postgis:5432, PAS à pgbouncer:6432 : PgBouncer
```

## Self-review

- **Completeness**: all 6 steps done and verified for real, no automated
  test suite exists for this task, so the compose validation commands
  (Step 4) plus the manual smoke test (Step 5) constitute the full
  verification.
- **Quality**: YAML matches the brief exactly, indentation (2 spaces per
  nesting level) is consistent with the rest of the file. `qgis-worker` has
  no `depends_on` (correct — it has no dependency on postgis/minio/etc,
  matches its "no credentials, no DB access" design). `worker:`'s new
  `volumes:` key is placed between `environment:` and `networks:` as
  specified.
- **Discipline**: only `docker-compose.yml` was staged and committed
  (`git status --short` before commit confirmed no other file was staged
  — this repo currently has several unrelated pre-existing modified/
  untracked files from other sessions, none touched here).
- Confirmed `git diff docker-compose.yml` before commit matches the brief's
  YAML snippets verbatim.

## Issues or concerns

None. The task went exactly as specified — the current file's structure
matched the brief's assumptions precisely (worker: at line 156 with an
environment block and no volumes key, cdc-worker: at line 185, top-level
volumes with pg-data/minio-data — plus a pre-existing keycloak-data: not
mentioned in the brief but harmless to leave alongside).

One minor observation, not a defect: `docker compose --profile etl down`
does not remove the `etl-scratch` volume (expected default behavior); it
was left in place after the smoke test. This is fine — it's an ordinary
compose volume that will be reused/recreated as needed and contains no
sensitive data (scratch space only).

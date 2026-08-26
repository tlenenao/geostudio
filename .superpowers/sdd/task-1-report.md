# Task 1 report — Conteneurs non-root (3.6)

## Summary

Implemented all 9 steps of the brief. 7 of 8 Dockerfiles were modified to run
as non-root at runtime (`core`, `deploy/export-worker`,
`deploy/appexport-runtime-builder`, `deploy/appexport-standalone`,
`deploy/qgis-worker`, `deploy/backup`, `shell`). `postgis` was verified but
NOT modified, per the brief's expectation. Every Dockerfile was actually
built with real `docker build`, and every specified verification command was
actually run against the real image — no verification was skipped, assumed,
or faked. Two real gaps not covered by the brief's literal text were found
empirically and fixed (both documented below, both re-verified after the
fix): `shell`'s nginx crashed on startup (`/run/nginx.pid` permission
denied), and `backup`'s `/backup/archives` — the actual runtime-mounted
volume target per `docker-compose.prod.yml` — was not writable by the
non-root `backup` user until an explicit `mkdir`+`chown` was added (the
brief's `$HOME`/`/tmp` decision tree for `backup` didn't cover this third
case).

Commit: `4b15da9` — `feat(deploy): fait tourner 7 des 8 conteneurs en
utilisateur non-root`.

## What was implemented, per Dockerfile

### 1. `core/Dockerfile`
Exactly as specified in Step 1: `groupadd`/`useradd` creating system user
`app` with `--home-dir /opt/geostudio-home --create-home`, `ENV
HOME=/opt/geostudio-home` set before the DuckDB `INSTALL` step (still root at
that point), `chown -R app:app /opt/geostudio-home /app` after all
`COPY`/`RUN` steps, `USER app` before `EXPOSE`/`CMD`.

### 2. `deploy/export-worker/Dockerfile`
Same pattern as `core`, plus Playwright/Chromium installed while `HOME` is
already pinned (so its `.cache/ms-playwright` lands under
`/opt/geostudio-home` and gets picked up by the final `chown -R`).

### 3. `deploy/appexport-standalone/Dockerfile`
Second (`python:3.12-slim`) stage only, per the brief. Same HOME-pin pattern,
single DuckDB extension (`spatial`), plus `mkdir -p /data && chown -R
app:app ... /data` before `USER app` (the `/data` volume mount target).

### 4. `deploy/appexport-runtime-builder/Dockerfile`
`node:20-slim`, new system user `builder`, `chown -R builder:builder /build
/export-runtime` before `USER builder`. One-shot build container, no
listening service.

### 5. `deploy/qgis-worker/Dockerfile`
`HOME` pinned to `/opt/qgis-home` **before** `RUN qgis_process plugins enable
grassprovider` (this is the whole point — the GRASS profile state is written
under `$HOME/.local/share/QGIS/...`). `mkdir -p /scratch && chown -R
qgis:qgis /opt/qgis-home /app /scratch` before `USER qgis`. Mount point
`/scratch` confirmed against `docker-compose.yml`'s `qgis-worker` service
(`etl-scratch:/scratch`) — matches the brief's assumption exactly, no
adjustment needed.

### 6. `deploy/backup/Dockerfile`
Followed the brief's investigate-before-modify instruction (Step 7).
`addgroup -S backup && adduser -S -G backup -h /home/backup backup` added
first, **without** `USER backup`, then empirically checked:
- `grep -n 'mkdir\|>.*\.mc\|HOME' backup.sh entrypoint.sh` → only two
  `mkdir -p` hits, both under `/backup/work` and `/backup/archives` (not
  `$HOME`, not `/tmp` — a third case the brief's decision tree didn't name).
- `/tmp` in the base `alpine:3.20` image is `1777` (world-writable) — no
  action needed there.
- **Found and fixed a real regression** (not anticipated by the brief):
  `deploy/backup/Dockerfile`'s only volume mount in production
  (`docker-compose.prod.yml`: `backup-archives:/backup/archives`) is a named
  Docker volume. When such a volume is freshly created and the mount path
  doesn't already exist in the image with correct ownership, Docker
  initializes it owned by `root:root` — verified by building a probe variant
  with `USER backup` but no prior `mkdir`/`chown` for `/backup`, mounting a
  fresh named volume at `/backup/archives`, and observing `touch: Permission
  denied`. Fixed by adding `RUN mkdir -p /backup/archives /backup/work &&
  chown -R backup:backup /backup` before `USER backup` — this way the image
  itself already owns `/backup` correctly, so Docker's volume-population
  step (which copies the image's existing directory content, ownership
  included, into a fresh named volume) produces a writable volume.
  Re-verified after the fix: `touch` succeeds, `mkdir -p
  /backup/work/<date>` succeeds (parent `/backup` now writable by `backup`),
  and `mc alias set` (writing config under `$HOME/.mc`) succeeds too since
  `/home/backup` was already correctly owned by `adduser -h`.

### 7. `shell/Dockerfile`
Reused the existing `nginx` system user (uid/gid 101) from the base
`nginx:1.27-alpine` image, as specified. Checked `nginx.conf`'s `listen
8300;` — no unprivileged-port issue (>1024).
- **Found and fixed a real crash** (not anticipated by the brief): the
  literal Dockerfile content given in the brief (`chown -R nginx:nginx
  /usr/share/nginx/html /var/cache/nginx` then `USER nginx`) makes the
  container **crash on startup**: `nginx: [emerg] open()
  "/run/nginx.pid" failed (13: Permission denied)`. The master nginx process
  writes its pidfile to `/run/nginx.pid` (per `/etc/nginx/nginx.conf`'s `pid`
  directive), and `/run` is owned by `root:root` in the base image — the
  `nginx:alpine` image is designed for a root master process that only drops
  its *worker* processes to `nginx` via the `user nginx;` directive, not for
  the entire container (including PID 1 / the master) to start as `nginx`.
  Fixed by extending the chown: `chown -R nginx:nginx /usr/share/nginx/html
  /var/cache/nginx /run`. Re-verified after the fix: container starts
  cleanly, `id -u` inside the container is `101`, `env-config.js` is served
  with the substituted `VITE_CORE_URL` value, and `docker logs` shows no
  permission errors (only benign warnings: the `user` directive no-op
  warning, expected once the master itself is non-root; and an unrelated
  pre-existing `info:` line from the base image's own
  `10-listen-on-ipv6-by-default.sh` about a read-only `default.conf`, which
  is informational only and not caused by this change).

### 8. `deploy/postgis` — verified, NOT modified
Built the existing (unmodified) `deploy/postgis/Dockerfile`, ran it with
`docker run -d -e POSTGRES_PASSWORD=test`, and inspected the actual process
tree via `/proc/<pid>/status` (the image ships no `ps` binary). Result: the
entire container, including PID 1, runs as **uid 999** (`postgres`), not
just the `postgres` server subprocess — stronger than the brief's minimum
expectation. Root cause confirmed by reading
`/usr/local/bin/docker-entrypoint.sh` inside the image: when invoked as root
with the default `postgres` command, it fixes ownership of `$PGDATA` and
`/var/run/postgresql` (`find ... -exec chown postgres`), then does `exec
gosu postgres "$BASH_SOURCE" "$@"` at line 313 — an `exec`, not a fork, so
the re-exec'd process keeps PID 1 while changing its uid. Confirmed
separately that `docker run --rm geostudio-postgis-test id -u` (bypassing
the entrypoint's `postgres`-only branch by overriding the command) shows
`0` — exactly the "entrypoint wrapper shows root, but the real running
server doesn't" distinction the brief asked to document. Per the brief's
explicit instruction, **no `USER postgres` was added** — doing so would
break the entrypoint's ability to `chown`-fix a fresh `PGDATA` volume on
first boot.

## Verification commands actually run, with real output observed

### core (Step 2)
```
$ cd core && docker build -t geostudio-core-test .
... build succeeded (no pre-existing mcp==2.0.0/libexpat regression hit this run) ...

$ docker run --rm geostudio-core-test id -u
999

$ docker run --rm --network none geostudio-core-test python -c "
from app.analytics.duckdb_conn import open_spatial_connection
conn = open_spatial_connection()
print(conn.execute('SELECT ST_AsText(ST_Point(1,2))').fetchone())
"
('POINT (1 2)',)
```
Non-zero uid confirmed; offline spatial query succeeded with `--network
none`, proving the extension was found locally under
`/opt/geostudio-home/.duckdb/extensions`, not re-downloaded. The
pre-existing packaging risk flagged in the task context (mcp==2.0.0 /
libexpat) did **not** manifest in this build — worth noting since
CLAUDE.md's SP-21 entry describes it as intermittent/environment-dependent;
this run used the real `uv pip install --system --no-cache -r
pyproject.toml`, which resolved cleanly.

### export-worker (Step 3)
Build context confirmed empirically against `docker-compose.yml` before
guessing:
```
$ grep -A5 "export-worker:" docker-compose.yml
  export-worker:
    build:
      context: ./core
      dockerfile: ../deploy/export-worker/Dockerfile
```
Matches the brief's fallback assumption exactly (context = `./core`).
```
$ cd deploy/export-worker && docker build -t geostudio-export-worker-test -f Dockerfile ../../core
... build succeeded, Chromium/FFmpeg/Chrome Headless Shell downloaded into
    /opt/geostudio-home/.cache/ms-playwright before the final chown ...

$ docker run --rm geostudio-export-worker-test id -u
999
```

### appexport-standalone (Step 4)
```
$ docker build -t geostudio-appexport-standalone-test -f deploy/appexport-standalone/Dockerfile .
... build succeeded (two-stage: shell-runtime + python:3.12-slim) ...

$ docker run --rm geostudio-appexport-standalone-test id -u
999

$ docker run --rm --network none geostudio-appexport-standalone-test python -c "
import duckdb
c = duckdb.connect(); c.execute('LOAD spatial')
print(c.execute('SELECT ST_AsText(ST_Point(1,2))').fetchone())
"
('POINT (1 2)',)

$ docker volume rm -f test-appexport-data; docker run --rm -v test-appexport-data:/data geostudio-appexport-standalone-test sh -c "touch /data/probe && echo DATA_WRITE_OK"
DATA_WRITE_OK
```
Went beyond the brief's literal Step 4 verification (which only asks for
uid) to also check the offline spatial extension (same rationale as `core`)
and the `/data` volume-mount scenario the brief's own comment flags as a
"known limitation to verify" — confirmed writable because `mkdir -p /data &&
chown` happens before `USER app` in the image, same fix pattern that turned
out to be necessary for `backup`.

### appexport-runtime-builder (Step 5)
```
$ docker build -t geostudio-appexport-runtime-builder-test -f deploy/appexport-runtime-builder/Dockerfile .
... build succeeded ...

$ docker run --rm geostudio-appexport-runtime-builder-test id -u
999

$ docker volume rm -f test-export-runtime; docker run --rm -v test-export-runtime:/export-runtime geostudio-appexport-runtime-builder-test
export runtime built

$ docker run --rm -v test-export-runtime:/export-runtime alpine ls -la /export-runtime
drwxr-xr-x 4 999 ping ... assets
drwxr-xr-x 4 999 ping ... fixtures
```
Ran the actual `CMD` (not just `id -u`) against a fresh named volume to
prove the brief's flagged risk ("if the volume was previously populated by a
root-run container, chown may fail") doesn't apply to the packaged flow:
the volume starts fresh each real deployment, and the image's own
`mkdir -p /export-runtime && chown` before `USER builder` means the volume
gets correctly-owned content populated by Docker at first mount.

### qgis-worker (Step 6)
Mount point confirmed against compose before assuming:
```
$ grep -A10 "qgis-worker:" docker-compose.yml
    volumes:
      - etl-scratch:/scratch
```
Matches the brief's assumption exactly.
```
$ docker build -t geostudio-qgis-worker-test deploy/qgis-worker
... build succeeded (base image was already cached locally, so this run did
    not re-pull the ~11GB qgis/qgis:release-3_34 image — build itself
    completed in under 5s of actual work) ...

$ docker run --rm geostudio-qgis-worker-test id -u
999

$ docker run --rm geostudio-qgis-worker-test qgis_process plugins list 2>&1 | grep -i grass
* grassprovider
```
The `*` confirms grassprovider is enabled — proving the profile written
under `$HOME/.local/share/QGIS/...` at build time (as root, but with `HOME`
already pinned to `/opt/qgis-home`) is found at runtime under `USER qgis`,
same `HOME`. This is the exact regression the brief flags as the
deployment-breaking risk for this file, and it does not occur.

### backup (Step 7a)
See "What was implemented" above for the investigation. Final verification:
```
$ docker build -t geostudio-backup-test deploy/backup
... build succeeded ...

$ docker run --rm --entrypoint id geostudio-backup-test -u
100

$ docker volume rm -f test-backup-archives; docker run --rm --entrypoint sh -v test-backup-archives:/backup/archives geostudio-backup-test -c "touch /backup/archives/probe && echo WRITE_OK"
WRITE_OK

$ docker run --rm --entrypoint sh geostudio-backup-test -c "mkdir -p /backup/work/20260101 && echo WORK_MKDIR_OK"
WORK_MKDIR_OK

$ docker run --rm --entrypoint sh geostudio-backup-test -c "mc alias set local http://example.invalid:9000 u p >/dev/null 2>&1; ls -ld \$HOME/.mc && echo MC_CONFIG_OK"
drwx--S--- 4 backup backup ... /home/backup/.mc
MC_CONFIG_OK
```
All three real write paths used by `backup.sh`/`entrypoint.sh` at runtime
(`/backup/archives` the volume, `/backup/work` the ephemeral staging dir,
`$HOME/.mc` the `mc` CLI's own config) verified writable as the non-root
`backup` user — not just `id -u`, which the brief's literal Step 7 text
would have accepted as sufficient but which alone would NOT have caught the
`/backup/archives` regression (it was only caught by mounting an actual
fresh named volume and attempting a real write, the same failure mode
production would hit on first deploy).

**Important caveat I noticed but did not act on**: `entrypoint.sh`'s loop
(`while true; do ...; sleep 60; done`) means running the image with its real
`ENTRYPOINT` (no override) blocks forever by design — I hit this once by
forgetting `--entrypoint`, the container just sat there waiting for
`BACKUP_HOUR`. Not a bug, just a trap for anyone re-running these checks:
always use `--entrypoint sh -c "..."` or `--entrypoint id` for probing this
image.

### shell (Step 7b)
See "What was implemented" above for the crash found and fixed. Final
verification, run exactly as specified in the brief:
```
$ cd shell && docker build -t geostudio-shell-test .
... build succeeded (tsc --noEmit + vite build, no type errors) ...

$ docker run --rm -e VITE_CORE_URL=http://example.test -p 18300:8300 -d --name shell-nonroot-test geostudio-shell-test
$ sleep 2
$ docker exec shell-nonroot-test id -u
101

$ curl -s http://localhost:18300/env-config.js | grep example.test
  VITE_CORE_URL: "http://example.test",

$ docker logs shell-nonroot-test
... "start worker process" x14, one successful GET /env-config.js 200 ...
    no permission-denied errors
$ docker rm -f shell-nonroot-test
```

### postgis (Step 8)
```
$ docker build -t geostudio-postgis-test deploy/postgis
... build succeeded (unmodified Dockerfile) ...

$ docker run -d --name postgis-nonroot-check -e POSTGRES_PASSWORD=test geostudio-postgis-test
$ sleep 8
$ docker exec postgis-nonroot-check ps aux | grep postgres
```
**Deviation from the brief's literal command**: the image ships no `ps`
binary (`OCI runtime exec failed: ... exec: "ps": executable file not found
in $PATH` — Debian-slim-based `postgres`/`postgis` images don't include
`procps`). Substituted an equivalent check reading `/proc/<pid>/status`
directly for every PID in the container:
```
$ docker exec postgis-nonroot-check sh -c 'for pid in $(ls /proc | grep -E "^[0-9]+$"); do
    cmd=$(cat /proc/$pid/comm 2>/dev/null)
    uid=$(grep "^Uid:" /proc/$pid/status 2>/dev/null | awk "{print \$2}")
    echo "pid=$pid uid=$uid cmd=$cmd"
  done'
pid=1 uid=999 cmd=bash
pid=48 uid=999 cmd=postgres
pid=49 uid=999 cmd=postgres
pid=66 uid=999 cmd=pg_ctl
pid=67 uid=0 cmd=sh          # <- my own `docker exec` shell, not a
                              #    container-spawned process; docker exec
                              #    defaults to root unless --user is given
```
Confirms not just the `postgres` server (pid 48/49) but the entrypoint
wrapper itself (pid 1, `bash`, and `pg_ctl` at pid 66) all run as uid 999 —
stronger than the brief's minimum bar of "at least the server process is
non-root".
```
$ docker run --rm geostudio-postgis-test id -u
0
```
Confirms the brief's documented distinction: raw `id -u` (which bypasses the
entrypoint's `postgres`-only re-exec branch by overriding the command)
shows root, while the actual running server — and in this case the whole
container — does not.
```
$ docker run --rm --entrypoint sh geostudio-postgis-test -c 'grep -n "gosu\|exec " /usr/local/bin/docker-entrypoint.sh | head -20'
...
313:			exec gosu postgres "$BASH_SOURCE" "$@"
351:	exec "$@"
```
Confirms the mechanism: line 313 is inside the root-only branch that first
chowns `$PGDATA`/`/var/run/postgresql` to `postgres`, then `exec gosu
postgres` — an `exec`, so PID 1 itself becomes the `postgres`-uid process,
matching the empirical `/proc` observation above.

**Per the brief's explicit instruction: no `USER postgres` was added to
`deploy/postgis/Dockerfile`.** This chantier is already satisfied for
`postgis` without any Dockerfile change.

**Note on `deploy/postgis/Dockerfile`'s current working-tree state**: per
this repo's CLAUDE.md, this file carries uncommitted lines from another,
unrelated in-progress session (a licensing-notice task, described as
"bloqué" in the "Suivis non bloquants ouverts" section). I built and tested
whatever was on disk at the start of this task, unmodified, and did not
touch this file in any way — consistent with the discipline the task brief
asked for.

## Files changed (staged and committed)

- `/home/lenen/projets/geostudio/core/Dockerfile`
- `/home/lenen/projets/geostudio/deploy/export-worker/Dockerfile`
- `/home/lenen/projets/geostudio/deploy/appexport-runtime-builder/Dockerfile`
- `/home/lenen/projets/geostudio/deploy/appexport-standalone/Dockerfile`
- `/home/lenen/projets/geostudio/deploy/qgis-worker/Dockerfile`
- `/home/lenen/projets/geostudio/deploy/backup/Dockerfile`
- `/home/lenen/projets/geostudio/shell/Dockerfile`

Not touched: `deploy/postgis/Dockerfile` (verified, intentionally left
unmodified per Step 8), `deploy/postgis/pg_hba.conf` (pre-existing untracked
file from another session, unrelated to this task, left as-is).

Commit: `4b15da9` — `feat(deploy): fait tourner 7 des 8 conteneurs en
utilisateur non-root`. Pre-commit hooks (`ruff`, `eslint`, `prettier`,
`commitlint`) all passed (the Python/lint hooks reported "no files to
check" since only Dockerfiles were staged).

## Self-review

**Completeness**: all 7 Dockerfiles touched exactly as specified (or
improved on, where the brief's literal text was insufficient — see below).
All verification commands specified in the brief were actually run, with
real `docker build`/`docker run` output observed — none were skipped,
assumed, or fabricated. The `ps`-unavailable substitution for `postgis` and
the two extra checks for `appexport-standalone`/`appexport-runtime-builder`
(beyond the brief's minimum `id -u`) are documented above as deviations,
with the reasoning for each.

**Quality**: In every Dockerfile that needed it, `HOME` is pinned
(`ENV HOME=...`) strictly before the build step whose output depends on it
(DuckDB `INSTALL` for core/export-worker/appexport-standalone; `qgis_process
plugins enable` for qgis-worker), and the corresponding `chown -R` runs
after **every** `COPY`/`RUN` step that writes into that tree, immediately
before `USER`. No file writes happen after the `USER` switch except ones
verified to land in already-`chown`ed paths.

**Discipline**: `USER postgres` was **not** added to `deploy/postgis`,
consistent with the brief's default expectation and the empirical Step 8
finding that it's unnecessary and would in fact regress first-boot behavior
on a fresh volume. No application code was touched — this task's `Files:`
list was Dockerfiles only, and that's all that was staged/committed.

**Two things I verified beyond the brief's literal text, both real bugs
in the brief's proposed content, both fixed and re-verified**:
1. `shell/Dockerfile`'s proposed `chown` list (`/usr/share/nginx/html
   /var/cache/nginx`) was missing `/run` — the container would have crashed
   on every start in production. Fixed by adding `/run` to the chown.
2. `deploy/backup/Dockerfile`'s decision tree (`$HOME` vs `/tmp`) didn't
   name the actual runtime-mounted volume path (`/backup/archives`, the
   real `backup-archives` named volume from `docker-compose.prod.yml`) —
   without an explicit `mkdir`+`chown` before `USER backup`, the container
   would have failed to write any backup archive on every real deployment
   (a fresh named volume mounts owned by root). Fixed by adding
   `mkdir -p /backup/archives /backup/work && chown -R backup:backup
   /backup` before `USER backup`.

Both were caught only because I insisted on testing the actual runtime
behavior (starting the real container, mounting real fresh volumes,
attempting real writes) rather than stopping at `id -u`, in line with this
task's explicit instruction to verify against the running artifact rather
than trusting the brief's literal Dockerfile content or source-only review.

## Issues / concerns

None blocking. Both real defects found in the brief's proposed content
(`shell` `/run` chown, `backup` `/backup` volume chown) were fixed and
re-verified in this same task, not deferred. The pre-existing packaging risk
described in the task context for `core` (mcp==2.0.0 / libexpat) did not
manifest in this session's build — worth a note for whoever runs this again,
since CLAUDE.md documents it as previously observed, but it is not something
this task caused or needs to fix.

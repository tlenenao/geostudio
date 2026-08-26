# Task 7 report — CSP, Permissions-Policy, compression (3.3)

## Commit history incident (self-caught, fixed)

The brief's suggested commit subject ("feat(deploy): CSP, Permissions-Policy
et compression") fails this repo's commitlint `subject-case` rule (mixed
upper/start-case is rejected — same class of issue SP-22 already documents
happening 3 times). My first `git commit` attempt with that literal subject
was rejected by the `commit-msg` hook and never created a commit. I then ran
`git commit --amend` to fix the subject — but since the first attempt never
actually committed, `--amend` amended the **previous real commit** (Task 6's
`feat(shell): error boundary applicatif à la racine`, `3598ce2`) instead,
silently merging Task 7's files into it and losing Task 6's commit as a
separate entry in history. Caught immediately by inspecting `git show --stat
HEAD` (showed `shell/src/App.tsx`/`AppErrorBoundary.*` files I never
touched) and `git reflog` (confirmed `3598ce2` was still a reachable object,
just no longer pointed to by any ref). Fixed with `git reset --soft 3598ce2`
(restores Task 6's commit as HEAD, keeps Task 7's changes staged in the
index/working tree unchanged) followed by a normal `git commit` (not
`--amend`) with a lowercased, commitlint-passing subject. Verified after the
fix: `3598ce2` shows its original 3 files
(`App.tsx`/`AppErrorBoundary.tsx`/`AppErrorBoundary.test.tsx`, 88
insertions), and the new Task 7 commit (`36ac18c`) shows only the 2 in-scope
files (`docker-compose.prod.yml`/`shell/nginx.conf`, 20 insertions). No data
was lost; both commits are intact and separate. Lesson for future sessions:
after a `commit-msg` hook rejects a commit, never blindly `--amend` — check
`git log`/`git status` first to confirm a new commit actually landed.

## What was implemented

1. **`docker-compose.prod.yml`** — extended the existing `security-headers`
   Traefik middleware (did not create a new middleware) with:
   - `customResponseHeaders.Content-Security-Policy-Report-Only` (Report-Only,
     not enforcing — see "Why Report-Only was kept" below)
   - `customResponseHeaders.Permissions-Policy`
   - a new `compress` middleware (`traefik.http.middlewares.compress.compress=true`)
   - `compress@docker` chained into both `core` and `shell` routers'
     `middlewares=` label

2. **`shell/nginx.conf`** — added the equivalent for the dev/standalone/export
   path that bypasses Traefik entirely: `gzip on` + `gzip_types`/`gzip_min_length`,
   and `add_header` for `X-Content-Type-Options`, `Referrer-Policy`,
   `Permissions-Policy`, `Content-Security-Policy-Report-Only` (kept `'self'`
   only for `connect-src`/`img-src`, no hardcoded host, per the brief's
   reasoning — this file also serves SP-18a/c export/standalone bundles whose
   core origin is baked in at build/runtime, not known here).

## A real bug found and fixed along the way

The brief's literal Step 1 YAML (line 28 of the brief) is **not valid YAML**:
the CSP directive value contains `data: blob:` (colon-space sequences), which
an unquoted YAML plain scalar cannot contain — colon+space starts a mapping.
Confirmed empirically: `docker compose -f docker-compose.yml -f
docker-compose.prod.yml config` failed with `yaml: line 113, column 268:
mapping values are not allowed in this context` when I first wrote the label
unquoted exactly as literally given. Fixed by wrapping that one label in
double quotes (the Permissions-Policy label doesn't need it — no colon+space
in `camera=(), microphone=(), payment=(), usb=()`). Re-ran `config` after the
fix: exit 0, and the resolved labels are correct (see below) — this is a
genuine improvement over the brief's literal text, not a deviation from its
intent.

## What was actually live-verified vs. config/curl-only (be honest)

**Environment constraints hit, both pre-existing and unrelated to this task's
own changes:**

- No Chrome/Chromium binary is installed in this sandboxed environment at all
  (`which google-chrome chromium chromium-browser` → nothing;
  `/opt/google/chrome/` doesn't exist). Both Playwright's
  `browser_navigate` and chrome-devtools-mcp's `new_page` failed outright
  trying to launch a browser. This means **no DevTools-console-level CSP
  violation check was possible in this environment, full stop** — not because
  of anything about this task's changes, but because there is no browser here
  to check with.
- Separately, `docker compose up -d --build` on the base (dev) stack hit the
  **pre-existing, unrelated** packaging bug already documented in this repo's
  CLAUDE.md ("Suivis non bloquants ouverts", SP-21): the locally-built `core`
  image resolves `mcp==2.0.0` at build time (ignoring `uv.lock`), which
  breaks `from mcp.server.fastmcp import FastMCP` at import time
  (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`) — reproduced
  and captured in full in `docker compose logs core`. `core` never becomes
  healthy, so `shell`'s hard `depends_on: core: condition: service_healthy`
  means the full app (map editor, builder, Keycloak SSO) can never be
  exercised end to end here. This confirms, rather than contradicts, what the
  task instructions warned about.
- Also hit (unrelated, host-level): `martin`'s host port 3000 binding fails
  at the Docker daemon level (`ports are not available: exposing port TCP
  0.0.0.0:3000 -> 127.0.0.1:0: /forwards/expose returned unexpected status:
  500`) — reproduced independently with a bare `docker run -p 3000:3000
  nginx:alpine`, so this is a Docker/WSL2 networking issue on this host, not
  anything about this task's compose changes. `martin` is not a dependency of
  `core` or `shell` so this didn't block the rest.

**What I actually did verify live**, by running the real built `shell` image
standalone (`docker run -d -p 8300:8300 geostudio-shell:latest`, i.e. the
exact image `docker compose build` produced, bypassing the `core` dependency
since header/gzip behavior is nginx-only and doesn't need `core`):

```
$ curl -sI http://localhost:8300/
HTTP/1.1 200 OK
...
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), payment=(), usb=()
Content-Security-Policy-Report-Only: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; object-src 'none'
```

- `index.html` (437 bytes, below `gzip_min_length 1024`): correctly **not**
  gzip-compressed — confirms `gzip_min_length` is respected, not just present.
- The built JS bundle (`/assets/index-*.js`, ~3 MB): `curl -sI -H
  'Accept-Encoding: gzip' ...` → `Content-Encoding: gzip` present. Live,
  real gzip compression confirmed against the actual built asset.

**What was config-only, not live** (exactly what the brief's own Step 6
anticipates as acceptable for the Traefik-fronted path):

```
$ docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```
resolved cleanly (exit 0) after the quoting fix, and the resolved labels
confirm (grepped from the resolved output):
```
core router:
  traefik.http.routers.core.middlewares: security-headers@docker,rate-limit@docker,compress@docker,strip-api@docker
shell router:
  traefik.http.routers.shell.middlewares: security-headers@docker,rate-limit@docker,compress@docker
  traefik.http.middlewares.compress.compress: "true"
  traefik.http.middlewares.security-headers.headers.customResponseHeaders.Content-Security-Policy-Report-Only: 'default-src ''self''; ... connect-src ''self'' https://changez-moi.exemple.ts.net; ...'
  traefik.http.middlewares.security-headers.headers.customResponseHeaders.Permissions-Policy: camera=(), microphone=(), payment=(), usb=()
```
`${GEOSTUDIO_PUBLIC_HOST}` substitution confirmed working (resolved to the
`.env` placeholder value). This proves the labels are syntactically correct
and attach to the right routers — it does **not** prove Traefik actually
emits these headers/compresses responses at runtime, since the prod overlay
was never brought up as a live stack (blocked by the same `core` packaging
bug above, which affects `core` regardless of dev vs. prod overlay since it's
a Dockerfile/build-time issue, and I did not attempt to pull real `ghcr.io`
images to route around it — out of scope for this task to investigate).

## Why Report-Only was kept (Step 5 not executed)

Step 5 says to flip to enforcing "once Step 4 shows no unexpected
violations." I have **no evidence** either way about violations — I could not
open a browser at all in this environment (no Chromium binary), so there is
no DevTools console to have shown violations or their absence. Per this
task's own explicit instructions ("enforcing CSP only shipped if you could
verify no unexpected breakage, or Report-Only left in place with an honest
note if you couldn't fully verify") and this repo's established discipline
("être honnête sur ce qui a été et n'a pas été réellement exécuté"), both
`docker-compose.prod.yml` and `shell/nginx.conf` keep
`Content-Security-Policy-Report-Only`, not enforcing `Content-Security-Policy`.
Step 5 is explicitly **not done** — flipping to enforcing is left for a
future session with a real browser and a working `core` image.

## Deployability guard (Step 7)

```
cd core && uv run pytest tests/test_deployability.py -v
```
Result: **31/31 passed**, 0 failed — no new env var substitution introduced
by this task (CSP values are hardcoded strings except the pre-existing
`${GEOSTUDIO_PUBLIC_HOST}`), consistent with the expectation in the task
brief.

## Files changed

- `docker-compose.prod.yml` — `security-headers` middleware extended
  (CSP-Report-Only + Permissions-Policy), new `compress` middleware, chained
  into `core` and `shell` routers.
- `shell/nginx.conf` — gzip + the same 4 headers added.

No other files touched. `deploy/postgis/pg_hba.conf` (untracked, pre-existing,
unrelated — documented in CLAUDE.md as inert) was left alone and not staged.

## Self-review

- **Completeness**: CSP/Permissions-Policy/compress added to the *existing*
  `security-headers` middleware (not a new one) — yes. Chained into both
  `core` and `shell` routers — yes, confirmed via resolved `docker compose
  config`. `nginx.conf` gets the equivalent gzip+headers — yes, live-curl
  confirmed. Enforcing CSP: **not** shipped (Report-Only kept), with an
  honest note above — per this task's explicit instructions, this is the
  correct call given no browser was available to verify "no unexpected
  breakage."
- **Quality**: CSP directive values match the brief exactly, character for
  character, in both files — the only change from the brief's literal text
  is wrapping the one Traefik CSP label in double quotes, which is a YAML
  *syntax* fix (the unquoted form doesn't parse), not a value change.
- **Discipline**: only the 2 named files are modified (`git diff --stat`
  confirms). No scope creep — did not attempt to fix the pre-existing
  `mcp==2.0.0`/`martin` port/Chrome-binary environment issues, per explicit
  instruction that these are out of scope.

## Concerns / honest gaps for a future session

- Full browser-based CSP violation checking (all 4 manual checks in Step 4)
  was **not possible at all** in this environment — no Chromium/Chrome binary
  installed, both Playwright and chrome-devtools-mcp failed to launch a
  browser. This is a tooling gap of the current sandbox, not something fixed
  or worked around here.
- `core` cannot reach a healthy state via `docker compose up` in this
  environment due to the pre-existing, already-documented `mcp==2.0.0`
  packaging bug (SP-21 "Suivis non bloquants ouverts") — reproduced again
  here, not introduced by this task, not fixed (out of scope).
- Because of the above two points, Step 5 (flip to enforcing) is not done.
  The next session that has both a real browser and a working `core` build
  should do the 4 manual checks from Step 4 against enforcing CSP before
  flipping the header name in both files.
- Traefik's actual real-world emission of `compress@docker` and the CSP
  headers was verified by config resolution only, not by a live `curl`
  against a running Traefik — consistent with what the brief's own Step 6
  explicitly anticipated as an acceptable fallback.

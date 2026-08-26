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


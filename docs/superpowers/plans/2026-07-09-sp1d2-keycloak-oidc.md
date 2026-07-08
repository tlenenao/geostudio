# SP-1d.2 — Réalm Keycloak & mode `oidc` réel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a Keycloak realm export into the dev `docker-compose` stack so `CORE_AUTH_MODE=oidc` (already built in SP-1a, only exercised in `mock` mode until now) and the shell's real OIDC login flow (`react-oidc-context`, already built) can run end-to-end for the first time, and document the manual verification procedure.

**Prerequisite (blocking, external to this plan):** a realm export JSON at `deploy/keycloak/geostudio-realm.json`, containing: realm `geostudio`; client `geostudio-shell` (public, PKCE/"Standard flow" enabled, valid redirect URI matching `VITE_OIDC_REDIRECT_URI`, web origins `+` for CORS); client `geostudio-core` (confidential/bearer-only, audience `geostudio-core` — matches `CORE_OIDC_AUDIENCE`'s existing default in `docker-compose.yml`); a couple of demo users with passwords. This file is being produced outside this plan (Tanguy is creating and exporting it from a running Keycloak instance). **Task 1's first step is to check for this file and its expected shape — if it's missing, stop and report exactly what's needed rather than inventing realm content**, since the realm's actual security configuration (client secrets, redirect URIs, user passwords) is not something this plan should author from scratch.

**Architecture:** Keycloak already runs in `docker-compose.yml` today (`start-dev`, backed by Postgres, no realm import). This plan changes its `command` to `start-dev --import-realm` and mounts the realm file into `/opt/keycloak/data/import/`, matching Keycloak's own auto-import convention (no custom import scripting needed). The cœur's `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` defaults in `docker-compose.yml` already point at realm `geostudio`/client `geostudio-core` (set correctly back in SP-1a) — only the **shell's** `Dockerfile` build-arg defaults are stale (`VITE_OIDC_AUTHORITY` still defaults to a `gis-platform` realm name, `VITE_OIDC_CLIENT_ID` still defaults to bare `shell`) and need fixing to match. No application code changes — `AuthProvider.tsx`/`useAuth.ts` (real `react-oidc-context` wiring) and the cœur's `app/auth/dependency.py` (JWKS validation) were both already built in SP-1a and need no changes, only a real realm to talk to.

**Tech Stack:** Keycloak 24 (`quay.io/keycloak/keycloak:24`, already the pinned image), Docker Compose. No new dependency.

## Global Constraints

- This plan does **not** create or design the realm's security content (client secrets, user passwords, redirect URI list) — that's the external prerequisite above. It only wires whatever realm file is provided into the compose stack and validates the wiring works.
- Realm name `geostudio`, clients `geostudio-shell` (public/PKCE) and `geostudio-core` (bearer-only, audience-validated) — these exact names are already load-bearing in already-merged code (`docker-compose.yml`'s `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` defaults, `core/app/auth/dependency.py`'s JWKS/issuer/audience validation from SP-1a) — the realm file must match them, not the other way around.
- Import failure must be loud: if `--import-realm` fails (invalid JSON, conflicting realm), Keycloak must not silently start in a broken state — add a healthcheck so `docker compose ps`/`depends_on: condition: service_healthy` surfaces it (per the SP-1d spec's §5 error-handling requirement).
- The manual `oidc` end-to-end verification (login → token → `GET /me`) is **not** automated in this plan — it's a documented README checklist, per the SP-1d spec's own testing strategy (§6: "un test manuel (pas e2e automatisé)"). The 13 Playwright e2e specs stay on `VITE_AUTH_MODE=mock` (untouched by this plan — see the separate `sp1d1-core-item-client` plan's Task 4 for their mock rewiring).
- No change to `app/auth/dependency.py`, `AuthProvider.tsx`, or `useAuth.ts` — this plan is pure infrastructure wiring, not auth code.

---

### Task 1: Check the realm file, wire it into `docker-compose.yml`

**Files:**
- Read (prerequisite check, no modification): `deploy/keycloak/geostudio-realm.json`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `deploy/keycloak/geostudio-realm.json` (external prerequisite — realm name `geostudio`, clients `geostudio-shell`/`geostudio-core`).
- Produces: `keycloak` service auto-imports this realm on every start; a healthcheck reports import/startup failure.

- [ ] **Step 1: Verify the prerequisite file exists and has the expected shape**

Run:
```bash
test -f deploy/keycloak/geostudio-realm.json && echo "FOUND" || echo "MISSING"
```
If `MISSING`: **stop here** and report back that `deploy/keycloak/geostudio-realm.json` is required before this task can proceed — do not author a realm file from scratch. If `FOUND`, continue.

Run a shape check:
```bash
python3 -c "
import json
data = json.load(open('deploy/keycloak/geostudio-realm.json'))
assert data.get('realm') == 'geostudio', f'expected realm=geostudio, got {data.get(\"realm\")}'
client_ids = {c.get('clientId') for c in data.get('clients', [])}
assert 'geostudio-shell' in client_ids, f'missing geostudio-shell client, found: {client_ids}'
assert 'geostudio-core' in client_ids, f'missing geostudio-core client, found: {client_ids}'
print('shape OK:', client_ids)
"
```
Expected: `shape OK: {'geostudio-shell', 'geostudio-core'}` (or a superset — extra clients are fine). If this fails, stop and report the exact mismatch rather than adjusting `docker-compose.yml`'s expectations to fit a wrong realm — the realm's names are already load-bearing elsewhere in already-merged code (see Global Constraints).

- [ ] **Step 2: Mount the realm file and switch to `--import-realm`**

In `docker-compose.yml`, change the `keycloak` service:
```yaml
  keycloak:
    image: quay.io/keycloak/keycloak:24
    environment:
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: ${KC_PASSWORD}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgis:5432/gis
      KC_DB_USERNAME: gis
      KC_DB_PASSWORD: ${PG_PASSWORD}
      KC_HEALTH_ENABLED: "true"
    command: start-dev --import-realm
    ports:
      - "8180:8080"
    networks: [gis-net]
    volumes:
      - keycloak-data:/opt/keycloak/data
      - ./deploy/keycloak/geostudio-realm.json:/opt/keycloak/data/import/geostudio-realm.json:ro
    depends_on:
      postgis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "exec 3<>/dev/tcp/localhost/8080 && echo -e 'GET /health/ready HTTP/1.1\\r\\nHost: localhost\\r\\nConnection: close\\r\\n\\r\\n' >&3 && grep -q 'UP' <&3"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
```
(`KC_HEALTH_ENABLED: "true"` turns on Keycloak's built-in `/health/ready` endpoint on the management port, which is exposed on the same `8080` internal port by default in Keycloak 24. The healthcheck uses a raw `/dev/tcp` HTTP request rather than `curl`/`wget` since the Keycloak image doesn't bundle either — matches the constraint that already-running services like `postgis`/`minio` in this same file use `CMD`/`CMD-SHELL` with tools proven present in their own images; verify in Step 3 whether `/dev/tcp` works in this image's shell, and fall back to installing `curl` via a custom entrypoint only if it doesn't — prefer the simpler `/dev/tcp` form first.)

- [ ] **Step 3: Bring the stack up and verify the healthcheck actually detects success**

Run:
```bash
docker compose up -d postgis keycloak
docker compose ps keycloak
```
Expected: after `start_period` (30s) plus a few retries, `docker compose ps keycloak` shows `healthy`, not `starting` indefinitely or `unhealthy`. If the healthcheck command doesn't work in this image (check with `docker compose logs keycloak` for import errors, and `docker compose exec keycloak sh -c '...'` to test the healthcheck command interactively), adjust the `test:` command until it correctly reports healthy only after a successful realm import and ready server — do not leave a healthcheck that always reports healthy regardless of import success (that would defeat the Global Constraint's "loud failure" requirement).

- [ ] **Step 4: Verify the realm was actually imported**

Run:
```bash
curl -s http://localhost:8180/realms/geostudio/.well-known/openid-configuration | python3 -m json.tool | head -5
```
Expected: a valid OpenID configuration JSON (has `issuer`, `authorization_endpoint`, etc.), confirming the `geostudio` realm exists and is served. If this 404s, the import failed silently despite a "healthy" status — go back to Step 3's healthcheck and tighten it (e.g. check `/realms/geostudio` reachability directly instead of just the generic `/health/ready`).

- [ ] **Step 5: Tear down**

Run: `docker compose down`
(Leaves no lingering containers between this task and the next.)

- [ ] **Step 6: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: import the geostudio Keycloak realm on startup, healthcheck"
```
(Do not commit `deploy/keycloak/geostudio-realm.json` in this commit unless it isn't already tracked — check `git status`; if Tanguy already committed it separately, this commit is compose-only.)

---

### Task 2: Fix the shell's stale OIDC defaults; document the manual `oidc` verification

**Files:**
- Modify: `shell/Dockerfile`
- Modify: `README.md`

**Interfaces:**
- Consumes: nothing new.
- Produces: `shell/Dockerfile`'s `VITE_OIDC_AUTHORITY`/`VITE_OIDC_CLIENT_ID` build-arg defaults match the real `geostudio`/`geostudio-shell` realm/client (previously stale from an earlier `gis-platform`/`shell` naming). A new README section walks through the manual real-`oidc` verification.

- [ ] **Step 1: Fix `shell/Dockerfile`'s stale defaults**

(This step assumes the `sp1d1-core-item-client` plan's Task 1 has already run, which replaced `VITE_GEONODE_URL`/`VITE_BUILDER_URL` with `VITE_CORE_URL` in this same file — if it hasn't, do that rename first, then apply this step on top.)

Change:
```dockerfile
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/gis-platform
ARG VITE_OIDC_CLIENT_ID=shell
```
to:
```dockerfile
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/geostudio
ARG VITE_OIDC_CLIENT_ID=geostudio-shell
```
(`VITE_OIDC_REDIRECT_URI=http://localhost:8300/` stays as-is — already correct, matches the compose stack's exposed shell port.)

- [ ] **Step 2: Run the shell's existing test suite to confirm nothing hardcodes the old defaults**

Run: `cd shell && npm test`
Expected: PASS (these are Docker build-arg defaults, not read by any Vitest test directly — this step is a defensive check that no test file hardcodes `gis-platform`/`client_id: "shell"` as an expected value; if one does, e.g. an `AuthProvider.test.tsx` asserting a literal client id, update that expectation to `geostudio-shell` to match).

- [ ] **Step 3: Add the manual verification section to `README.md`**

After the existing "Démarrage rapide (dev)" section's service table, add:

```markdown
### Vérifier le mode `oidc` réel (manuel)

Le mode `mock` (`VITE_AUTH_MODE=mock`, `CORE_AUTH_MODE=mock`) suffit pour le
développement courant et pour les 13 specs E2E — aucun accès réseau à
Keycloak n'est nécessaire. Le mode `oidc` réel (utilisé en usage réel, pas en
CI) se vérifie manuellement :

1. `docker compose up -d` (stack complète, y compris `keycloak` avec le realm
   `geostudio` importé automatiquement — voir `docker compose ps keycloak`
   pour confirmer `healthy`).
2. Construire et lancer le shell avec `CORE_AUTH_MODE=oidc` côté cœur et sans
   `VITE_AUTH_MODE=mock` côté shell (retirer la variable ou la mettre à
   `oidc`).
3. Ouvrir http://localhost:8300 — être redirigé vers Keycloak
   (`http://localhost:8180/realms/geostudio/...`), se connecter avec un des
   utilisateurs de démo du realm importé.
4. Après redirection retour vers le shell : le catalogue doit se charger
   normalement (preuve que le token JWT émis par Keycloak est accepté par le
   cœur — `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` validés côté
   `app/auth/dependency.py`).
5. Ouvrir les DevTools réseau, vérifier qu'un appel `GET /me` retourne un
   `username` cohérent avec l'utilisateur Keycloak connecté (pas `mockuser`).

Un échec à l'étape 3 (pas de redirection, ou erreur `invalid_redirect_uri`)
indique un realm mal configuré (`Valid redirect URIs` du client
`geostudio-shell` doit inclure exactement `http://localhost:8300/`). Un échec
à l'étape 4 (401 du cœur après connexion réussie) indique un décalage entre
l'`audience`/`issuer` attendus par le cœur (`CORE_OIDC_AUDIENCE`,
`CORE_OIDC_ISSUER`) et ce que le realm émet réellement.
```

- [ ] **Step 4: Commit**

```bash
git add shell/Dockerfile README.md
git commit -m "fix(shell): correct stale oidc realm/client defaults; document manual oidc verification"
```

# SP-1d.2 — Réalm Keycloak & mode `oidc` réel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire a Keycloak realm export into the dev `docker-compose` stack so `CORE_AUTH_MODE=oidc` (already built in SP-1a, only exercised in `mock` mode until now) and the shell's real OIDC login flow (`react-oidc-context`, already built) can run end-to-end for the first time, and document the manual verification procedure.

**Prerequisite (now satisfied):** `deploy/keycloak/geostudio-realm.json` has been authored and validated (not by Tanguy — plan revised in-session; see below) — realm `geostudio`; client `geostudio-shell` (public, PKCE `S256`, standard flow + direct-access-grants enabled for dev convenience, redirect URIs `http://localhost:8300/` and `http://localhost:8300/*`, web origins `+`); client `geostudio-core` (`bearerOnly: true`, confidential, no login flow); an `oidc-audience-mapper` on `geostudio-shell` adding `geostudio-core` to the access token's `aud` claim; demo users `alice`/`bob` (password `Demo1234!`, plaintext in the JSON — Keycloak hashes it at import time, this is a dev-only realm never exposed publicly). **Validated empirically**, not just written from memory: created via the Admin REST API against a scratch Keycloak 24.0 container, exported via `partial-export`, demo users added by hand (partial-export never includes user credentials — a real limitation of that endpoint, not an oversight), then the resulting JSON was imported COLD into a fresh Keycloak container (`--import-realm`, no shared state with the authoring instance) and round-tripped through the exact validation `core/app/auth/dependency.py` performs (`PyJWKClient` + `jwt.decode(..., audience=..., issuer=...)`, using `uv run python3` from `core/`) — confirmed `VALID` for both demo users after the cold import.

**Critical finding from that validation, folded into Task 1 below:** Keycloak's `start-dev` (no `KC_HOSTNAME` set) derives the token's `iss` claim from whichever Host header reached the token endpoint — dynamically, per request. A browser doing the Authorization Code flow reaches Keycloak via `http://localhost:8180` (the published port), so `iss` will be `http://localhost:8180/realms/geostudio` — **not** `http://keycloak:8080/realms/geostudio`, which is `docker-compose.yml`'s current `CORE_OIDC_ISSUER` default (correct for `mock` mode, where no real Keycloak round-trip happens, but wrong for a real token). Since the `core` container itself cannot resolve `localhost:8180` (that's the *host's* loopback, not reachable from inside a container) to fetch the JWKS for signature verification, this requires **decoupling** issuer validation from JWKS retrieval — which `core/app/auth/dependency.py` already supports via a separate `CORE_OIDC_JWKS_URL` env var (built in SP-1a, previously unused since only `mock` mode had ever been exercised). Task 1 sets `CORE_OIDC_ISSUER=http://localhost:8180/realms/geostudio` (matches what the browser-issued token will actually carry) and adds `CORE_OIDC_JWKS_URL=http://keycloak:8080/realms/geostudio/protocol/openid-connect/certs` (internal docker-network hostname, reachable from the `core` container) to the `core` service's environment. This is exactly the kind of Keycloak configuration surprise the SP-1d spec's own §8 Risks section predicted for this sub-phase.

**Second finding:** the `keycloak` image tag pinned in `docker-compose.yml`, `quay.io/keycloak/keycloak:24`, no longer resolves (`docker pull` returns "not found" — the bare `:24` tag has been retired upstream). `:24.0` does resolve and is what this plan's realm was authored/validated against. Task 1 repins the image tag.

**Architecture:** Keycloak already runs in `docker-compose.yml` today (`start-dev`, backed by Postgres, no realm import). This plan changes its `command` to `start-dev --import-realm` and mounts the realm file into `/opt/keycloak/data/import/`, matching Keycloak's own auto-import convention (no custom import scripting needed). The cœur's `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` defaults in `docker-compose.yml` already point at realm `geostudio`/client `geostudio-core` (set correctly back in SP-1a) — only the **shell's** `Dockerfile` build-arg defaults are stale (`VITE_OIDC_AUTHORITY` still defaults to a `gis-platform` realm name, `VITE_OIDC_CLIENT_ID` still defaults to bare `shell`) and need fixing to match. No application code changes — `AuthProvider.tsx`/`useAuth.ts` (real `react-oidc-context` wiring) and the cœur's `app/auth/dependency.py` (JWKS validation) were both already built in SP-1a and need no changes, only a real realm to talk to.

**Tech Stack:** Keycloak 24 (`quay.io/keycloak/keycloak:24.0` — the bare `:24` tag this repo previously pinned no longer resolves upstream, repinned by Task 1), Docker Compose. No new dependency.

## Global Constraints

- The realm's security content (client secrets, user passwords, redirect URI list) was authored and empirically validated as part of this plan (see the revised Prerequisite section above) — it is not an external, user-provided artifact. This plan's tasks wire that already-validated realm file into the compose stack and fix the infra bugs that surfaced while proving the wiring works end-to-end.
- Realm name `geostudio`, clients `geostudio-shell` (public/PKCE) and `geostudio-core` (bearer-only, audience-validated) — these exact names are already load-bearing in already-merged code (`docker-compose.yml`'s `CORE_OIDC_ISSUER`/`CORE_OIDC_AUDIENCE` defaults, `core/app/auth/dependency.py`'s JWKS/issuer/audience validation from SP-1a) — the realm file must match them, not the other way around.
- Import failure must be loud: if `--import-realm` fails (invalid JSON, conflicting realm), Keycloak must not silently start in a broken state — add a healthcheck so `docker compose ps`/`depends_on: condition: service_healthy` surfaces it (per the SP-1d spec's §5 error-handling requirement).
- The manual `oidc` end-to-end verification (login → token → `GET /me`) is **not** automated in this plan — it's a documented README checklist, per the SP-1d spec's own testing strategy (§6: "un test manuel (pas e2e automatisé)"). The 13 Playwright e2e specs stay on `VITE_AUTH_MODE=mock` (untouched by this plan — see the separate `sp1d1-core-item-client` plan's Task 4 for their mock rewiring).
- No change to `app/auth/dependency.py`, `AuthProvider.tsx`, or `useAuth.ts` — this plan is pure infrastructure wiring, not auth code.

---

### Task 1: Wire the realm into `docker-compose.yml`; fix the issuer/JWKS split and the image tag

**Files:**
- Read (already authored and validated — see above): `deploy/keycloak/geostudio-realm.json`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: `deploy/keycloak/geostudio-realm.json` (realm `geostudio`, clients `geostudio-shell`/`geostudio-core`, demo users `alice`/`bob`).
- Produces: `keycloak` service auto-imports this realm on every start; a healthcheck reports import/startup failure; `core` service's `CORE_OIDC_ISSUER`/`CORE_OIDC_JWKS_URL` correctly split so real (not `mock`-mode) tokens validate.

- [ ] **Step 1: Sanity-check the realm file's shape (already validated end-to-end, this is just a fast local re-check)**

Run:
```bash
python3 -c "
import json
data = json.load(open('deploy/keycloak/geostudio-realm.json'))
assert data.get('realm') == 'geostudio'
client_ids = {c.get('clientId') for c in data.get('clients', [])}
assert 'geostudio-shell' in client_ids and 'geostudio-core' in client_ids
user_names = {u.get('username') for u in data.get('users', [])}
print('shape OK:', client_ids, user_names)
"
```
Expected: `shape OK: {...'geostudio-shell', 'geostudio-core'...} {'alice', 'bob'}`.

- [ ] **Step 2: Fix the pinned Keycloak image tag**

`quay.io/keycloak/keycloak:24` no longer resolves (confirmed via `docker pull` during this plan's realm-authoring work — the bare `:24` tag was retired upstream). Change:
```yaml
    image: quay.io/keycloak/keycloak:24
```
to:
```yaml
    image: quay.io/keycloak/keycloak:24.0
```

- [ ] **Step 3: Mount the realm file, switch to `--import-realm`, add a healthcheck**

In `docker-compose.yml`, change the `keycloak` service:
```yaml
  keycloak:
    image: quay.io/keycloak/keycloak:24.0
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
(`KC_HEALTH_ENABLED: "true"` turns on Keycloak's built-in `/health/ready` endpoint. The healthcheck uses a raw `/dev/tcp` HTTP request since the Keycloak image bundles neither `curl` nor `wget` — verify in Step 5 whether this works in the `24.0` image's shell; if not, adjust until it correctly reports healthy only after a successful realm import and ready server, never unconditionally.)

- [ ] **Step 4: Fix the `core` service's issuer/JWKS split**

In `docker-compose.yml`'s `core` service `environment:` block, change:
```yaml
      CORE_OIDC_ISSUER: ${CORE_OIDC_ISSUER:-http://keycloak:8080/realms/geostudio}
      CORE_OIDC_AUDIENCE: ${CORE_OIDC_AUDIENCE:-geostudio-core}
```
to:
```yaml
      CORE_OIDC_ISSUER: ${CORE_OIDC_ISSUER:-http://localhost:8180/realms/geostudio}
      CORE_OIDC_AUDIENCE: ${CORE_OIDC_AUDIENCE:-geostudio-core}
      CORE_OIDC_JWKS_URL: ${CORE_OIDC_JWKS_URL:-http://keycloak:8080/realms/geostudio/protocol/openid-connect/certs}
```
This is the fix documented above: Keycloak's `start-dev` derives a real browser-issued token's `iss` from the Host header the browser actually used (`localhost:8180`, the published port) — the `core` container validates `issuer` against that same value, but fetches the JWKS from `keycloak:8080` (the internal docker-network hostname, unreachable as `localhost` from inside a different container). `app/auth/dependency.py`'s existing `CORE_OIDC_JWKS_URL` override (built in SP-1a, unused until now) is exactly the mechanism for this split — no code change needed, only this env var.

Also update `.env.example` to mention the split (add a comment, no new required var — both already have defaults):
```
CORE_OIDC_ISSUER=http://localhost:8180/realms/geostudio
CORE_OIDC_AUDIENCE=geostudio-core
# JWKS fetched from inside the core container, via the internal docker network —
# deliberately different from CORE_OIDC_ISSUER (which must match what a real
# browser's token actually carries as `iss`, i.e. the externally published port).
CORE_OIDC_JWKS_URL=http://keycloak:8080/realms/geostudio/protocol/openid-connect/certs
```

- [ ] **Step 5: Bring the stack up and verify the healthcheck actually detects success**

Run:
```bash
docker compose up -d postgis keycloak
docker compose ps keycloak
```
Expected: after `start_period` (30s) plus a few retries, `docker compose ps keycloak` shows `healthy`, not `starting` indefinitely or `unhealthy`. If the healthcheck command doesn't work in this image (check `docker compose logs keycloak` for import errors, and `docker compose exec keycloak sh -c '...'` to test interactively), adjust the `test:` command until it correctly reports healthy only after a successful realm import and ready server.

- [ ] **Step 6: Verify the realm was actually imported**

Run:
```bash
curl -s http://localhost:8180/realms/geostudio/.well-known/openid-configuration | python3 -m json.tool | head -5
```
Expected: valid OpenID configuration JSON with `"issuer": "http://localhost:8180/realms/geostudio"`. If this 404s, the import failed silently despite a "healthy" status — tighten Step 5's healthcheck to check `/realms/geostudio` reachability directly instead of just the generic `/health/ready`.

- [ ] **Step 7: End-to-end token validation against the real compose stack**

Bring up `core` too, with `CORE_AUTH_MODE=oidc` (it defaults to `mock` in `docker-compose.yml`, which would skip real JWT validation entirely and make this step pass for the wrong reason):
```bash
CORE_AUTH_MODE=oidc docker compose up -d postgis keycloak core
```
Get a token (password grant, `geostudio-shell`, demo user `alice`):
```bash
curl -s -X POST http://localhost:8180/realms/geostudio/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=geostudio-shell&username=alice&password=Demo1234!" \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" > /tmp/kc_token.txt
```
Call the cœur's `/me` directly with it (`CORE_AUTH_MODE` must be `oidc`, not `mock`, for this container — check/set it in `docker-compose.yml`'s `core.environment` or via `.env` before this step):
```bash
curl -s http://localhost:8200/me -H "Authorization: Bearer $(cat /tmp/kc_token.txt)"
```
Expected: `200` with a JSON body whose `username` is `"alice"` (not a `401` — a `401` here means the issuer/audience/JWKS wiring from Steps 3-4 is still wrong; re-check `docker compose logs core` for the specific PyJWT rejection reason).

- [ ] **Step 8: Tear down**

Run: `docker compose down`

- [ ] **Step 9: Commit**

```bash
git add docker-compose.yml .env.example deploy/keycloak/geostudio-realm.json
git commit -m "feat: import the geostudio Keycloak realm on startup; fix issuer/JWKS split and image tag"
```

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

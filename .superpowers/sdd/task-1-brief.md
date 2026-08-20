## Task 1: Keycloak realm — MCP-audience scope on `geostudio-shell`

**Why this shape, not the design doc's original client-signinSilent-with-`resource`-param or a core-side token-exchange:** `deploy/keycloak/geostudio-realm.json` already defines a `geostudio-mcp-audience` client scope (custom-audience mapper, `consentRequired: false`) — provisioned in SP-2 for exactly this case, just never attached to `geostudio-shell`. Requesting it via the standard OIDC `scope` parameter on a second `signinSilent()` call is the established, version-independent mechanism (unlike RFC 8693 token-exchange, only available as a preview feature requiring fine-grained authorization config on Keycloak 24, the version pinned in `docker-compose.yml`).

**Files:**
- Modify: `deploy/keycloak/geostudio-realm.json` (the `geostudio-shell` client's `optionalClientScopes`)

- [ ] **Step 1: Add the scope**

In `deploy/keycloak/geostudio-realm.json`, find the `geostudio-shell` client object (`"clientId": "geostudio-shell"`) and change:

```json
      "optionalClientScopes": [
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt"
      ]
```

to:

```json
      "optionalClientScopes": [
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt",
        "geostudio-mcp-audience"
      ]
```

- [ ] **Step 2: Verify against a real Keycloak (docker compose)**

Run:

```bash
docker compose up -d keycloak
# Wait for it to report healthy:
docker compose ps keycloak
```

Once healthy (`docker compose ps keycloak` shows `healthy`), request a token via the Direct Access Grant (ROPC) flow — `geostudio-shell` is a public client with `directAccessGrantsEnabled: true`, and `alice`/`Demo1234!` is a seeded dev-only user in this same realm file (already public in this open-source repo, not a real credential):

```bash
curl -s -X POST http://localhost:8180/realms/geostudio/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=geostudio-shell \
  -d username=alice \
  -d password=Demo1234! \
  -d scope="openid geostudio-mcp-audience" \
  | python3 -c "
import json, sys, base64
tok = json.load(sys.stdin)['access_token']
payload = tok.split('.')[1]
payload += '=' * (-len(payload) % 4)
claims = json.loads(base64.urlsafe_b64decode(payload))
print('aud:', claims['aud'])
assert 'geostudio-mcp' in claims['aud'], 'geostudio-mcp missing from aud!'
print('OK: geostudio-mcp present in aud')
"
```

Expected output: `aud: ['geostudio-core', 'geostudio-mcp']` (or similar, in some order) then `OK: geostudio-mcp present in aud`. If the realm didn't reload your edit (Keycloak only re-imports on a fresh volume), remove the `keycloak-data` volume first: `docker compose down keycloak && docker volume rm geostudio_keycloak-data && docker compose up -d keycloak` (check the exact volume name via `docker compose config --volumes` first — do not guess).

If this fails (audience missing), stop and re-investigate — do not proceed to Task 11 (`useMcpToken.ts`) on an unverified assumption.

- [ ] **Step 3: Commit**

```bash
git add deploy/keycloak/geostudio-realm.json
git commit -m "$(cat <<'EOF'
feat(deploy): geostudio-shell peut demander le scope d'audience MCP (SP-20)

Ajoute geostudio-mcp-audience aux optionalClientScopes de geostudio-shell —
scope déjà provisionné en SP-2, jusqu'ici jamais attaché à ce client.
Permet au shell d'obtenir un second token (audience geostudio-mcp) via
signinSilent({scope: "... geostudio-mcp-audience"}) sans passer par le
grant token-exchange (preview feature sur Keycloak 24).
EOF
)"
```

---


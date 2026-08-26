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


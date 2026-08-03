### Task 5: E2E coverage

**Files:**
- Create: `shell/e2e/sql-lab.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`, already exists) ; the running app's `/analytics/sql` route and "SQL Lab" nav link (Task 4) ; the `SqlLabPage` UI surface — `aria-label="Requête SQL"` textarea, `"Exécuter"` button, results `<table>`, `role="alert"` error message, history button labelled `"Recharger la requête : <sql>"` (Task 3).
- Produces: nothing consumed by later tasks — this is the last task.

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/sql-lab.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un analyste exécute une requête SQL, voit le résultat, et recharge une requête depuis l'historique", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: false, isAnalyst: true,
      },
    });
  });

  let posted: unknown;
  // Host-scoped (not "**/analytics/sql"): the shell's own client-side route
  // to this very page is "/analytics/sql" — a path-only glob would also
  // intercept the browser's document navigation and break rendering (same
  // rationale as "/admin/extensions" and "/admin/collections" elsewhere in
  // this suite, see admin-extensions.spec.ts).
  await page.route("https://core.test/analytics/sql", async (route) => {
    posted = await route.request().postDataJSON();
    await route.fulfill({
      json: { columns: ["nom", "surface"], rows: [["Parc A", 12]], truncated: false },
    });
  });

  await page.goto("/analytics/sql");
  await expect(page.getByRole("link", { name: "SQL Lab" })).toBeVisible();
  await page.getByLabel("Requête SQL").fill("select nom, surface from parcs");
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByRole("columnheader", { name: "nom" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Parc A" })).toBeVisible();
  await expect.poll(() => posted).toEqual({ sql: "select nom, surface from parcs" });

  await page.getByLabel("Requête SQL").fill("");
  await page.getByRole("button", { name: "Recharger la requête : select nom, surface from parcs" }).click();
  await expect(page.getByLabel("Requête SQL")).toHaveValue("select nom, surface from parcs");
});

test("une erreur SQL affiche le message du serveur et conserve le texte dans l'éditeur", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: false, isAnalyst: true,
      },
    });
  });
  await page.route("https://core.test/analytics/sql", async (route) => {
    await route.fulfill({
      status: 400,
      json: { detail: { errors: [{ field: "sql", code: "sql_error", message: "Parser Error: syntax error" }] } },
    });
  });

  await page.goto("/analytics/sql");
  await page.getByLabel("Requête SQL").fill("select * fro parcs");
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByRole("alert")).toHaveText("Parser Error: syntax error");
  await expect(page.getByLabel("Requête SQL")).toHaveValue("select * fro parcs");
});

test("un utilisateur non-analyste ne voit pas le lien SQL Lab et reçoit un message d'accès refusé", async ({ page }) => {
  await mockCore(page);
  let sqlCalled = false;
  await page.route("https://core.test/analytics/sql", async (route) => {
    sqlCalled = true;
    await route.fulfill({ json: { columns: [], rows: [], truncated: false } });
  });

  await page.goto("/analytics/sql");
  await expect(page.getByRole("alert")).toHaveText("Accès réservé aux analystes.");
  expect(await page.getByRole("link", { name: "SQL Lab" }).count()).toBe(0);
  expect(sqlCalled).toBe(false);
});
```

(The third test relies on `mockCore`'s default `/me` route in `shell/e2e/mocks.ts`, which sets `isAdmin: false` and omits `isAnalyst` entirely — `meQuery.data?.isAnalyst !== true` is then `true`, matching the existing non-admin pattern in `admin-extensions.spec.ts`. No override needed, same as that spec's non-admin test.)

- [ ] **Step 2: Run the new spec**

Run: `cd shell && npm run e2e -- e2e/sql-lab.spec.ts`
Expected: PASS, 3/3 tests green. (Requires `VITE_AUTH_MODE=mock`, per this repo's standard `npm run e2e` setup — no extra env needed if `npm run e2e` already configures it, per `package.json`.)

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS, all 79 specs green (76 pre-existing + 3 new).

- [ ] **Step 4: Commit**

```bash
cd shell && git add e2e/sql-lab.spec.ts
git commit -m "test(e2e): couvre SQL Lab — exécution, erreur, historique, garde analyste (SP-14i)"
```

---

## Final check

- [ ] Run `cd shell && npm test && npx tsc --noEmit && npm run e2e` once more from a clean state to confirm the whole suite (unit + E2E) is green end to end.

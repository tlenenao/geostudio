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

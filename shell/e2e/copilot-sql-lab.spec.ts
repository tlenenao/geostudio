// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ANALYST_ME } from "./mocks";

test("copilot on SQL Lab: generated SQL is inserted as a draft, never auto-executed", async ({
  page,
}) => {
  await mockCore(page);
  // Le brief du plan omettait ce mock : /analytics/sql est gardée par le
  // privilège analytics.sql_lab.access (cf. shell/src/shell/routes.tsx), que
  // le rôle Créateur par défaut de mockCore() ne porte pas — sans ce mock la
  // page rend "Accès réservé aux analystes." et le panneau copilote (donc
  // "Message au copilote") n'apparaît jamais. Même patron que
  // e2e/sql-lab.spec.ts.
  await mockMe(page, ANALYST_ME);
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  let executed = false;
  await page.route("https://core.test/v1/analytics/sql", async (route) => {
    executed = true;
    await route.fulfill({
      json: { columns: ["titre"], rows: [["Nid de poule"]], truncated: false },
    });
  });
  await page.route("https://core.test/v1/copilot/turn", async (route) => {
    await route.fulfill({
      json: {
        reply: "Voici un brouillon.",
        clientOps: [{ op: "applySqlDraft", args: { sql: "SELECT titre FROM incidents" } }],
      },
    });
  });

  await page.goto("/analytics/sql");

  await page.getByLabel("Message au copilote").fill("les titres des incidents");
  await page.getByRole("button", { name: "Envoyer" }).click();

  await expect(page.getByLabel("Requête SQL")).toHaveValue("SELECT titre FROM incidents");
  // Point d'arrêt humain : rien n'a exécuté la requête tant que l'utilisateur
  // n'a pas cliqué sur Exécuter.
  expect(executed).toBe(false);

  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByText("Nid de poule")).toBeVisible();
  expect(executed).toBe(true);
});

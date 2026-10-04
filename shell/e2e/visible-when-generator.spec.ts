// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("REV-183 : générer une condition d'affichage, l'appliquer seulement sur clic", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  let turnBody: Record<string, unknown> = {};
  await page.route("https://core.test/v1/copilot/turn", async (route) => {
    turnBody = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({
      json: {
        reply: "Voici une condition.",
        clientOps: [{ op: "applyCelDraft", args: { expression: 'user.name == "alice"' } }],
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte", exact: true }).click();
  const condition = page.getByLabel("Condition d'affichage (visibleWhen)");
  await expect(condition).toHaveValue("");

  await page.getByText("Générer", { exact: true }).click();
  await page.getByLabel("Décrire la condition").fill("visible pour alice");
  await page.getByRole("button", { name: "Proposer" }).click();
  await expect(page.getByText('user.name == "alice"')).toBeVisible();
  // Jamais appliqué sans clic humain.
  await expect(condition).toHaveValue("");

  await page.getByRole("button", { name: "Appliquer" }).click();
  await expect(condition).toHaveValue('user.name == "alice"');

  expect(turnBody.surface).toBe("visible_when");
  expect((turnBody.clientTools as { name: string }[])[0].name).toBe("applyCelDraft");
  expect((turnBody.currentConfig as { availableFields: string[] }).availableFields).toContain(
    "user.name",
  );
});

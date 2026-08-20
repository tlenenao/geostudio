// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("copilot panel is absent without copilotEnabled", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await expect(page.getByLabel("Message au copilote")).toHaveCount(0);
});

test("copilot: explain prompt makes no changes, add-widget prompt adds and is undoable", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, copilotEnabled: true } });
  });
  await page.route("https://core.test/copilot/turn", async (route) => {
    const body = route.request().postDataJSON() as { message: string };
    if (body.message.includes("indicateur")) {
      await route.fulfill({
        json: {
          reply: "J'ai ajouté un indicateur.",
          clientOps: [{ op: "addWidget", args: { type: "indicator" } }],
        },
      });
    } else {
      await route.fulfill({ json: { reply: "Ce dataset contient des incidents.", clientOps: [] } });
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Explique — pas de changement de canevas.
  await page.getByLabel("Message au copilote").fill("Explique ce dataset");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("Ce dataset contient des incidents.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);

  // Ajoute un widget — apparaît sur le canevas, annulable via le bouton
  // Annuler de la barre d'outils (pas de bouton dédié dans le panneau).
  await page.getByLabel("Message au copilote").fill("Ajoute un indicateur");
  await page.getByRole("button", { name: "Envoyer" }).click();
  await expect(page.getByText("J'ai ajouté un indicateur.")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();

  await page.getByRole("button", { name: "Annuler" }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);
});

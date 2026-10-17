// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { bindTemplateSources, mockCore } from "./mocks";

// ARC-15 : onglet Historique du widget Formulaire (patron incident-form.spec.ts).
test("consulter l'historique d'une entité et restaurer une version", async ({ page }) => {
  await mockCore(page);
  let restored = false;
  await page.route("**/collections/incidents/items/1/history", async (route) => {
    await route.fulfill({
      json: {
        versions: [
          {
            id: 2,
            fid: "1",
            op: "update",
            at: "2026-10-12T10:00:00Z",
            actor: { id: "u1", username: "alice" },
            before: { properties: { titre: "Fuite d'eau" }, geometry: null },
            after: { properties: { titre: "Fuite d'eau (résolue)" }, geometry: null },
          },
          {
            id: 1,
            fid: "1",
            op: "create",
            at: "2026-10-12T09:00:00Z",
            actor: null,
            before: null,
            after: { properties: { titre: "Fuite d'eau" }, geometry: null },
          },
        ],
      },
    });
  });
  await page.route("**/collections/incidents/items/1/history/1/restore", async (route) => {
    restored = true;
    await route.fulfill({ status: 204, body: "" });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await bindTemplateSources(dialog);
  await dialog.getByLabel("Titre").fill("Historique");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Sélectionner Formulaire" }).click();
  await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
  await expect(page.getByLabel("Label du champ titre")).toBeVisible();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("titre").fill("Fuite d'eau");
  await page.getByLabel("gravite").selectOption("haute");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();
  await page.getByText("Fuite d'eau").click();
  await expect(page.getByText(/Modification de l'enregistrement #1/)).toBeVisible();

  const toggle = page.getByRole("button", { name: "Historique" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  await expect(page.getByText(/Modification.*alice/)).toBeVisible();
  await expect(page.getByText(/auteur effacé/)).toBeVisible();
  await page.getByRole("button", { name: "Restaurer cette version" }).last().click();
  await expect.poll(() => restored).toBe(true);
});

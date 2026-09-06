import { test, expect } from "@playwright/test";
import { mockCore, mockMe } from "./mocks";

// SP-58 Tâche 5 (GAP-73/GAP-11) : un tenant qui dépasse son quota
// d'items voit sa création refusée avec un message clair (preuve de
// sortie du chantier 4.22) — le cœur répond 409 (RFC 7807), le shell
// affiche déjà une alerte visible (role="alert") sur tout échec de
// création (NewItemButton.tsx), indépendamment de la cause précise.
test("la création d'un item refusée pour quota dépassé affiche une erreur visible", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page);

  await page.route("**/configs", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 409,
        contentType: "application/problem+json",
        json: {
          type: "about:blank",
          title: "Conflict",
          status: 409,
          detail: "quota d'items du tenant dépassé : 1/1",
        },
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte en trop");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page.getByRole("alert")).toContainText("Échec de la création.");
});

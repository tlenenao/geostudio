import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un item en lecture seule ne propose ni suppression ni partage", async ({ page }) => {
  await mockCore(page);
  // Un seul item, en lecture seule : on surcharge la route APRÈS mockCore,
  // la dernière route enregistrée l'emporte chez Playwright.
  await page.route("**/items*", async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            pk: "77",
            resourceType: "map",
            title: "Partagée en lecture",
            abstract: "",
            owner: "tanguy",
            thumbnailUrl: null,
            date: "2026-08-29T00:00:00Z",
            configId: null,
            isPublished: false,
            keywords: [],
            permissions: { read: true, write: false, delete: false, share: false },
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      },
    });
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Partagée en lecture" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).click();

  await expect(page.getByRole("button", { name: /^supprimer$/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^partager$/i })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Modifier" })).toBeDisabled();
  // Publier et Miniature sont aussi verrouillées par `write` pour ce même item
  // et affichent la même raison (`locked.needWrite`) : plusieurs occurrences
  // du texte sont donc attendues, `.first()` remplace l'appel nu du brief
  // (piège n°3 — texte littéral faux face au rendu réel, même correction
  // qu'en unitaire dans ItemActions.test.tsx).
  await expect(
    page.getByText("Modification réservée aux éditeurs de cet élément.").first(),
  ).toBeVisible();
});

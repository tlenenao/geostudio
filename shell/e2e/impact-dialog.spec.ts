import { test, expect } from "@playwright/test";
import { mockCore, mockMe, mockCollection, ADMIN_ME } from "./mocks";

// ARC4-F15 (vague 4) : supprimer une collection utilisée par 2 cartes et 1 pipeline
// affiche les 3 dépendants visibles, et compte sans le nommer un dépendant non lisible.
test("le dialogue de suppression d'une collection liste ses dépendants avant confirmation", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  let deleted = false;

  // Host-scoped (cf. admin-collections.spec.ts) : un glob par chemin seul
  // intercepterait aussi la navigation du document vers /admin/collections.
  await page.route("https://core.test/v1/collections*", async (route) => {
    await route.fulfill({ json: { collections: deleted ? [] : [mockCollection()] } });
  });
  await page.route("https://core.test/v1/collections/points_interet**", async (route) => {
    const url = route.request().url();
    if (route.request().method() === "DELETE") {
      deleted = true;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (url.endsWith("/impact")) {
      await route.fulfill({
        json: {
          target: {
            type: "collection",
            id: "points_interet",
            title: "Points d'intérêt",
            resourceType: "collection",
          },
          dependents: [
            {
              type: "item",
              id: "m1",
              title: "Carte des écoles",
              resourceType: "map",
              depth: 1,
              direct: true,
            },
            {
              type: "item",
              id: "m2",
              title: "Carte des parcs",
              resourceType: "map",
              depth: 1,
              direct: true,
            },
            {
              type: "item",
              id: "p1",
              title: "Import nocturne",
              resourceType: "pipeline",
              depth: 1,
              direct: true,
            },
          ],
          hiddenCount: 1,
        },
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/admin/collections");
  await page.getByRole("button", { name: "Supprimer" }).click();
  const dialog = page.getByRole("alertdialog");
  await expect(
    dialog.getByText("3 objets dépendent de celui-ci et seront affectés :"),
  ).toBeVisible();
  for (const title of ["Carte des écoles", "Carte des parcs", "Import nocturne"]) {
    await expect(dialog.getByText(title)).toBeVisible();
  }
  await expect(
    dialog.getByText("+ 1 autre objet que vous n'avez pas le droit de voir."),
  ).toBeVisible();
  expect(deleted).toBe(false);

  await dialog.getByRole("button", { name: "Supprimer" }).click();
  await expect.poll(() => deleted).toBe(true);
});

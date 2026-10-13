// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, mockCollection, ADMIN_ME } from "./mocks";

// ARC-10 : file de modération des soumissions publiques d'une collection.
test("un modérateur approuve une soumission et crée un lien de soumission", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);

  let approved = false;
  let createdBody: unknown = null;

  await page.route("https://core.test/v1/collections*", async (route) => {
    await route.fulfill({ json: { collections: [mockCollection({ title: "Signalements" })] } });
  });
  await page.route("https://core.test/v1/collections/points_interet/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.endsWith("/submissions") && method === "GET") {
      await route.fulfill({
        json: {
          submissions: approved
            ? []
            : [
                {
                  id: "s1",
                  status: "pending",
                  properties: { nom: "Nid-de-poule" },
                  geometry: null,
                  attachment: null,
                  createdAt: null,
                },
              ],
        },
      });
      return;
    }
    if (url.endsWith("/submissions/s1/approve")) {
      approved = true;
      await route.fulfill({ json: { fid: "7" } });
      return;
    }
    if (url.endsWith("/submission-tokens") && method === "POST") {
      createdBody = route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "k1",
          name: "mairie",
          prefix: "gss_abc",
          expiresAt: null,
          maxSubmissions: 100,
          submissionCount: 0,
          revokedAt: null,
          token: "gss_abc_SECRET",
        },
      });
      return;
    }
    if (url.endsWith("/submission-tokens")) {
      await route.fulfill({ json: { tokens: [] } });
      return;
    }
    await route.fallback();
  });

  await page.goto("/admin/collections");
  await page.getByRole("button", { name: "Soumissions" }).click();
  await expect(page.getByText(/Nid-de-poule/)).toBeVisible();
  await page.getByRole("button", { name: "Approuver la soumission s1" }).click();
  await expect.poll(() => approved).toBe(true);
  await expect(page.getByText("Aucune soumission en attente.")).toBeVisible();

  await page.getByLabel("Nom du lien").fill("mairie");
  await page.getByRole("button", { name: "Créer un lien" }).click();
  await expect(page.getByText("gss_abc_SECRET")).toBeVisible();
  expect(createdBody).toEqual({ name: "mairie", expiresInDays: 30, maxSubmissions: 100 });
});

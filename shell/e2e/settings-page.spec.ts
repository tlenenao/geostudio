// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME, READER_ME } from "./mocks";

test("un profil sans privilège admin ne voit que Général dans la navigation Paramètres", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  await page.route("https://core.test/v1/notifications/preference", (route) =>
    route.fulfill({ json: { value: "all" } }),
  );
  await page.goto("/settings");
  await expect(page.getByRole("link", { name: "Général →" })).toBeVisible();
  for (const name of [
    "Extensions →",
    "Outils d'infrastructure →",
    "Rôles et privilèges →",
    "Utilisateurs →",
    "Collections →",
    "Moissonnage →",
    "Conformité (RGPD) →",
  ]) {
    await expect(page.getByRole("link", { name })).not.toBeVisible();
  }
});

test("un admin navigue de Paramètres vers Extensions sans repasser par la barre de domaines", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  await page.route("https://core.test/v1/notifications/preference", (route) =>
    route.fulfill({ json: { value: "all" } }),
  );
  await page.route("https://core.test/v1/extensions**", (route) =>
    route.fulfill({ json: { extensions: [] } }),
  );
  await page.goto("/settings");
  await page.getByRole("link", { name: "Extensions →" }).click();
  await expect(page).toHaveURL(/\/admin\/extensions$/);
  await expect(page.getByRole("heading", { name: "Extensions" })).toBeVisible();
});

test("changer la préférence de notifications persiste après rechargement", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  let preference = "all";
  await page.route("https://core.test/v1/notifications/preference", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as { value: string };
      preference = body.value;
      await route.fulfill({ json: { value: preference } });
      return;
    }
    await route.fulfill({ json: { value: preference } });
  });
  await page.goto("/settings");
  await page.getByRole("radio", { name: "Échecs seulement" }).click();
  await expect(page.getByRole("radio", { name: "Échecs seulement" })).toBeChecked();
  await page.reload();
  await expect(page.getByRole("radio", { name: "Échecs seulement" })).toBeChecked();
});

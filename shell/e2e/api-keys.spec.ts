// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, READER_ME } from "./mocks";

test("Paramètres : créer une clé d'API affiche le secret une fois, puis la révoquer", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  await page.route("https://core.test/v1/notifications/preference", (route) =>
    route.fulfill({ json: { value: "all" } }),
  );
  const base = {
    id: "k1",
    name: "CI",
    prefix: "gsk_0123456789ab",
    createdAt: "2026-10-11T08:00:00Z",
    expiresAt: "2027-01-01T00:00:00Z",
    revokedAt: null as string | null,
    lastUsedAt: null,
  };
  let keys: (typeof base)[] = [];
  await page.route("https://core.test/v1/api-keys", async (route) => {
    if (route.request().method() === "POST") {
      keys = [base];
      await route.fulfill({ status: 201, json: { ...base, token: "gsk_0123456789ab_SECRET" } });
      return;
    }
    await route.fulfill({ json: keys });
  });
  await page.route("https://core.test/v1/api-keys/k1", async (route) => {
    keys = [{ ...base, revokedAt: "2026-10-11T09:00:00Z" }];
    await route.fulfill({ json: keys[0] });
  });

  await page.goto("/settings");
  await page.getByLabel("Nom de la clé").fill("CI");
  await page.getByRole("button", { name: "Créer la clé" }).click();
  await expect(page.getByText("gsk_0123456789ab_SECRET")).toBeVisible();
  await page.getByRole("button", { name: "J'ai copié la clé" }).click();
  await expect(page.getByText("gsk_0123456789ab_SECRET")).not.toBeVisible();

  await page.reload();
  await expect(page.getByText("gsk_0123456789ab…")).toBeVisible();
  await expect(page.getByText("gsk_0123456789ab_SECRET")).not.toBeVisible();

  await page.getByRole("button", { name: "Révoquer" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Révoquer" }).click();
  await expect(page.getByText("Révoquée")).toBeVisible();
});

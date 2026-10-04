// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("REV-102 : rechercher une adresse centre la carte et la vue est enregistrée", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/geocode*", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q");
    expect(q).toBe("1 rue de pontoise cergy");
    await route.fulfill({
      json: { results: [{ label: "1 Rue de Pontoise 95000 Cergy", lon: 2.0628, lat: 49.0316 }] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  await page.getByLabel("Rechercher une adresse").fill("1 rue de pontoise cergy");
  await page.getByRole("button", { name: "Localiser" }).click();
  await page.getByRole("button", { name: "1 Rue de Pontoise 95000 Cergy" }).click();

  const saved = page.waitForRequest(
    (r) => r.method() === "PUT" && r.url().includes("/configs/by-item/77"),
  );
  await page.getByRole("button", { name: "Enregistrer" }).click();
  const body = (await saved).postDataJSON() as {
    map: { view: { center: number[]; zoom: number } };
  };
  expect(body.map.view.center[0]).toBeCloseTo(2.0628, 3);
  expect(body.map.view.center[1]).toBeCloseTo(49.0316, 3);
});

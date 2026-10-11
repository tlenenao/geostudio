// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const EVENTS = {
  type: "FeatureCollection",
  features: [
    { day: "2026-06-01", n: 1 },
    { day: "2026-06-10", n: 2 },
  ].map(({ day, n }) => ({
    type: "Feature",
    properties: { n, date: day },
    geometry: { type: "Point", coordinates: [2.3 + n * 0.01, 46.6] },
  })),
};

// ARC-09b : le lecteur temps pilote le filtre `datetime` (ARC-02) des couches à
// `timeField`, et son état est accepté à l'enregistrement puis relu (piège n°5).
test("map time player drives datetime and round-trips through save and reload", async ({
  page,
}) => {
  await mockCore(page);
  const datetimeUrls: string[] = [];
  await page.route(/https:\/\/external\.test\/events\.geojson.*/, (route) => {
    datetimeUrls.push(route.request().url());
    return route.fulfill({
      status: 200,
      contentType: "application/geo+json",
      body: JSON.stringify(EVENTS),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte temps");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Titre de la couche GeoJSON").fill("Événements");
  await page.getByLabel("URL du GeoJSON").fill("https://external.test/events.geojson");
  await page.getByRole("button", { name: "Ajouter la couche" }).click();
  await page.getByLabel("Champ temporel").selectOption("date");

  await page.getByLabel("Début de l'animation").fill("2026-06-01");
  await page.getByLabel("Fin de l'animation").fill("2026-06-30");
  await expect(page.getByText("Période : 2026-06-01 → 2026-06-07")).toBeVisible();
  await expect
    .poll(() => datetimeUrls.some((u) => u.includes("datetime=2026-06-01%2F2026-06-07")))
    .toBe(true);
  expect(datetimeUrls.some((u) => u.includes("datetime_field=date"))).toBe(true);

  const put = page.waitForRequest((r) => r.method() === "PUT" && r.url().includes("/configs/"));
  await page.getByRole("button", { name: "Enregistrer" }).click();
  const body = (await put).postDataJSON();
  expect(body.map.timePlayer).toMatchObject({ start: "2026-06-01", end: "2026-06-30" });
  expect(JSON.stringify(body)).toContain('"timeField":"date"');
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Période : 2026-06-01 → 2026-06-07")).toBeVisible();
});

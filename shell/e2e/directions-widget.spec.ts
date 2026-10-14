// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// ARC-34 : widget « Directions » — deux points → POST /v1/routing/route ; service absent = 503 lisible.
async function addDirectionsApp(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill("Mon app itinéraire");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Itinéraire", exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.goto("/apps/9");
  await page.getByLabel("Départ").fill("45.26, 1.77");
  await page.getByLabel("Arrivée").fill("45.16, 1.53");
}

test("ARC-34 : un widget Directions calcule un itinéraire et affiche distance, durée et consignes", async ({
  page,
}) => {
  await mockCore(page);
  let posted: unknown = null;
  await page.route("https://core.test/v1/routing/route", async (route) => {
    posted = route.request().postDataJSON();
    await route.fulfill({
      json: {
        distance_km: 25.4,
        duration_s: 1800,
        geometry: { type: "LineString", coordinates: [[1.77, 45.26]] },
        legs: [
          {
            distance_km: 25.4,
            duration_s: 1800,
            maneuvers: [{ instruction: "Tournez à gauche.", distance_km: 1, duration_s: 60 }],
          },
        ],
      },
    });
  });
  await addDirectionsApp(page);
  await page.getByLabel("Mode de déplacement").selectOption("bicycle");
  await page.getByRole("button", { name: "Calculer l'itinéraire" }).click();
  await expect(page.getByText("25,4 km, 30 min.")).toBeVisible();
  await expect(page.getByText("Tournez à gauche.")).toBeVisible();
  expect(posted).toEqual({
    points: [
      { lon: 1.77, lat: 45.26 },
      { lon: 1.53, lat: 45.16 },
    ],
    costing: "bicycle",
  });
});

test("ARC-34 : service de routage absent, le message 503 du cœur est affiché", async ({ page }) => {
  await mockCore(page);
  await page.route("https://core.test/v1/routing/route", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/problem+json",
      json: {
        type: "about:blank",
        title: "Service Unavailable",
        status: 503,
        detail: "Routage désactivé sur cette instance (CORE_ROUTING_URL vide).",
      },
    }),
  );
  await addDirectionsApp(page);
  await page.getByRole("button", { name: "Calculer l'itinéraire" }).click();
  await expect(page.getByRole("alert")).toContainText("Routage désactivé sur cette instance");
});

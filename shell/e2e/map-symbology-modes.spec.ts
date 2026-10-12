// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// ARC-17 : les 4 modes avancés + les effets se posent dans l'éditeur de
// cartes, apparaissent dans la légende, et survivent à save → reload.
test("mode bivarié + effets : légende, enregistrement et rechargement", async ({ page }) => {
  await mockCore(page);
  await page.route("**/map-icons", (route) => route.fulfill({ json: [] }));
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({ status: 200, contentType: "application/vnd.mapbox-vector-tile", body: TILE }),
  );
  await page.route("**/collections/communes/schema", (route) =>
    route.fulfill({
      json: {
        collection: "communes",
        pk: "id",
        geometry: null,
        fields: [
          { name: "pop", type: "integer", required: false },
          { name: "revenu", type: "integer", required: false },
        ],
      },
    }),
  );
  await page.route("**/collections/communes/aggregate", (route) =>
    route.fulfill({ json: { rows: [{ properties: { min: 0, max: 90 } }] } }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte modes avancés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await page.getByRole("button", { name: /Communes/ }).click();

  await page.getByLabel("Mode avancé").selectOption("bivariate");
  await page.getByLabel("Champ X").selectOption("pop");
  await page.getByLabel("Champ Y").selectOption("revenu");
  await page.getByRole("button", { name: "Recalculer l'échelle" }).click();
  await expect(page.getByText(/Échelle non calculée/)).toHaveCount(0);
  await page.getByLabel("Halo (bloom)").check();
  await page.getByLabel("Ombre portée").check();

  await expect(page.getByTestId("legend-advanced")).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);
  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await expect(page.getByLabel("Mode avancé")).toHaveValue("bivariate");
  await expect(page.getByLabel("Champ X")).toHaveValue("pop");
  await expect(page.getByLabel("Champ Y")).toHaveValue("revenu");
  await expect(page.getByLabel("Halo (bloom)")).toBeChecked();
  await expect(page.getByLabel("Ombre portée")).toBeChecked();
  await expect(page.getByTestId("legend-advanced")).toBeVisible();
});

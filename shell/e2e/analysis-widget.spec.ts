// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// ARC-25 : widget « Analyse » — outil + collection + paramètre → POST /collections/{id}/analysis.
test("ARC-25 : un widget Analyse exécute un tampon sur une collection et affiche le résultat", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/analysis/tools", (route) =>
    route.fulfill({
      json: {
        tools: [
          {
            name: "buffer",
            label: "Tampon",
            help: "Zone tampon autour des entités.",
            needsOtherCollection: false,
            paramsSchema: {
              properties: { distance: { type: "number", title: "Distance" } },
              required: ["distance"],
            },
          },
        ],
      },
    }),
  );
  await page.route("https://core.test/v1/collections?*", (route) =>
    route.fulfill({ json: { collections: [{ id: "c1", title: "Villes" }] } }),
  );
  let posted: unknown = null;
  await page.route("https://core.test/v1/collections/c1/analysis", async (route) => {
    posted = route.request().postDataJSON();
    await route.fulfill({
      json: {
        tool: "buffer",
        output: "ephemeral",
        srid: 4326,
        truncated: false,
        featureCollection: { type: "FeatureCollection", features: [{}, {}, {}] },
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill("Mon app analyse");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Analyse spatiale", exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Outil d'analyse").selectOption("buffer");
  await page.getByLabel("Collection analysée").selectOption("c1");
  await page.getByLabel(/Distance/).fill("500");
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByText("3 entité(s) en résultat.")).toBeVisible();
  expect(posted).toMatchObject({
    tool: "buffer",
    params: { distance: 500 },
    output: "ephemeral",
  });
});

// ARC-33 × ARC-25 : outil « Statistiques raster par zone » — le raster se choisit dans la liste
// des COG hébergés, jamais par un identifiant saisi à la main.
test("ARC-33 : le widget Analyse résume un raster sous les polygones d'une collection", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/analysis/tools", (route) =>
    route.fulfill({
      json: {
        tools: [
          {
            name: "zonalStats",
            label: "Statistiques raster par zone",
            help: "Résume une bande d'un raster sous chaque polygone.",
            needsOtherCollection: false,
            paramsSchema: {
              properties: {
                rasterItemId: { type: "string", title: "Raster" },
                stats: { type: "array", title: "Statistiques" },
              },
              required: ["rasterItemId"],
            },
          },
        ],
      },
    }),
  );
  await page.route("https://core.test/v1/collections?*", (route) =>
    route.fulfill({ json: { collections: [{ id: "c1", title: "Communes" }] } }),
  );
  await page.route("https://core.test/v1/items?type=raster*", (route) =>
    route.fulfill({ json: { items: [{ pk: "r1", title: "MNT 25 m" }] } }),
  );
  let posted: unknown = null;
  await page.route("https://core.test/v1/collections/c1/analysis", async (route) => {
    posted = route.request().postDataJSON();
    await route.fulfill({
      json: {
        tool: "zonalStats",
        output: "ephemeral",
        srid: 4326,
        truncated: false,
        featureCollection: { type: "FeatureCollection", features: [{}, {}] },
      },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre", { exact: true }).fill("Mon app raster");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Analyse spatiale", exact: true }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Outil d'analyse").selectOption("zonalStats");
  await page.getByLabel("Collection analysée").selectOption("c1");
  await page.getByLabel(/^Raster/).selectOption("r1");
  await page.getByLabel("Statistiques", { exact: true }).fill("count, mean");
  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByText("2 entité(s) en résultat.")).toBeVisible();
  expect(posted).toMatchObject({
    tool: "zonalStats",
    params: { rasterItemId: "r1", stats: ["count", "mean"] },
    output: "ephemeral",
  });
});

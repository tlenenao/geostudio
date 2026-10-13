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

// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));
// PNG 1x1 : un vrai fichier image pour l'upload du logo.
const PNG_1X1 = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

async function setup(page: Page) {
  await mockCore(page);
  await page.route("https://core.test/v1/instance", (route) =>
    route.fulfill({ json: { readOnly: false, etlEnabled: false, exportEnabled: true } }),
  );
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
}

async function createMap(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte à imprimer");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
}

// ARC-16 : un gabarit A3 paysage complet (titre, cartouche, texte libre, logo,
// flèche du nord, échelle, légende de la symbologie réelle) se compose dans
// l'éditeur, s'enregistre, et se rend à la taille exacte de la feuille.
test("gabarit A3 paysage : éléments du rendu d'export et échelle graphique à ±1 %", async ({
  page,
}) => {
  await setup(page);
  await createMap(page);

  // Symbologie bivariée sur une couche, pour que la légende imprimée la reflète.
  await page.getByRole("button", { name: /Communes/ }).click();
  await page.getByLabel("Mode avancé").selectOption("bivariate");
  await page.getByLabel("Champ X").selectOption("pop");
  await page.getByLabel("Champ Y").selectOption("revenu");
  await page.getByRole("button", { name: "Recalculer l'échelle" }).click();
  await expect(page.getByText(/Échelle non calculée/)).toHaveCount(0);

  await page.getByLabel("Format", { exact: true }).selectOption("a3");
  await page.getByLabel("Orientation", { exact: true }).selectOption("landscape");
  await page.getByLabel("Titre", { exact: true }).fill("Atlas communal");
  await page.getByLabel("Échelle graphique").check();
  await page.getByLabel("Flèche du nord").check();
  await page.getByLabel("Texte libre").fill("Source : INSEE 2024");
  await page.getByLabel("Cartouche").fill("Service SIG");
  await page.getByLabel(/^Logo/).setInputFiles({
    name: "logo.png",
    mimeType: "image/png",
    buffer: PNG_1X1,
  });

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  // Config réellement persistée (aller-retour, pas l'état local de l'éditeur).
  const saved = await page.evaluate(async () => {
    const r = await fetch("https://core.test/v1/configs/by-item/77");
    return r.json();
  });
  expect(saved.config.printLayout).toMatchObject({
    pageSize: "a3",
    orientation: "landscape",
    scaleBar: true,
    northArrow: true,
    freeText: "Source : INSEE 2024",
    logo: expect.stringMatching(/^data:image\/png;base64,/),
  });
  const { center, zoom } = saved.config.map.view as { center: [number, number]; zoom: number };

  // Rendu tel que le worker le fait : viewport = feuille A3 paysage.
  await page.setViewportSize({ width: 1587, height: 1123 });
  await page.goto("/maps/77?exportRender=1");
  await expect(page.locator('[data-export-ready="true"]')).toBeAttached({ timeout: 30_000 });

  await expect(page.getByTestId("print-title")).toHaveText("Atlas communal");
  await expect(page.getByTestId("print-cartouche")).toHaveText("Service SIG");
  await expect(page.getByTestId("print-free-text")).toHaveText("Source : INSEE 2024");
  await expect(page.getByTestId("print-logo")).toBeVisible();
  await expect(page.getByTestId("print-north-arrow")).toBeVisible();
  // La légende reflète la symbologie courante (mode bivarié).
  await expect(page.getByTestId("print-legend").getByTestId("legend-advanced")).toBeVisible();

  // Aucun élément d'interface d'édition dans la capture.
  await expect(page.getByRole("button", { name: "Enregistrer" })).toHaveCount(0);

  // Échelle : largeur affichée vs distance annoncée, mesurées sur la page.
  const scale = page.locator(".maplibregl-ctrl-scale");
  await expect(scale).toBeVisible();
  const label = (await scale.textContent())?.trim() ?? "";
  const m = /^([\d\s.,]+)\s*(km|m)$/.exec(label);
  expect(m, `libellé d'échelle « ${label} »`).not.toBeNull();
  const meters = Number(m![1].replace(/\s/g, "").replace(",", ".")) * (m![2] === "km" ? 1000 : 1);
  const widthPx = (await scale.boundingBox())!.width;
  // Mètres par pixel CSS au centre, projection Web Mercator, tuiles de 512 px.
  const mpp = (40075016.686 * Math.cos((center[1] * Math.PI) / 180)) / (512 * 2 ** zoom);
  const expectedPx = meters / mpp;
  // Largeur réellement rendue (boîte mesurée sur la page, bordure comprise).
  expect(Math.abs(widthPx - expectedPx) / expectedPx).toBeLessThan(0.01);

  // Le rendu occupe la feuille entière.
  const box = await page.getByTestId("map-container").boundingBox();
  expect(Math.round(box!.width)).toBe(1587);
  expect(Math.round(box!.height)).toBe(1123);
});

test("export SVG puis annulation d'un export en cours", async ({ page }) => {
  await setup(page);
  let createdBody: unknown = null;
  let cancelled = false;
  await page.route("**/export", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    createdBody = route.request().postDataJSON();
    await route.fulfill({ status: 202, json: { jobId: "job-svg" } });
  });
  await page.route("**/export/jobs/job-svg", (route) =>
    route.fulfill({
      json: {
        id: "job-svg",
        status: cancelled ? "cancelled" : "running",
        resultUrl: null,
        error: null,
      },
    }),
  );
  await page.route("**/export/jobs/job-svg/cancel", async (route) => {
    cancelled = true;
    await route.fulfill({
      json: { id: "job-svg", status: "cancel_requested", resultUrl: null, error: null },
    });
  });

  await createMap(page);
  await page.getByRole("button", { name: "Exporter", exact: true }).click();
  await page.getByRole("button", { name: "SVG", exact: true }).click();
  await expect.poll(() => createdBody).toEqual({ itemId: "77", format: "svg" });

  await page.getByRole("button", { name: "Annuler l'export" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Annulation demandée" })).toBeVisible();
  // Le sondage continue jusqu'à l'acquittement du worker.
  await expect(page.getByRole("status").filter({ hasText: "Annulé" })).toBeVisible({
    timeout: 10_000,
  });
});

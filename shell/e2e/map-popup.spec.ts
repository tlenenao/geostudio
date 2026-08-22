// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { mockCore } from "./mocks";

const TILE = readFileSync(fileURLToPath(new URL("./fixtures/world-tile.mvt", import.meta.url)));

// La preuve de sortie du chantier 4.1 du plan d'action : cliquer une entité
// d'une collection servie en tuiles MVT ouvre un popup renseigné, sur une
// carte publiée, sans widget d'app à côté.
test("un lecteur clique une entité tuilée et voit ses attributs", async ({ page }) => {
  await mockCore(page);
  // Toute tuile demandée renvoie la même fixture : un polygone couvrant
  // presque toute la tuile, donc un clic au centre du canvas le touche
  // quel que soit le niveau de zoom courant.
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );

  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  // Deviation from the brief's literal coordinates: at this viewport/zoom
  // combination MapLibre actually requests four z=1 subtiles to cover the
  // view (not the single z=0/0/0 tile the brief assumed), and the same
  // fixture body is reused verbatim for every subtile — so each subtile
  // shows its own copy of the (buffered) polygon, with a thin unfilled seam
  // running along the shared subtile edges exactly through the canvas
  // center. Clicking a quarter-point instead reliably lands inside one
  // subtile's fill. The click is also retried (`toPass`) rather than fired
  // once: it can legitimately land before the tile has finished loading and
  // rendering, and a single click that misses never gets a second chance.
  const cx = box.x + box.width / 4;
  const cy = box.y + box.height / 4;
  const popup = page.getByRole("dialog", { name: "Attributs de l'entité" });
  await expect(async () => {
    await page.mouse.click(cx, cy);
    await expect(popup).toBeVisible({ timeout: 300 });
  }).toPass({ timeout: 10000 });
  await expect(popup.getByText("Tulle")).toBeVisible();
  await expect(popup.getByText("Habitants")).toBeVisible();
  await expect(popup.getByText("14000")).toBeVisible();
  // Le champ titre n'est pas répété en ligne d'attribut.
  await expect(popup.getByText("nom")).toHaveCount(0);

  await popup.getByRole("button", { name: "Fermer" }).click();
  await expect(popup).toHaveCount(0);
});

test("la requête de tuile porte le jeton de session", async ({ page }) => {
  await mockCore(page);
  const tileRequest = page.waitForRequest((r) => r.url().includes("/collections/communes/tiles/"));
  await page.route("**/collections/communes/tiles/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: TILE,
    }),
  );
  await page.goto("/maps/map-1");
  const req = await tileRequest;
  expect(req.headers()["authorization"]).toMatch(/^Bearer /);
});

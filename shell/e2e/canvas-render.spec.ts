// SPDX-License-Identifier: Apache-2.0
// REV-267 (P04.07) : filet de rendu — la page carte dessine réellement (canvas
// WebGL non uniforme), pas seulement un <canvas> monté. Un style local cassé ou
// un fond tuilé hors-ligne donnerait un canvas vide que `toBeVisible()` accepte.
import { expect, test, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// Capture (compositée, donc valable pour un canvas WebGL sans
// preserveDrawingBuffer) décodée dans le navigateur : nombre de couleurs
// distinctes échantillonnées (plafonné à 2).
async function distinctColors(page: Page, shot: Buffer): Promise<number> {
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement("canvas");
    c.width = img.width;
    c.height = img.height;
    const ctx = c.getContext("2d")!;
    ctx.drawImage(img, 0, 0);
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    const seen = new Set<number>();
    for (let i = 0; i < d.length && seen.size < 2; i += 4 * 97) {
      seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    }
    return seen.size;
  }, shot.toString("base64"));
}

test("la carte dessine : le canvas n'est pas d'une couleur uniforme", async ({ page }) => {
  await mockCore(page);
  await page.goto("/maps/map-1");
  const canvas = page.locator("canvas.maplibregl-canvas");
  await expect(canvas).toHaveCount(1);
  await expect
    .poll(async () => distinctColors(page, await canvas.screenshot()), { timeout: 15_000 })
    .toBeGreaterThan(1);
});

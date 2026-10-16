import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

// REV-367 i : les fonds de carte partagés du tenant apparaissent dans le sélecteur de fond
// de l'éditeur de carte ; un fond `xyz:` est rendu comme style raster (le canvas se monte).
test("un fond de carte du tenant est proposé dans l'éditeur de carte et sélectionnable", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("https://core.test/v1/basemaps", (route) =>
    route.fulfill({
      json: [
        { id: "b1", label: "Ortho communale", style: "xyz:https://tuiles.test/{z}/{x}/{y}.png" },
      ],
    }),
  );
  await page.route("https://tuiles.test/**", (route) => route.fulfill({ status: 404, body: "" }));
  await page.goto("/maps/map-1?tab=settings");
  const select = page.getByLabel("Fond de carte");
  await expect(select.locator("option", { hasText: "Ortho communale" })).toHaveCount(1);
  await select.selectOption({ label: "Ortho communale" });
  await expect(select).toHaveValue("xyz:https://tuiles.test/{z}/{x}/{y}.png");
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
});

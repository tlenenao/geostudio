import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create a Map → add a layer → save → canvas mounts", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Ma carte");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/maps\/77$/);

  // The real MapLibre canvas mounts (Chromium has WebGL).
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Add a layer from the picker, then save.
  await page.getByRole("button", { name: /Communes/ }).click();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // No error alert after saving.
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);
});

test("add a 3D tileset + terrain, set the camera, save, and reload — everything round-trips", async ({ page }) => {
  await mockCore(page);
  await page.route("https://example.test/tileset.json", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        asset: { version: "1.0" },
        geometricError: 500,
        root: { boundingVolume: { region: [0, 0, 0, 0, 0, 0] }, geometricError: 500, refine: "ADD", children: [] },
      }),
    }),
  );
  await page.route("https://example.test/dem/**", (route) => route.fulfill({ status: 404, body: "" }));

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte 3D");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  // Add a 3D Tiles layer by URL.
  await page.getByLabel("Titre du tileset 3D").fill("Bâtiments");
  await page.getByLabel("URL du tileset.json").fill("https://example.test/tileset.json");
  await page.getByRole("button", { name: "Ajouter le tileset 3D" }).click();

  // Enable terrain.
  await page.getByLabel("Activer le terrain 3D").check();
  await page.getByLabel("URL de tuiles terrain").fill("https://example.test/dem/{z}/{x}/{y}.png");

  // Set the camera.
  await page.getByLabel("Inclinaison de la caméra").fill("45");
  await page.getByLabel("Orientation de la caméra").fill("90");

  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/échec de l'enregistrement/i)).toHaveCount(0);

  await page.reload();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Bâtiments").first()).toBeVisible();
  await expect(page.getByLabel("Activer le terrain 3D")).toBeChecked();
  await expect(page.getByLabel("URL de tuiles terrain")).toHaveValue("https://example.test/dem/{z}/{x}/{y}.png");
  await expect(page.getByLabel("Inclinaison de la caméra")).toHaveValue("45");
  await expect(page.getByLabel("Orientation de la caméra")).toHaveValue("90");
});

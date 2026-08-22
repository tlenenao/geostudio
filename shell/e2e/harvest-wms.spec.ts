// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

const CAPS = "https://ows.example.com/geoserver/wms?service=WMS&request=GetCapabilities";
const TILES =
  "https://ows.example.com/geoserver/wms?service=WMS&version=1.3.0&request=GetMap&layers=topp:states&styles=&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=256&height=256&format=image/png&transparent=true";

test("un admin déclare une source WMS, la moissonne, et affiche la couche raster dans une carte", async ({
  page,
}) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: true,
      },
    });
  });

  let created: unknown = null;
  let runCount = 0;
  const harvestedById = new Map<string, Record<string, unknown>>();
  // Couches raster exposées par /harvest/layers après moissonnage.
  const rasterLayers: { id: string; title: string; kind: "raster"; tilesUrl: string }[] = [];

  await page.route("https://core.test/harvest/sources", async (route) => {
    if (route.request().method() === "POST") {
      created = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "src-1",
          type: "wms",
          url: CAPS,
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        sources: created
          ? [
              {
                id: "src-1",
                type: "wms",
                url: CAPS,
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: runCount > 0 ? "2026-07-23T10:00:00Z" : null,
                lastStatus: runCount > 0 ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      },
    });
  });

  await page.route("https://core.test/harvest/sources/src-1/run", async (route) => {
    runCount += 1;
    harvestedById.set(`${CAPS}#topp:states`, {
      pk: "ext-wms-1",
      resourceType: "external",
      title: "USA States (WMS distant)",
      abstract: "",
      owner: "mockuser",
      thumbnailUrl: null,
      date: "2026-01-01",
      configId: null,
      isPublished: false,
    });
    rasterLayers.length = 0;
    rasterLayers.push({
      id: "ext-wms-1",
      title: "USA States (WMS distant)",
      kind: "raster",
      tilesUrl: TILES,
    });
    await route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.route("https://core.test/items*", async (route) => {
    const url = new URL(route.request().url());
    const type = url.searchParams.get("type");
    // LayerPicker also fires a hosted-tileset3d lookup (`?type=tileset3d`,
    // Task 10) against this same generic /items endpoint — without this
    // filter it would answer with the harvested WMS item too (resourceType
    // "external"), producing a phantom tiles3d entry with the same title as
    // the real raster source and a strict-mode-ambiguous button below.
    const items = Array.from(harvestedById.values()).filter(
      (item) => !type || item.resourceType === type,
    );
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });

  await page.route("https://core.test/harvest/layers*", async (route) => {
    const url = new URL(route.request().url());
    const q = url.searchParams.get("q");
    const layers = q
      ? rasterLayers.filter((l) => l.title.toLowerCase().includes(q.toLowerCase()))
      : rasterLayers;
    await route.fulfill({ json: { layers } });
  });

  // 1) Déclarer et moissonner la source WMS
  await page.goto("/admin/harvest");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(CAPS);
  await dialog.getByLabel("Type").selectOption("wms");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect
    .poll(() => created)
    .toEqual({
      type: "wms",
      url: CAPS,
      mode: "reference",
      enabled: true,
    });
  await page.getByRole("button", { name: "Moissonner maintenant" }).click();
  await expect.poll(() => runCount).toBe(1);
  await expect(page.getByText("ok")).toBeVisible();

  // 2) L'item raster externe apparaît au catalogue
  await page.goto("/");
  await expect(page.getByText("USA States (WMS distant)")).toBeVisible();
  // .last(), not the default first match: the catalog's "Type" <select>
  // (SP-23, chantier 4.6) always renders an <option value="external">Externe</option>
  // ahead of the item grid in DOM order — .last() lands on the item's own
  // badge instead.
  await expect(page.getByText("Externe").last()).toBeVisible();

  // 3) Créer une carte, chercher la couche, l'ajouter
  await page.getByRole("button", { name: "Nouveau" }).click();
  const newDialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await newDialog.getByLabel("Type").selectOption("map");
  await newDialog.getByLabel("Titre").fill("Carte WMS");
  await newDialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/maps\/77$/);

  const search = page.getByRole("searchbox", { name: /rechercher une source de couche/i });
  await search.fill("USA");
  await page.getByRole("button", { name: /USA States \(WMS distant\)/ }).click();

  // 4) Assertion : une couche raster est ajoutée à la carte (LayersPanel).
  await expect(
    page.getByRole("button", { name: "Retirer USA States (WMS distant)" }),
  ).toBeVisible();
});

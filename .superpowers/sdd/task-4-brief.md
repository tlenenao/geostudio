## Task 4: E2E — categorical legend, numeric color+size legend, cross-filter regression, unconfigured no-op

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` (already defined at the top of this file, unmodified); the `map` widget's new PropsPanel fields, addressable via labels `"Champ couleur"` / `"Type de couleur"` / `"Champ taille"`.
- Produces: nothing consumed by later tasks — this is the last task in the plan.

- [ ] **Step 1: Write the four E2E tests**

Append to the end of `shell/e2e/analytics-context.spec.ts` (after the last existing test, the SP-14g unconfigured-pivot scenario):

```ts
// -------------------------------------------------------------------------
// Scénario 22 (SP-14h) — couleur catégorielle : le widget Carte colore une
// couche polygonale par un champ catégoriel ; la légende affiche les valeurs
// distinctes obtenues via une requête statistics (groupBy) séparée de la
// DataSource "features" qui alimente la géométrie.
// -------------------------------------------------------------------------
test("a map with a categorical color encoding shows a legend built from a groupBy domain query (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/communes/schema", async (route) => {
    await route.fulfill({
      json: { collection: "communes", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/communes/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, geometry: { type: "Polygon", coordinates: [[[2, 46], [3, 46], [3, 47], [2, 47], [2, 46]]] }, properties: { region: "Nord" } },
          { id: 2, geometry: { type: "Polygon", coordinates: [[[2, 44], [3, 44], [3, 45], [2, 45], [2, 44]]] }, properties: { region: "Sud" } },
        ],
      },
    });
  });
  await page.route("**/collections/communes/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "region", rows: [{ region: "Nord", value: 1 }, { region: "Sud", value: 1 }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "communes", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte catégorielle");
  await addFeaturesSource(page, "communes");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("region");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("Nord")).toBeVisible();
  await expect(page.getByText("Sud")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 23 (SP-14h) — couleur + taille numériques : le widget Carte
// dimensionne et colore une couche ponctuelle par deux champs numériques ;
// la légende affiche les bornes des deux domaines (deux requêtes
// statistics distinctes, une par champ).
// -------------------------------------------------------------------------
test("a map with numeric color and size encodings shows a legend with both domains' bounds (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/points/schema", async (route) => {
    await route.fulfill({
      json: { collection: "points", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 },
        fields: [{ name: "valeur", type: "number" }, { name: "montant", type: "number" }] },
    });
  });
  await page.route("**/collections/points/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, geometry: { type: "Point", coordinates: [2.3, 46.5] }, properties: { valeur: 10, montant: 2 } },
          { id: 2, geometry: { type: "Point", coordinates: [2.5, 46.7] }, properties: { valeur: 90, montant: 18 } },
        ],
      },
    });
  });
  await page.route("**/collections/points/aggregate", async (route) => {
    const body = route.request().postDataJSON() as { measures?: { field: string }[] };
    const field = body.measures?.[0]?.field;
    if (field === "valeur") {
      await route.fulfill({ json: { categoryKey: "valeur", rows: [{ min: 10, max: 90 }] } });
      return;
    }
    await route.fulfill({ json: { categoryKey: "montant", rows: [{ min: 2, max: 18 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "points", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte numérique");
  await addFeaturesSource(page, "points");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("valeur");
  await page.getByLabel("Type de couleur").selectOption("numeric");
  await page.getByLabel("Champ taille").fill("montant");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  await expect(page.getByText("10 – 90")).toBeVisible();
  await expect(page.getByText("2 – 18")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 24 (SP-14h) — non-régression : un clic sur une entité stylée
// déclenche toujours le cross-filter par pk (comportement pk existant,
// inchangé par la symbologie). Fixture : une entité (id=1) en polygone
// couvrant tout le viewport par défaut (center [2.4,46.6], zoom 5), une
// seconde (id=2) placée hors champ (jamais rendue à l'écran) — n'importe
// quel clic sur le canvas ne peut donc toucher que id=1, sans dépendre
// d'un calcul précis de projection Web Mercator.
// -------------------------------------------------------------------------
test("a click on a styled map feature still cross-filters a sibling table by pk (SP-14h)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/zones/schema", async (route) => {
    await route.fulfill({
      json: { collection: "zones", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/zones/items*", async (route) => {
    const url = new URL(route.request().url());
    const id = url.searchParams.get("id");
    const all = [
      { id: 1, geometry: { type: "Polygon", coordinates: [[[-20, 30], [30, 30], [30, 65], [-20, 65], [-20, 30]]] }, properties: { region: "Nord" } },
      { id: 2, geometry: { type: "Polygon", coordinates: [[[170, -80], [175, -80], [175, -75], [170, -75], [170, -80]]] }, properties: { region: "Sud" } },
    ];
    const features = id ? all.filter((f) => String(f.id) === id) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/zones/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "region", rows: [{ region: "Nord", value: 1 }, { region: "Sud", value: 1 }] },
    });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "zones", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Carte cross-filter");
  await addFeaturesSource(page, "zones");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "zones");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ couleur").fill("region");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });
  await page.getByLabel("Colonnes").fill("region");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/zones/items") && r.url().includes("id=1"));
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 25 (SP-14h) — non-régression : sans encodings configurés, le
// widget Carte se comporte exactement comme avant (aucune requête statistics
// de domaine n'est émise).
// -------------------------------------------------------------------------
test("a map with no encodings configured issues no domain query (SP-14h)", async ({ page }) => {
  await mockCore(page);
  let aggregateCalls = 0;
  await page.route("**/collections/parcelles/schema", async (route) => {
    await route.fulfill({
      json: { collection: "parcelles", pk: "id", geometry: { column: "geom", type: "Polygon", srid: 4326 },
        fields: [{ name: "region", type: "string" }] },
    });
  });
  await page.route("**/collections/parcelles/items*", async (route) => {
    await route.fulfill({
      json: { type: "FeatureCollection", features: [
        { id: 1, geometry: { type: "Polygon", coordinates: [[[2, 46], [3, 46], [3, 47], [2, 47], [2, 46]]] }, properties: { region: "Nord" } },
      ] },
    });
  });
  await page.route("**/collections/parcelles/aggregate", async (route) => {
    aggregateCalls++;
    await route.fulfill({ json: { categoryKey: "region", rows: [] } });
  });

  await createApp(page, "Carte sans symbologie");
  await addFeaturesSource(page, "parcelles");

  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Enregistrer" }).click();

  const itemsReq = page.waitForRequest((r) => r.url().includes("/collections/parcelles/items"));
  await page.goto("/apps/9");
  await itemsReq;
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();
  expect(aggregateCalls).toBe(0);
});
```

- [ ] **Step 2: Run the four new E2E tests**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts -g "SP-14h"`
Expected: PASS — 4 tests green. If a selector or assertion fails, use Playwright's trace/HTML report (`npx playwright show-report`) to inspect the actual DOM and adjust the test to match real rendered output — do not change the widget implementation to satisfy an incorrect test expectation without re-checking the spec first.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: PASS — all existing specs remain green (72+ scenarios), plus the 4 new SP-14h scenarios.

- [ ] **Step 4: Run the full non-regression check (unit + build)**

Run: `cd shell && npm run test && npm run build`
Expected: PASS — full Vitest suite green, `tsc --noEmit` clean, Vite build succeeds.

- [ ] **Step 5: Commit**

```bash
cd shell && git add e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover map categorical/numeric symbology legends, pk cross-filter regression and no-encodings no-op (SP-14h)"
```

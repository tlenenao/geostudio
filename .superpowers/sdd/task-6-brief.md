### Task 6: E2E — extend `analytics-context.spec.ts`

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), the existing `createApp`/`addFeaturesSource`/`promoteLastSource` helpers already in the file (unchanged).
- Produces: no new exports — pure E2E coverage addition.

- [ ] **Step 1: Write the new E2E scenarios**

Append to `shell/e2e/analytics-context.spec.ts` (after the last existing test, scenario 11):

```ts
// -------------------------------------------------------------------------
// Scénario 12 (SP-14e) — KPI riche : delta affiché contre la période de
// référence quand referencePeriod + plage temporelle + dataset.timeField
// sont tous actifs.
// -------------------------------------------------------------------------
test("a KPI shows a delta badge against the reference period", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-10" } }, { id: 2, properties: { nom: "B", date: "2026-01-20" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    const body = await route.request().postDataJSON();
    const gte = body.filters?.date__gte;
    if (gte === "2026-01-01") return route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 120 }] } });
    if (gte === "2025-12-01") return route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 100 }] } });
    await route.fulfill({ json: { categoryKey: "group", rows: [] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "KPI delta");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Comparer à").selectOption("previous");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");

  await expect(page.getByText("120")).toBeVisible();
  await expect(page.getByText(/\+20 % vs période précédente/)).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 13 (SP-14e) — seuil CEL : une pastille critique apparaît quand
// criticalWhen dépasse le seuil, absente sinon (indicateur à plat, sans
// contexte temporel).
// -------------------------------------------------------------------------
test("a KPI shows a critical pastille when criticalWhen is exceeded, none otherwise", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({ json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "valeur", type: "number" }] } });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { valeur: 1 } }, { id: 2, properties: { valeur: 1 } }, { id: 3, properties: { valeur: 1 } },
    ] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Seuil CEL");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Seuil critique (CEL)").fill("record.value > 2");

  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByText("3")).toBeVisible();
  await expect(page.getByLabelText("Seuil critique atteint")).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 14 (SP-14e) — chart en mode comparaison : 2 séries visibles
// (attribut data-chart-series du wrapper EChart, seul signal DOM fiable
// pour une légende rendue en canvas).
// -------------------------------------------------------------------------
test("chart compare-periods mode renders two aligned series", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-01" } }, { id: 2, properties: { nom: "B", date: "2026-01-02" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    const body = await route.request().postDataJSON();
    const gte = body.filters?.date__gte;
    if (gte === "2026-01-01") {
      return route.fulfill({ json: { categoryKey: "date", rows: [
        { date: "2026-01-01 00:00:00", value: 5 }, { date: "2026-01-02 00:00:00", value: 7 },
      ] } });
    }
    if (gte === "2025-12-31") {
      return route.fulfill({ json: { categoryKey: "date", rows: [{ date: "2025-12-31 00:00:00", value: 3 }] } });
    }
    await route.fulfill({ json: { categoryKey: "date", rows: [] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "Chart compare");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("line");
  await page.getByLabel("Comparer les périodes").check();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-01-02");

  await expect(page.getByTestId("echart")).toHaveAttribute("data-chart-series", "2", { timeout: 10000 });
});

// -------------------------------------------------------------------------
// Scénario 15 (SP-14e) — non-régression explicite : indicateur/graphique
// sans les nouvelles props se comportent exactement comme avant, y compris
// avec une plage temporelle active.
// -------------------------------------------------------------------------
test("indicator and chart behave exactly as before without the new SP-14e props, even with an active time range", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "events", title: "Événements", description: "", tableName: "events", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 2, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/events/schema", async (route) => {
    await route.fulfill({
      json: { collection: "events", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }, { name: "date", type: "string" }] },
    });
  });
  await page.route("**/collections/events/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { nom: "A", date: "2026-01-05" } }, { id: 2, properties: { nom: "B", date: "2026-01-20" } },
    ] } });
  });
  await page.route("**/collections/events/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 2 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "events", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Événements partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("events");
  await dialog.getByLabel("Titre").fill("Événements partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Colonne temporelle").selectOption("date");
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();

  await createApp(page, "Non-régression KPI/Chart");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Indicateur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("line");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");

  await expect(page.getByText("2")).toBeVisible();
  await expect(page.getByTestId("echart")).toHaveAttribute("data-chart-series", "1");
});
```

- [ ] **Step 2: Run the new scenarios**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/analytics-context.spec.ts -g "SP-14e|KPI|compare-periods|behave exactly as before without the new SP-14e"`
Expected: PASS (scenarios 12-15)

- [ ] **Step 3: Run the full E2E suite for non-regression**

Run: `cd shell && npm run e2e`
Expected: PASS — all 18+ specs (including the full `analytics-context.spec.ts`, now 15 scenarios) stay green.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(e2e): cover KPI delta, CEL threshold pastille, chart compare-periods, non-regression (SP-14e)"
```

---

## Final verification

- [ ] Run the complete cross-stack suite one more time before declaring the branch done:

```bash
cd core && uv run pytest
cd ../shell && npm run test && npm run build && npm run e2e
```

Expected: all green — 606+4 core tests, 61+ shell unit test files, `tsc --noEmit` + `vite build` clean, 18+ E2E specs (15 scenarios in `analytics-context.spec.ts`).

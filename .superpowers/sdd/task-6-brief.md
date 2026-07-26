## Task 6: E2E — explorer menu and drill panel

**Files:**
- Modify: `shell/e2e/analytics-context.spec.ts` (append new scenarios; reuses the existing `mockCore`, `createApp`, `addFeaturesSource`, `promoteLastSource` helpers already defined in the file, cf. SP-14b/14c)

**Interfaces:**
- Consumes: the running app built by Tasks 1-5 (`⋮ Explorer` button, `Voir les entités` menu item, `Fermer le panneau` close button) through the real UI — no direct import of shell source.

- [ ] **Step 1: Write the failing E2E tests**

Append to `shell/e2e/analytics-context.spec.ts`, after the last existing `test(...)` block, before the file's closing:

```ts
// -------------------------------------------------------------------------
// Scénario 3 (SP-14d) — menu « explorer » : « Voir les entités » montre les
// lignes filtrées par le cross-filter courant, que le panneau soit ouvert
// depuis un autre widget ou depuis le widget qui a lui-même posé le filtre.
// -------------------------------------------------------------------------
test("voir les entités shows cross-filtered rows, even opened from the widget that set the filter", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }, { name: "valeur", type: "number" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    const cat = new URL(route.request().url()).searchParams.get("categorie");
    const all = [
      { id: 1, properties: { categorie: "Nord", valeur: 100 } },
      { id: 2, properties: { categorie: "Sud", valeur: 100 } },
    ];
    const features = cat ? all.filter((f) => f.properties.categorie === cat) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Explorer");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");
  const nordBar = { x: box.width * 0.3, y: box.height * 0.42 };
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: nordBar });
  await filteredReq;

  // Ouvrir « Voir les entités » depuis la Table (widget différent de l'origine
  // du clic) — le graphique est ajouté en premier, donc son bouton Explorer
  // est `.first()`, celui de la table `.last()`.
  await page.getByRole("button", { name: "Explorer" }).last().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
  await page.getByRole("button", { name: "Fermer le panneau" }).click();
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();

  // Ouvrir « Voir les entités » depuis le Graphique lui-même (l'origine du
  // clic) — reste filtré, contrairement au graphique qui s'affiche lui-même
  // sans filtre (design §4 : la requête synthétique du tiroir n'a jamais
  // l'id d'un widget réel).
  await page.getByRole("button", { name: "Explorer" }).first().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();

  // Fermer via Échap (plutôt que la croix, déjà couvert plus haut) — l'app
  // sous-jacente et son cross-filter restent inchangés.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 4 (SP-14d) — non-régression : une app `interactions: "manual"`
// n'affiche jamais le bouton « explorer », quel que soit le widget.
// -------------------------------------------------------------------------
test("the explorer menu never appears when interactions is manual", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({ json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "categorie", type: "string" }] } });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [{ id: 1, properties: { categorie: "Nord" } }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Manuel");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Interactions automatiques (cross-filter)").uncheck();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Explorer" })).toHaveCount(0);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts`
Expected: the 2 new scenarios FAIL against a `dev` build that predates Task 1-5 (no `⋮` button exists yet). If run *after* Tasks 1-5 are already merged (normal execution order of this plan), this step instead confirms they PASS — in that case treat Step 2 as already satisfied and proceed straight to Step 4's full run.

- [ ] **Step 3: Fix up selectors if needed**

Tasks 1-5 already implement everything these scenarios exercise. If a selector doesn't match (e.g. accessible name differs, or `.first()`/`.last()` ordering doesn't match actual DOM order), adjust the locator in the test — the underlying feature code does not change for this task.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run e2e -- analytics-context.spec.ts`
Expected: PASS, all scenarios in the file (previous SP-14b/14c ones + the 2 new SP-14d ones).

Run: `cd shell && npm run e2e`
Expected: full E2E suite green (previous 19 specs unaffected, `analytics-context.spec.ts` now covers SP-14d too).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/analytics-context.spec.ts
git commit -m "test(shell): E2E voir les entités — cross-filtered even from origin, non-regression manual (SP-14d)"
```

---

## Final Verification

- [ ] Run the full check used at the end of every SP-14 sub-part:

```bash
cd shell && npm run build && npm run test && npm run e2e
```

Expected: `tsc --noEmit` clean, `vite build` succeeds, full unit suite green (previous total + 23 new tests: 5 Task 1 + 4 Task 2 + 5 Task 3 + 8 Task 4 + 1 Task 5 — the exact count is whatever `npm run test`'s summary line reports), full E2E suite green (previous 19 specs + 2 new SP-14d scenarios in `analytics-context.spec.ts`).

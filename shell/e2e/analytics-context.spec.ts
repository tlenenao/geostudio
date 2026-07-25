// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

// SP-14b — E2E du contexte analytique global (cross-filter, emprise, plage
// temporelle, restauration URL, non-régression). Chaque test appelle
// `mockCore(page)` puis surcharge quelques routes `page.route(...)` (mêmes
// conventions que actions.spec.ts / datasets-shared.spec.ts) et construit
// l'app via la vraie UI du builder — jamais en injectant du JSON brut.

// Décodage du paramètre ?ctx= (base64url Unicode-safe, miroir de
// lib/analyticsContextUrl.ts) — sert à distinguer le canal auto (contexte
// analytique) du canal manuel (bus d'actions) en scénario 5, et à capturer
// l'état pour le scénario 4.
function decodeCtx(rawUrl: string): { timeRange: unknown; extent: unknown; crossFilter: Record<string, unknown> } {
  const raw = new URL(rawUrl).searchParams.get("ctx");
  if (!raw) return { timeRange: null, extent: null, crossFilter: {} };
  const b64 = raw.replace(/-/g, "+").replace(/_/g, "/");
  const padded = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
  const json = Buffer.from(padded, "base64").toString("utf-8");
  const parsed = JSON.parse(json);
  return { timeRange: parsed.timeRange ?? null, extent: parsed.extent ?? null, crossFilter: parsed.crossFilter ?? {} };
}

// Crée une App vide et atterrit sur l'éditeur (/apps/9/edit).
async function createApp(page: Page, title: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill(title);
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
}

// Ajoute une source features et renseigne sa collection (dernière source ajoutée).
async function addFeaturesSource(page: Page, collection: string) {
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).last().fill(collection);
}

// Promeut la dernière source en dataset partagé (→ datasetId="dataset-1" côté mock).
async function promoteLastSource(page: Page, expectedActiveCount: number) {
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).last().click();
  await expect(page.getByText("Dataset partagé actif")).toHaveCount(expectedActiveCount);
}

// -------------------------------------------------------------------------
// Scénario 1 — cross-filter automatique : un clic sur une barre du graphique
// filtre la table (même dataset), un second clic sur la même barre l'efface.
// -------------------------------------------------------------------------
test("a chart click cross-filters a table on the same dataset, second click clears it", async ({ page }) => {
  await mockCore(page);

  // Collection "analytics" : catégorie + valeur numérique (barres cliquables),
  // items filtrés par `categorie` pour observer le cross-filter de bout en bout.
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
  // Dataset partagé "dataset-1" adossé à "analytics" (timeField vide).
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Cross-filter");

  // Deux sources sur le même dataset : une pour le graphique, une pour la table.
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  // Graphique lié à la source 1, catégorie = "categorie".
  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  // Table liée à la source 2.
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  // Interactions automatiques ON (défaut des nouvelles apps, garanti idempotent).
  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : la table montre les deux lignes.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  // Clic sur la première barre (catégorie "Nord") → la table refetch avec
  // categorie=Nord (assertion sur la requête sortante) et se restreint. Les deux
  // barres (valeur 100) forment une bande à mi-hauteur de la petite cellule.
  const nordBar = { x: box.width * 0.3, y: box.height * 0.42 };
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: nordBar });
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  // Second clic sur la même barre → efface le cross-filter, la table remontre tout.
  await chart.click({ position: nordBar });
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 2 — réactivité à l'emprise : déplacer la carte refetch un dataset
// reactsToExtent après le debounce, la requête porte le bbox. Le bbox n'est
// transmis au serveur que sur le chemin statistiques (body.bbox) — spec §3 :
// c'est le consommateur réel du bbox. On observe donc une source statistiques
// sur le même dataset reactsToExtent.
// -------------------------------------------------------------------------
test("map extent reactivity refetches a reactsToExtent dataset after the debounce", async ({ page }) => {
  await mockCore(page);

  let savedDataset: Record<string, unknown> = {};

  // Collection "geo" listée dans le dialog de création de dataset.
  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: { collections: [{ id: "geo", title: "Géo", description: "", tableName: "geo", isPublic: true, editable: true, geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 1, owner: "mockuser" }] },
    });
  });
  await page.route("**/collections/geo/schema", async (route) => {
    await route.fulfill({ json: { collection: "geo", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }] } });
  });
  await page.route("**/collections/geo/items*", async (route) => {
    await route.fulfill({
      json: { type: "FeatureCollection", features: [{ id: 1, geometry: { type: "Point", coordinates: [2.4, 46.6] }, properties: { nom: "P1" } }] },
    });
  });
  // Aggregate (chemin statistiques) : renvoie une ligne, peu importe le bbox.
  await page.route("**/collections/geo/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "nom", rows: [{ nom: "P1", count: 1 }] } });
  });
  // Dataset partagé "dataset-1" : capture le PUT (reactsToExtent réglé via l'UI)
  // et le ressert au runtime.
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      savedDataset = (await route.request().postDataJSON()).dataset;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: savedDataset } });
      return;
    }
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "geo", columns: {}, ...savedDataset } } },
    });
  });
  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Géo partagé", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  // 1. Créer le dataset (dialog) et régler reactsToExtent via DatasetEditPage.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("geo");
  await dialog.getByLabel("Titre").fill("Géo partagé");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  await page.getByLabel("Réagir au déplacement de la carte").check();
  await page.getByRole("button", { name: "Enregistrer les colonnes" }).click();
  await expect.poll(() => savedDataset).toMatchObject({ reactsToExtent: true });

  // 2. App : carte (source 1) + source statistiques (source 2) sur le dataset.
  await createApp(page, "Emprise");
  await addFeaturesSource(page, "geo");
  await page.getByRole("button", { name: "Carte" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });

  // Source 2 : promue puis basculée en "statistiques" (seul chemin qui porte le bbox).
  await addFeaturesSource(page, "geo");
  await promoteLastSource(page, 1);
  await page.getByLabel(/Type de la source/).last().selectOption("statistics");
  await page.getByLabel(/Grouper par/).fill("nom");

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 3. Runtime : déplacer la carte → aggregate refetch avec body.bbox après debounce.
  await page.goto("/apps/9");
  const canvas = page.locator("canvas.maplibregl-canvas").first();
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas has no bounding box");

  const bboxReq = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().includes("/collections/geo/aggregate") && (r.postData() ?? "").includes("bbox"),
    { timeout: 10000 },
  );
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx - 140, cy - 90, { steps: 10 });
  await page.mouse.move(cx - 180, cy - 120, { steps: 6 });
  await page.mouse.up();
  await bboxReq;
});

// -------------------------------------------------------------------------
// Scénario 3 — plage temporelle : un widget date-range filtre une table liée
// à un dataset timeField.
// -------------------------------------------------------------------------
test("a date-range widget filters a timeField-bound dataset", async ({ page }) => {
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
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01" } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01" } },
    ];
    const features = gte && lte ? all.filter((f) => f.properties.date >= gte && f.properties.date <= lte) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
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

  await setupTimeFieldDatasetAndApp(page);

  // Runtime : la table montre les deux lignes.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();

  // Remplir la plage → la table refetch avec date__gte/date__lte.
  const rangeReq = page.waitForRequest(
    (r) => r.url().includes("/collections/events/items") && r.url().includes("date__gte=2026-01-01") && r.url().includes("date__lte=2026-12-31"),
  );
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-12-31");
  await rangeReq;
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 4 — restauration de l'état analytique depuis l'URL (?ctx=).
// Réutilise le montage du scénario 3 (plage temporelle, déterministe).
// -------------------------------------------------------------------------
test("the analytics context in the URL restores on reload", async ({ page }) => {
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
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("date__gte");
    const lte = url.searchParams.get("date__lte");
    const all = [
      { id: 1, properties: { nom: "Ancien", date: "2020-05-01" } },
      { id: 2, properties: { nom: "Récent", date: "2026-06-01" } },
    ];
    const features = gte && lte ? all.filter((f) => f.properties.date >= gte && f.properties.date <= lte) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
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

  await setupTimeFieldDatasetAndApp(page);

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeVisible();

  // Poser la plage → ?ctx= encode le timeRange (après debounce).
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-12-31");
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
  await expect.poll(() => decodeCtx(page.url()).timeRange).not.toBeNull();
  const restored = page.url();
  expect(restored).toContain("ctx=");

  // Navigation fraîche sur l'URL capturée → l'état est restauré sans re-remplir.
  await page.goto(restored);
  await expect(page.getByRole("cell", { name: "Récent" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Ancien" })).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 5 — non-régression : une app sans interactions auto ("manual") ne
// déclenche AUCUN filtrage automatique au clic ; le câblage manuel du bus
// (chart.categorySelected → table.setFilter) continue de fonctionner. Les deux
// canaux coexistent (spec §5).
// -------------------------------------------------------------------------
test("an existing app without interactions never auto-filters on click", async ({ page }) => {
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

  await createApp(page, "Non-régression");

  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  // Câblage MANUEL chart.categorySelected → table.setFilter (comme actions.spec.ts).
  await page.getByLabel("Widget émetteur").selectOption({ label: "Graphique" });
  await page.getByLabel("Événement").selectOption("categorySelected");
  await page.getByLabel("Widget cible").selectOption({ label: "Table" });
  await page.getByLabel("Action", { exact: true }).selectOption("setFilter");
  await page.getByRole("button", { name: "Ajouter une action" }).click();
  await expect(page.getByText(/Graphique\.categorySelected → Table\.setFilter/)).toBeVisible();

  // Interactions automatiques OFF (contrairement au défaut des nouvelles apps).
  await page.getByLabel("Interactions automatiques (cross-filter)").uncheck();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  // Clic sur la barre "Nord" : le canal MANUEL filtre la table…
  const manualReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: { x: box.width * 0.3, y: box.height * 0.42 } });
  await manualReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();

  // …mais AUCUN contexte analytique n'a été écrit dans l'URL (interactions
  // "manual") : additivité (contrainte globale #1) — pas de ?ctx= du tout,
  // même vide, pour une app qui ne passe jamais en mode auto. On laisse passer
  // le délai du debounce (EXTENT_DEBOUNCE_MS = 500ms) pour s'assurer qu'aucune
  // écriture différée ne survient.
  await page.waitForTimeout(700);
  expect(new URL(page.url()).searchParams.has("ctx")).toBe(false);
});

// Montage commun scénarios 3 & 4 : dataset timeField "date" réglé via
// DatasetEditPage, puis app dateRangeFilter + table sur ce dataset.
async function setupTimeFieldDatasetAndApp(page: Page) {
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

  await createApp(page, "Plage temporelle");
  await addFeaturesSource(page, "events");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Plage de dates" }).click();
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();
}

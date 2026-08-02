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

// -------------------------------------------------------------------------
// Scénario 6 — select multi-valeurs : cocher/décocher des valeurs filtre une
// table sur le même dataset via field__in.
// -------------------------------------------------------------------------
test("a select filter multi-value cross-filters a table via field__in", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    const inList = new URL(route.request().url()).searchParams.get("categorie__in");
    const all = [
      { id: 1, properties: { categorie: "Nord" } },
      { id: 2, properties: { categorie: "Sud" } },
    ];
    const features = inList ? all.filter((f) => inList.split(",").includes(f.properties.categorie)) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/analytics/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "categorie", rows: [{ categorie: "Nord", value: 1 }, { categorie: "Sud", value: 1 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Select cross-filter");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Sélecteur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du sélecteur").fill("categorie");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();

  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie__in=Nord"));
  await page.getByLabel("Nord").check();
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();

  await page.getByLabel("Nord").uncheck();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 7 — slider numérique : déplacer une poignée filtre une table par
// plage (field__gte/field__lte), revenir aux bornes complètes l'efface.
// -------------------------------------------------------------------------
test("a slider filter cross-filters a table by range, resetting to full bounds clears it", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/mesures/schema", async (route) => {
    await route.fulfill({
      json: { collection: "mesures", pk: "id", geometry: null,
        fields: [{ name: "score", type: "number" }] },
    });
  });
  await page.route("**/collections/mesures/items*", async (route) => {
    const url = new URL(route.request().url());
    const gte = url.searchParams.get("score__gte");
    const all = [
      { id: 1, properties: { score: 10 } },
      { id: 2, properties: { score: 90 } },
    ];
    const features = gte ? all.filter((f) => f.properties.score >= Number(gte)) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/collections/mesures/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", min: 10, max: 90 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "mesures", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Slider cross-filter");
  await addFeaturesSource(page, "mesures");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "mesures");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Curseur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du curseur").fill("score");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "10" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "90" })).toBeVisible();

  const minInput = page.getByLabel("Borne minimale");
  await expect(minInput).toHaveValue("10");
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/mesures/items") && r.url().includes("score__gte=50"));
  await minInput.evaluate((el: HTMLInputElement) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, "50");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await filteredReq;
  await expect(page.getByRole("cell", { name: "10" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "90" })).toBeVisible();

  await minInput.evaluate((el: HTMLInputElement) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value")!.set!;
    setter.call(el, "10");
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(page.getByRole("cell", { name: "10" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 8 — indicateur : période + cross-filter affichent deux chips,
// effacer une chip ne touche pas l'autre, "Tout effacer" vide tout.
// -------------------------------------------------------------------------
test("the context indicator shows chips for active period and cross-filter, clears individually and globally", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null,
        fields: [{ name: "categorie", type: "string" }, { name: "valeur", type: "number" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { categorie: "Nord", valeur: 100 } },
      { id: 2, properties: { categorie: "Sud", valeur: 100 } },
    ] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Indicateur");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ catégorie").fill("categorie");

  await page.getByRole("button", { name: "Plage de dates" }).click();

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await page.getByLabel("Date de début").fill("2026-01-01");
  await page.getByLabel("Date de fin").fill("2026-02-01");
  await expect(page.getByText(/Période : 2026-01-01 → 2026-02-01/)).toBeVisible();
  await expect(page.getByText("Tout effacer")).toBeHidden();

  const chart = page.getByTestId("echart");
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");
  await chart.click({ position: { x: box.width * 0.3, y: box.height * 0.42 } });
  await expect(page.getByText(/categorie : Nord/)).toBeVisible();

  await page.getByLabel("Effacer le filtre categorie").click();
  await expect(page.getByText(/categorie : Nord/)).toBeHidden();
  await expect(page.getByText(/Période :/)).toBeVisible();

  await chart.click({ position: { x: box.width * 0.3, y: box.height * 0.42 } });
  await page.getByRole("button", { name: "Tout effacer" }).click();
  await expect(page.getByText(/Période :/)).toBeHidden();
  await expect(page.getByText(/categorie : Nord/)).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 9 — non-régression : une app en interactions "manual" n'affiche
// jamais l'indicateur et le sélecteur ne filtre jamais rien.
// -------------------------------------------------------------------------
test("interactions manual: no indicator, select/slider never cross-filter", async ({ page }) => {
  await mockCore(page);

  await page.route("**/collections/analytics/schema", async (route) => {
    await route.fulfill({
      json: { collection: "analytics", pk: "id", geometry: null, fields: [{ name: "categorie", type: "string" }] },
    });
  });
  await page.route("**/collections/analytics/items*", async (route) => {
    await route.fulfill({ json: { type: "FeatureCollection", features: [
      { id: 1, properties: { categorie: "Nord" } },
      { id: 2, properties: { categorie: "Sud" } },
    ] } });
  });
  await page.route("**/collections/analytics/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "categorie", rows: [{ categorie: "Nord", value: 1 }, { categorie: "Sud", value: 1 }] } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "analytics", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Manual non-regression");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Sélecteur" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Champ du sélecteur").fill("categorie");
  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  // Interactions automatiques OFF — le défaut des nouvelles apps est "auto"
  // (cf. scénario 5), donc il faut décocher explicitement pour tester "manual".
  await page.getByLabel("Interactions automatiques (cross-filter)").uncheck();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible();
  // Le sélecteur est un composant entièrement piloté par AnalyticsContext (pas
  // d'état local) : en mode "manual", setCrossFilter est un no-op, donc la case
  // ne passe jamais à cochée après le clic — on utilise .click() (pas .check(),
  // qui échouerait sur l'assertion Playwright « la case doit finir cochée »).
  await page.getByLabel("Nord").click();
  await expect(page.getByLabel("Nord")).not.toBeChecked();
  await expect(page.getByRole("cell", { name: "Sud" })).toBeVisible(); // toujours visible : pas de filtrage
  // …et rien n'a été écrit dans AnalyticsContext : aucune chip d'indicateur
  // n'apparaît pour ce filtre, preuve que le canal automatique est resté inerte.
  await expect(page.getByLabel("Effacer le filtre categorie")).toHaveCount(0);
});

// -------------------------------------------------------------------------
// Scénario 10 (SP-14d) — menu « explorer » : « Voir les entités » montre les
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
  // est `.first()`, celui de la table `.last()`. Le tableau du tiroir est
  // rendu avant le GridCanvas dans AppRenderer (ExplorerDrawer précède
  // DataProvider/GridCanvas dans le JSX) : c'est donc toujours le premier
  // <table> du DOM tant que le tiroir est ouvert, distinct du tableau du
  // widget Table sous-jacent (également cross-filtré, d'où l'ambiguïté sans
  // ce scoping).
  const drawerTable = page.locator("table").first();
  await page.getByRole("button", { name: "Explorer" }).last().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(drawerTable.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(drawerTable.getByRole("cell", { name: "Sud" })).toBeHidden();
  await page.getByRole("button", { name: "Fermer le panneau" }).click();
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();

  // Ouvrir « Voir les entités » depuis le Graphique lui-même (l'origine du
  // clic) — reste filtré, contrairement au graphique qui s'affiche lui-même
  // sans filtre (design §4 : la requête synthétique du tiroir n'a jamais
  // l'id d'un widget réel).
  await page.getByRole("button", { name: "Explorer" }).first().click();
  await page.getByRole("button", { name: "Voir les entités" }).click();
  await expect(drawerTable.getByRole("cell", { name: "Nord" })).toBeVisible();
  await expect(drawerTable.getByRole("cell", { name: "Sud" })).toBeHidden();

  // Fermer via Échap (plutôt que la croix, déjà couvert plus haut) — l'app
  // sous-jacente et son cross-filter restent inchangés.
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Fermer le panneau" })).toBeHidden();
  await expect(page.getByRole("cell", { name: "Nord" })).toBeVisible();
});

// -------------------------------------------------------------------------
// Scénario 11 (SP-14d) — non-régression : une app `interactions: "manual"`
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
  await page.route("**/collections/analytics/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 3 }] } });
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
  await expect(page.getByLabel("Seuil critique atteint")).toBeVisible();
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

// -------------------------------------------------------------------------
// Scénario 16 (SP-14f) — entonnoir : le clic sur une étape croise-filtre une
// table sur le même dataset, comme les barres (2 valeurs égales → l'étape
// "Nord" (première ligne) reste en haut).
// -------------------------------------------------------------------------
test("a funnel click cross-filters a table on the same dataset (SP-14f)", async ({ page }) => {
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

  await createApp(page, "Funnel cross-filter");
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "analytics");
  await promoteLastSource(page, 2);

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("funnel");
  await page.getByLabel("Champ catégorie").fill("categorie");
  await page.getByLabel("Champ valeur").fill("valeur");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });

  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  // Funnel with 2 equal-value stages stacks them top/bottom — top band is "Nord"
  // (first stage). Measured empirically (pixel color sampling of the rendered
  // canvas): with a 6:4 widget grid cell, the chart's actual plotting area is a
  // narrow horizontal strip roughly mid-height (title/legend padding above and
  // below it), so a naive geometric quarter-height guess (0.25) misses the
  // shape entirely and lands on transparent canvas — 0.42 lands inside the
  // "Nord" trapezoid consistently (same fraction as the existing bar-chart
  // click test above, which uses the identical widget size).
  const topStage = { x: box.width * 0.5, y: box.height * 0.42 };
  const filteredReq = page.waitForRequest((r) => r.url().includes("/collections/analytics/items") && r.url().includes("categorie=Nord"));
  await chart.click({ position: topStage });
  await filteredReq;
  await expect(page.getByRole("cell", { name: "Sud" })).toBeHidden();
});

// -------------------------------------------------------------------------
// Scénario 17 (SP-14f) — fumée sankey/treemap/sunburst : les trois types
// rendent sans planter à partir d'une source statistiques à groupBy
// multi-champs, preuve de bout en bout (builder → /aggregate → EChart).
// Pas de clic : les positions pixel des rectangles/flux ne sont pas
// prévisibles (design note tâche 12), contrairement à un funnel/barres.
// -------------------------------------------------------------------------
test("sankey, treemap and sunburst render from a multi-field groupBy dataset (SP-14f)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/flows/schema", async (route) => {
    await route.fulfill({
      json: { collection: "flows", pk: "id", geometry: null,
        fields: [{ name: "origin", type: "string" }, { name: "destination", type: "string" }, { name: "amount", type: "number" }] },
    });
  });
  await page.route("**/collections/flows/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: ["origin", "destination"],
        rows: [
          { origin: "Paris", destination: "Lyon", value: 10 },
          { origin: "Paris", destination: "Marseille", value: 5 },
        ],
      },
    });
  });

  await createApp(page, "Sankey/Treemap/Sunburst smoke");
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Type de la source/).last().selectOption("statistics");
  await page.getByLabel(/Collection de la source/).last().fill("flows");
  await page.getByLabel(/Grouper par/).last().fill("origin,destination");
  await page.getByLabel(/Champ agrégé/).last().fill("amount");

  for (const [type, label] of [["sankey", "Flux (sankey)"], ["treemap", "Zones hiérarchiques (treemap)"], ["sunburst", "Soleil hiérarchique (sunburst)"]] as const) {
    await page.getByRole("button", { name: "Graphique" }).click();
    await page.getByLabel("Source de données").selectOption({ index: 1 });
    await page.getByLabel("Type de graphique").selectOption(type);
    if (type === "sankey") {
      await page.getByLabel("Champ source").fill("origin");
      await page.getByLabel("Champ cible").fill("destination");
    } else {
      await page.getByRole("button", { name: "+ Niveau" }).click();
      await page.getByLabel("Niveau 1", { exact: true }).fill("origin");
    }
    void label;
  }
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByTestId("echart").locator("canvas")).toHaveCount(3);
});

// -------------------------------------------------------------------------
// Scénario 18 (SP-14f) — histogramme : rend les classes calculées côté
// serveur et ne croise-filtre jamais au clic (filtrage par plage hors du
// modèle de cross-filter à valeur unique).
//
// Preuve à charge (task 12 review round 1) : un second widget Table réel,
// sur le MÊME dataset partagé que le graphique, cross-filter activé — pas
// seulement une absence de requête réseau avec rien d'abonné. La source du
// graphique est promue (comme la table) PUIS basculée en type
// "statistiques" : elle conserve ainsi le datasetId acquis par la
// promotion (DataSourcePanel ne le réinitialise pas au changement de type),
// donc `data.datasetId` reste défini côté graphique — si resolveClickFilter
// se trompait un jour pour "histogram", `setCrossFilter` serait bien émis
// et la table (même datasetId) le verrait. Le "Champ catégorie" est
// renseigné avec un champ réel ("city") : si le garde-fou
// `chartType === "histogram" → null` disparaissait de resolveClickFilter,
// le clic tomberait dans la branche générique et produirait un filtre
// `city=<label de la barre>` — observable par la table via le mock
// `/collections/pops/items*` (même mécanisme conditionnel que le mock
// `analytics/items*` du scénario funnel ci-dessus).
// -------------------------------------------------------------------------
test("a histogram renders binned data and never cross-filters on click (SP-14f)", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/pops/schema", async (route) => {
    await route.fulfill({
      json: { collection: "pops", pk: "id", geometry: null,
        fields: [{ name: "city", type: "string" }, { name: "pop", type: "number" }] },
    });
  });
  await page.route("**/collections/pops/aggregate", async (route) => {
    await route.fulfill({
      json: { categoryKey: "bucketIndex", rows: [
        { bucketIndex: 0, bucketStart: 0, bucketEnd: 5, count: 3 },
        { bucketIndex: 1, bucketStart: 5, bucketEnd: 10, count: 7 },
      ] },
    });
  });
  await page.route("**/collections/pops/items*", async (route) => {
    const city = new URL(route.request().url()).searchParams.get("city");
    const all = [
      { id: 1, properties: { city: "Paris", pop: 5 } },
      { id: 2, properties: { city: "Lyon", pop: 8 } },
    ];
    const features = city ? all.filter((f) => f.properties.city === city) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "pops", columns: {}, timeField: null, reactsToExtent: false } } },
    });
  });

  await createApp(page, "Histogram smoke");

  // Deux sources sur le même dataset partagé "pops" : une pour l'histogramme
  // (basculée en "Statistiques" après promotion), une pour la table qui
  // consomme réellement /items.
  await addFeaturesSource(page, "pops");
  await promoteLastSource(page, 1);
  await addFeaturesSource(page, "pops");
  await promoteLastSource(page, 2);

  await page.getByLabel(/Type de la source/).first().selectOption("statistics");
  await page.getByLabel(/Champ agrégé/).last().fill("pop");
  await page.getByLabel(/Nombre de classes/).last().fill("2");

  await page.getByRole("button", { name: "Graphique" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });
  await page.getByLabel("Type de graphique").selectOption("histogram");
  await page.getByLabel("Champ catégorie").fill("city");

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 2 });
  await page.getByLabel("Interactions automatiques (cross-filter)").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Paris" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Lyon" })).toBeVisible();

  const chart = page.getByTestId("echart");
  await expect(chart.locator("canvas")).toBeVisible();
  const box = await chart.boundingBox();
  if (!box) throw new Error("chart canvas has no bounding box");

  let sawFilteredItemsRequest = false;
  page.on("request", (r) => {
    if (r.url().includes("/collections/pops/items") && new URL(r.url()).searchParams.has("city")) sawFilteredItemsRequest = true;
  });
  // Click position verified empirically (not assumed), same technique as the
  // funnel scenario above: rendered this exact 2-bucket histogram (counts 3
  // and 7) in a real browser and sampled canvas pixels on a grid to map the
  // two bars. ECharts only dispatches its "click" event when the click lands
  // on an actual graphic element — a click on blank canvas never fires it at
  // all, which would make this test pass vacuously regardless of whether the
  // histogram guard in resolveClickFilter is correct. The naive geometric
  // center (x:0.5, y:0.5) actually lands in the empty gap BETWEEN the two
  // bars (confirmed by sampling: at y:0.5 the solid-fill pixels stop around
  // x:0.47 and resume around x:0.57) — it would never have exercised the
  // click handler at all. The second bucket's bar (count=7, the taller one)
  // renders as a solid fill from x:0.59–0.88 / y:0.40–0.50 of the canvas box,
  // a comfortable margin; x:0.72/y:0.45 sits well inside it.
  const secondBar = { x: box.width * 0.72, y: box.height * 0.45 };
  await chart.click({ position: secondBar });
  await page.waitForTimeout(300); // no debounce/refetch to await — proving nothing fires

  // Primary assertion: the table — a real consuming widget — still shows
  // every original row (it never narrowed), not just "no request was seen".
  await expect(page.getByRole("cell", { name: "Paris" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Lyon" })).toBeVisible();
  expect(sawFilteredItemsRequest).toBe(false);
});

# SP-3c — Bascule du shell sur le cœur (retrait de pg_featureserv) : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Le shell lit ses couches "feature" (sélecteur de couches carte, sources de données du builder) directement depuis le cœur GeoStudio au lieu de pg_featureserv, qui sort du compose — dernière sous-phase de SP-3, cf. [SP-3 — Collections & CRUD features](../specs/2026-07-09-sp3-collections-features-design.md) §6.

**Architecture:** `shell/src/api/itemClient.ts` reste le seul point de contact shell↔backend (règle CLAUDE.md n°1). Deux fonctions changent de cible : `fetchFeatureservSources` (liste des couches) devient `fetchCoreCollections` (`GET {coreUrl}/collections`) et `buildFeaturesUrl` (URL des items GeoJSON) pointe sur `{coreUrl}/collections/{id}/items` au lieu de `{featureservUrl}/collections/{id}/items.json`. Le reste du client (construction des filtres, agrégation statistique côté client, `Bearer` déjà en place pour les items) ne change pas — c'est une bascule de base URL, pas une réécriture.

**Tech Stack:** React 18 + TypeScript + Vitest + MSW (tests unitaires), Playwright (E2E, `VITE_AUTH_MODE=mock`), FastAPI (cœur — déjà livré en SP-3b, aucune modification backend dans ce plan).

## Global Constraints

- **Portée stricte** : ce plan couvre uniquement §6 de la spec SP-3 (bascule shell + démolition pg_featureserv). Les correctifs backend mineurs différés lors de la revue finale de SP-3b (voir `.superpowers/sdd/progress.md`, ex. `introspect` non catché sur les routes de lecture, `PUT` sans mapping `IntegrityError`→409) **ne font pas partie de ce plan** — ce sont des tâches backend, pas une bascule shell ; ils restent un backlog séparé (ne pas les traiter ici, ne pas les ignorer ailleurs).
- `itemClient.ts` (`shell/src/api/itemClient.ts`) est le sas (CLAUDE.md règle n°1) : tout changement de routage passe par lui, jamais par un composant.
- Compat filtres inchangée : les clés `STAT_KEYS` (`groupBy`, `split`, `agg`, `field`, `measures`) restent exclues côté shell avant construction de l'URL ; les autres clés passent triées par nom en query string, valeurs scalaires uniquement, entrées vides/nullish omises — comportement actuel de `buildFeaturesUrl`, ne pas le changer.
- Divergence de compat assumée par la spec : une clé de filtre inconnue renvoie `400` côté cœur (pg_featureserv l'ignorait silencieusement) — invisible pour le builder qui ne produit que des clés valides ; aucune garde supplémentaire à écrire côté shell.
- `Authorization: Bearer` déjà envoyé pour les items (`queryDataSource`/`featuresUrl`) — ne pas y toucher. À **ajouter** pour `fetchCoreCollections` (absent aujourd'hui côté featureserv) : `GET /collections` du cœur utilise `get_current_user_optional`, donc sans token le sélecteur de couches ne verrait que les collections publiques du tenant par défaut — avec le token de l'utilisateur connecté, il voit aussi ses collections privées/partagées, cohérent avec `can()`.
- CRS84/bbox : le shell ne construit jamais de paramètre `bbox` aujourd'hui (`buildFeaturesUrl` ne l'émet pas) — aucun changement requis, hors périmètre.
- Les 13 specs E2E existantes restent vertes (CLAUDE.md). Seul `shell/e2e/mocks.ts` doit changer (routes) — ne pas modifier les fichiers `*.spec.ts`, qui pilotent l'UI et ne connaissent aucune URL de service.
- `docker compose` reste une stack **partagée** avec d'autres sessions de travail actives (voir `.worktrees/sp1a-socle-core`, `.worktrees/sp1b-items`) : ne jamais faire `docker compose down`/`up` sur la stack réelle depuis ce plan. Valider le YAML avec `docker compose config` (parse + résolution des services, aucun conteneur touché), pas avec `up`.
- TDD systématique ; commits conventional en français ; code/identifiants en anglais ; `npm run test`, `npm run build` (`tsc --noEmit` + vite build) verts à la fin de chaque tâche.

---

## Task 1: Sélecteur de couches — `fetchCoreCollections` remplace `fetchFeatureservSources`

**Files:**
- Modify: `shell/src/api/types.ts:62` (union `LayerSource.service`)
- Modify: `shell/src/api/itemClient.ts:177-191` (fonction), `:284-296` (`listLayerSources`)
- Modify: `shell/src/map/LayerPicker.test.tsx:12,46` (fixture forcée par le type)
- Modify: `shell/src/api/itemClient.test.ts:1-12` (helper `makeClient` — retrait de `featureservUrl` de l'objet passé, la clé disparaîtra du type en Task 2 mais l'appel garde `martinUrl`/`coreUrl`), `:114-168` (3 tests `listLayerSources`)

**Interfaces:**
- Produces: `LayerSource.service: "martin" | "core"` (remplace `"featureserv"`) — type utilisé par `LayerPicker.tsx` (clé React uniquement, aucun branchement dessus, donc aucun risque de régression comportementale).
- Consumes: rien de nouveau — `coreUrl` et `getToken` existent déjà dans les opts de `createItemClient`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts`, remplacer les 3 tests `listLayerSources` (actuellement lignes 114-168) par :

```ts
test("listLayerSources aggregates Martin vector sources and core collections", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://martin.test/catalog", () =>
      HttpResponse.json({
        tiles: {
          communes: { content_type: "application/x-protobuf", description: "Communes" },
          routes: { content_type: "application/x-protobuf" },
        },
      }),
    ),
    http.get("https://core.test/collections", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({
        collections: [{ id: "public.parcs", title: "Parcs" }],
      });
    }),
  );
  const sources = await makeClient("abc").listLayerSources();
  expect(auth).toBe("Bearer abc");
  const martin = sources.find((s) => s.id === "communes");
  expect(martin).toMatchObject({
    title: "Communes",
    service: "martin",
    kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}",
    sourceLayer: "communes",
  });
  // Martin source without a description falls back to its id for the title.
  expect(sources.find((s) => s.id === "routes")?.title).toBe("routes");
  const feature = sources.find((s) => s.id === "public.parcs");
  expect(feature).toMatchObject({
    title: "Parcs",
    service: "core",
    kind: "feature",
    url: "https://core.test/collections/public.parcs/items",
  });
});

test("listLayerSources still returns one service when the other fails", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [{ id: "public.parcs", title: "Parcs" }] }),
    ),
  );
  const sources = await makeClient().listLayerSources();
  expect(sources).toHaveLength(1);
  expect(sources[0].service).toBe("core");
});

test("listLayerSources throws when both services fail", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => new HttpResponse(null, { status: 500 })),
    http.get("https://core.test/collections", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(makeClient().listLayerSources()).rejects.toThrow();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t listLayerSources`
Expected: FAIL — `https://core.test/collections` n'a pas de handler MSW par défaut (aucune requête ne l'atteint, la vraie implémentation appelle encore `https://featureserv.test/collections.json`), donc `auth` reste `null` et `feature`/`sources[0].service` ne matchent pas `"core"`.

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, ligne 62 :
```ts
  service: "martin" | "core";
```

Dans `shell/src/api/itemClient.ts`, remplacer la fonction (lignes 177-191) :
```ts
  async function fetchCoreCollections(): Promise<LayerSource[]> {
    const token = getToken();
    const res = await fetch(`${coreUrl}/collections`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "core" as const,
      kind: "feature" as const,
      url: `${coreUrl}/collections/${c.id}/items`,
    }));
  }
```

Et dans `listLayerSources` (lignes 284-296), remplacer l'appel :
```ts
    async listLayerSources(): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(),
        fetchCoreCollections(),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },
```

Dans `shell/src/map/LayerPicker.test.tsx`, ligne 12 : `service: "featureserv"` → `service: "core"`. Ligne 46, renommer le test `"emits a feature MapLayer for a featureserv source"` → `"emits a feature MapLayer for a core source"` (le corps du test ne change pas).

Dans `shell/src/api/itemClient.test.ts`, ligne 9 (helper `makeClient`), retirer `featureservUrl: "https://featureserv.test",` de l'objet passé à `createItemClient` (le champ disparaît du type accepté par `createItemClient` en Task 2 — le retirer ici évite un aller-retour ; l'objet reste valide en TypeScript tant qu'il ne fournit pas de propriété inconnue à un type qui ne l'a pas encore, ce qui n'est vérifié qu'à l'appel : ce retrait est sans risque dès cette étape).

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/map/LayerPicker.test.tsx`
Expected: PASS (tous les tests des deux fichiers, y compris ceux non touchés par cette tâche)

Run: `cd shell && npm run build`
Expected: PASS (aucune erreur TypeScript)

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts src/map/LayerPicker.test.tsx
git commit -m "feat(shell): sélecteur de couches — collections du cœur au lieu de pg_featureserv"
```

---

## Task 2: Items de features — `buildFeaturesUrl`/`featuresUrl`/`queryDataSource` sur le cœur

**Files:**
- Modify: `shell/src/api/itemClient.ts:34-47` (`buildFeaturesUrl`), `:135-141` (opts de `createItemClient`), `:372-374` et `:376-394` (`featuresUrl`/`queryDataSource`)
- Modify: `shell/src/config.ts:4,33` (retrait de `featureservUrl`)
- Modify: `shell/src/App.tsx:21` (retrait du câblage)
- Modify: `shell/src/builder/DataSourcePanel.tsx:18` (littéral par défaut d'une nouvelle source)
- Modify: `shell/src/api/itemClient.test.ts:5-12` (helper), `:277-332` (features), `:334-449` (statistiques)

**Interfaces:**
- Consumes: `LayerSource.service: "core"` (Task 1) — pas de dépendance directe, mentionné pour cohérence.
- Produces: `createItemClient(opts: { coreUrl: string; martinUrl?: string; getToken: () => string | undefined })` — le champ `featureservUrl` disparaît définitivement de la surface publique du client. Aucune tâche ultérieure n'en dépend (dernière tâche à toucher `itemClient.ts` dans ce plan).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts`, remplacer le bloc lignes 277-332 par :

```ts
test("featuresUrl builds the core items url", () => {
  const url = makeClient().featuresUrl({ id: "d", type: "features", service: "core", layer: "public.parcs", query: {} });
  expect(url).toBe("https://core.test/collections/public.parcs/items");
});

test("queryDataSource maps a feature collection to records", async () => {
  server.use(
    http.get("https://core.test/collections/public.parcs/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { type: "Feature", id: 1, properties: { nom: "Parc A" }, geometry: { type: "Point", coordinates: [1, 2] } },
          { type: "Feature", properties: { nom: "Parc B" }, geometry: null },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({ id: "d", type: "features", service: "core", layer: "public.parcs", query: {} });
  expect(records).toHaveLength(2);
  expect(records[0]).toMatchObject({ id: 1, properties: { nom: "Parc A" } });
  // Missing feature id falls back to the index.
  expect(records[1].id).toBe(1);
});

test("queryDataSource returns inline records for a static source", async () => {
  const records = await makeClient().queryDataSource({
    id: "s", type: "static", service: "", layer: "",
    query: { records: [{ id: "a", properties: { v: 1 } }] },
  });
  expect(records).toEqual([{ id: "a", properties: { v: 1 } }]);
});

test("queryDataSource throws when the feature request fails", async () => {
  server.use(
    http.get("https://core.test/collections/x/items", () => new HttpResponse(null, { status: 500 })),
  );
  await expect(
    makeClient().queryDataSource({ id: "d", type: "features", service: "core", layer: "x", query: {} }),
  ).rejects.toThrow();
});

test("featuresUrl appends scalar query entries as sorted filter params", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "core", layer: "parcs",
    query: { nom: "Parc A", limit: 10 },
  });
  expect(url).toBe("https://core.test/collections/parcs/items?limit=10&nom=Parc+A");
});

test("featuresUrl omits empty/nullish query entries", () => {
  const url = makeClient().featuresUrl({
    id: "d", type: "features", service: "core", layer: "parcs",
    query: { nom: "", ville: undefined as unknown as string },
  });
  expect(url).toBe("https://core.test/collections/parcs/items");
});
```

Puis remplacer le bloc lignes 334-449 (tests statistiques) par :

```ts
test("queryDataSource aggregates a statistics source by count per group", async () => {
  server.use(
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", pop: 10 } },
          { id: 2, properties: { region: "Nord", pop: 20 } },
          { id: 3, properties: { region: "Sud", pop: 5 } },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", agg: "count" },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 2 } },
    { id: "Sud", properties: { region: "Sud", value: 1 } },
  ]);
});

test("queryDataSource supports sum/avg/min/max aggregations per group", async () => {
  const feats = {
    type: "FeatureCollection",
    features: [
      { id: 1, properties: { region: "Nord", pop: 10 } },
      { id: 2, properties: { region: "Nord", pop: 20 } },
      { id: 3, properties: { region: "Sud", pop: 6 } },
    ],
  };
  const run = async (agg: string) => {
    server.use(
      http.get("https://core.test/collections/villes/items", () => HttpResponse.json(feats)),
    );
    return makeClient().queryDataSource({
      id: "s", type: "statistics", service: "core", layer: "villes",
      query: { groupBy: "region", agg, field: "pop" },
    });
  };
  expect(await run("sum")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 30 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("avg")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 15 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("min")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 10 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
  expect(await run("max")).toEqual([
    { id: "Nord", properties: { region: "Nord", value: 20 } },
    { id: "Sud", properties: { region: "Sud", value: 6 } },
  ]);
});

test("queryDataSource pivots a statistics source into one column per split value", async () => {
  server.use(
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", annee: "2025", pop: 10 } },
          { id: 2, properties: { region: "Nord", annee: "2026", pop: 12 } },
          { id: 3, properties: { region: "Sud", annee: "2025", pop: 5 } },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop" },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", "2025": 10, "2026": 12 } },
    { id: "Sud", properties: { region: "Sud", "2025": 5, "2026": 0 } },
  ]);
});

test("queryDataSource produces one wide column per measure", async () => {
  server.use(
    http.get("https://core.test/collections/villes/items", () =>
      HttpResponse.json({
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", pop: 10, rev: 4 } },
          { id: 2, properties: { region: "Nord", pop: 20, rev: 8 } },
        ],
      }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: {
      groupBy: "region",
      measures: [
        { field: "pop", agg: "sum", label: "Population" },
        { field: "rev", agg: "avg" },
      ],
    },
  });
  expect(records).toEqual([
    { id: "Nord", properties: { region: "Nord", Population: 30, avg_rev: 6 } },
  ]);
});

test("featuresUrl strips reserved statistics keys but keeps filter params", () => {
  const url = makeClient().featuresUrl({
    id: "s", type: "statistics", service: "core", layer: "villes",
    query: { groupBy: "region", split: "annee", agg: "sum", field: "pop", annee_filtre: 2026 },
  });
  expect(url).toBe("https://core.test/collections/villes/items?annee_filtre=2026");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL sur tous les tests remplacés — l'implémentation actuelle construit encore des URLs `https://featureserv.test/.../items.json`, qui ne matchent aucun handler MSW enregistré ci-dessus (MSW retourne 404 par défaut pour une requête sans handler, donc `res.ok` est `false`).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/itemClient.ts`, remplacer `buildFeaturesUrl` (lignes 34-47) :
```ts
function buildFeaturesUrl(coreUrl: string, source: DataSource): string {
  const base = `${coreUrl}/collections/${source.layer}/items`;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(source.query).sort(([a], [b]) => a.localeCompare(b))) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      params.set(k, String(v));
    }
  }
  const qs = params.toString();
  return qs ? `${base}?${qs}` : base;
}
```
(`coreUrl` est une variable de configuration obligatoire — `loadConfig` lève si `VITE_CORE_URL` est absent — donc la garde `if (!featureservUrl) throw` de l'ancienne version, nécessaire parce que `featureservUrl` était optionnel, disparaît : elle n'a plus de raison d'être.)

Dans les opts de `createItemClient` (lignes 135-141) :
```ts
export function createItemClient(opts: {
  coreUrl: string;
  martinUrl?: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { coreUrl, martinUrl, getToken } = opts;
```

Dans les méthodes `featuresUrl`/`queryDataSource` (lignes 372-374 et 376-394), remplacer les deux appels `buildFeaturesUrl(featureservUrl, source)` par `buildFeaturesUrl(coreUrl, source)` :
```ts
    featuresUrl(source: DataSource): string {
      return buildFeaturesUrl(coreUrl, source);
    },

    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      if (source.type === "static") {
        return (source.query.records as DataRecord[] | undefined) ?? [];
      }
      const token = getToken();
      const res = await fetch(buildFeaturesUrl(coreUrl, source), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${source.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      const records = (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
      return source.type === "statistics" ? aggregateRecords(records, source.query) : records;
    },
```

Dans `shell/src/config.ts`, retirer `featureservUrl: string;` (ligne 4) du type `AppConfig`, et retirer `featureservUrl: env.VITE_FEATURESERV_URL ?? "",` (ligne 33) du retour de `loadConfig`.

Dans `shell/src/App.tsx`, retirer la ligne 21 `featureservUrl: config.featureservUrl,` de l'appel à `createItemClient`.

Dans `shell/src/builder/DataSourcePanel.tsx`, ligne 18 : `service: "featureserv"` → `service: "core"` (valeur par défaut d'une source nouvellement ajoutée — `DataSource.service` reste un `string` libre, ce changement est cosmétique mais évite qu'une source neuve porte un nom de service qui n'existe plus).

Dans `shell/src/api/itemClient.test.ts`, dans le helper `makeClient()` (haut de fichier), retirer `featureservUrl: "https://featureserv.test",` de l'objet passé à `createItemClient` — c'est la dernière tâche à référencer ce champ (Task 1 l'avait délibérément laissé en place car les tests de features/statistiques, réécrits seulement dans cette tâche, en dépendaient encore ; voir la revue de Task 1 dans le ledger).

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run`
Expected: PASS — 56 fichiers, 277 tests (ce plan renomme et modifie des tests existants, il n'en ajoute ni n'en retire aucun ; le compte total reste inchangé)

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/api/itemClient.ts src/api/itemClient.test.ts src/config.ts src/App.tsx src/builder/DataSourcePanel.tsx
git commit -m "feat(shell): items de features — bascule sur le cœur, retrait de featureservUrl"
```

---

## Task 3: E2E — mocks re-câblés sur les routes du cœur

**Files:**
- Modify: `shell/e2e/mocks.ts:154-188`
- Modify: `shell/.env.e2e:4` (suppression de la ligne)
- Modify: `shell/playwright.config.ts:14` (suppression de la ligne — miroir de `.env.e2e` pour le serveur de preview lancé par Playwright, oublié lors de la rédaction initiale de ce plan)

**Interfaces:**
- Consumes: rien de `itemClient.ts` — les mocks Playwright interceptent au niveau HTTP, indépendamment de l'implémentation du client. Cette tâche vérifie que les URLs produites par Tasks 1-2 (`{VITE_CORE_URL}/collections`, `{VITE_CORE_URL}/collections/{id}/items`) sont bien celles interceptées.

- [ ] **Step 1: Écrire (adapter) le mock — c'est la "spécification" de cette tâche**

Dans `shell/e2e/mocks.ts`, remplacer le bloc lignes 154-188 par :

```ts
  // Cœur OGC API collections — return empty list (no feature layers needed
  // beyond the two below).
  await page.route("**/collections", async (route) => {
    await route.fulfill({
      json: { collections: [] },
    });
  });

  // Cœur items for the "villes" collection — a statistics source aggregates
  // these client-side (groupBy region, split annee → 2 series).
  await page.route("**/collections/villes/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", annee: "2025", pop: 10 } },
          { id: 2, properties: { region: "Nord", annee: "2026", pop: 12 } },
          { id: 3, properties: { region: "Sud", annee: "2025", pop: 5 } },
          { id: 4, properties: { region: "Sud", annee: "2026", pop: 7 } },
        ],
      },
    });
  });

  // Cœur items endpoint for the "parcs" collection — filters by the `nom`
  // query param so setFilter can be observed end-to-end.
  await page.route("**/collections/parcs/items*", async (route) => {
    const url = new URL(route.request().url());
    const nom = url.searchParams.get("nom");
    const all = [
      { id: 1, properties: { nom: "Parc du Test" } },
      { id: 2, properties: { nom: "Bois Test" } },
    ];
    const features = nom ? all.filter((f) => f.properties.nom === nom) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
```

Dans `shell/.env.e2e`, retirer la ligne `VITE_FEATURESERV_URL=https://featureserv.test`.

Dans `shell/playwright.config.ts`, dans le bloc `webServer.env`, retirer la ligne `VITE_FEATURESERV_URL: "https://featureserv.test",` (ce fichier fixe les variables d'environnement du serveur de preview que Playwright lance lui-même — distinct de `.env.e2e`, qui ne s'applique qu'à `npm run dev`/`vite`).

- [ ] **Step 2: Lancer la suite E2E, vérifier l'échec attendu avant tout autre changement**

Ce mock est déjà la cible finale (pas de cycle rouge séparé ici : les fichiers `*.spec.ts` ne changent pas, seul le mock change, et Tasks 1-2 ont déjà basculé le client sur le cœur). Lancer directement :

Run: `cd shell && npm run e2e`
Expected à ce stade (avant cette tâche, sur l'état d'avant Step 1) : `actions.spec.ts`, `chart.spec.ts`, `data-widget.spec.ts` échouent — le client interroge `{coreUrl}/collections/villes/items` mais l'ancien mock n'intercepte que `**/collections/villes/items.json*`. Si vous exécutez cette tâche à la suite de Task 2 (le cas normal), constatez cet échec en lançant `npm run e2e` une fois avant d'éditer `mocks.ts`, pour confirmer que c'est bien le mock — et non une régression du client — qui est en cause.

- [ ] **Step 3: Confirmer le succès après l'édition du Step 1**

Run: `cd shell && npm run e2e`
Expected: PASS — 13 specs vertes.

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/mocks.ts .env.e2e
git commit -m "test(shell): e2e — mocks re-câblés sur les routes collections/items du cœur"
```

---

## Task 4: Démolition — retrait de pg_featureserv du compose et de la doc

**Files:**
- Modify: `docker-compose.yml` (retrait du service `pg-featureserv`)
- Modify: `README.md:33,68`
- Modify: `CLAUDE.md` (bloc Commandes + section État)

**Interfaces:** aucune — tâche documentaire/infra, pas de code applicatif.

- [ ] **Step 1: Retirer le service du compose**

Dans `docker-compose.yml`, retirer entièrement le bloc :
```yaml
  pg-featureserv:
    image: pramsey/pg_featureserv:latest
    environment:
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    ports:
      - "9000:9000"
    networks: [gis-net]
    depends_on:
      pgbouncer:
        condition: service_started
```

- [ ] **Step 2: Valider le YAML sans toucher à la stack partagée**

Run: `docker compose config --quiet`
Expected: aucune sortie, code de sortie 0 (YAML valide, graphe de services résoluble sans `pg-featureserv`). **Ne pas lancer `docker compose up`/`down`** — la stack est partagée avec d'autres sessions de travail actives sur ce host.

- [ ] **Step 3: Mettre à jour la documentation**

Dans `README.md`, ligne 33 :
```
- **`docker-compose.yml`** — la stack de dev : PostGIS, PgBouncer, MinIO, Martin,
  TiTiler, Keycloak, Traefik, cœur, shell. GeoNode, Superset, Redis et
  pg_featureserv sont sortis (jalons M1 et SP-3c).
```
Ligne 68, retirer la ligne du tableau :
```
| pg_featureserv (OGC API Features) | http://localhost:9000 |
```

Dans `CLAUDE.md`, dans le bloc Commandes :
```
docker compose up -d # nécessite .env (cf. .env.example) ; 9 services
                      # (postgis, pgbouncer, minio, martin, titiler,
                      # core, keycloak, shell, traefik)
```

Dans la section « État au 2026-07-11 », le paragraphe SP-3b se termine
actuellement par la phrase « **Prochain chantier : SP-3c** (bascule du shell
sur le cœur, retrait de pg_featureserv). ». Remplacer cette phrase finale (et
elle seule — le reste du paragraphe SP-3b ne change pas) par un nouveau
paragraphe SP-3c, de sorte que le texte devienne :
```
- **SP-3b livré** (2026-07-11) : OGC API Features Part 1+4 dans le cœur
  (landing, conformance, items GeoJSON — bbox, filtres, pagination avec
  liens —, POST/PUT/DELETE validés par schéma, audités), chaque requête
  métier sous `rls_scope` (rôle `gis_rls` + GUC tenant, validé à travers
  PgBouncer par `scripts/spike_pgbouncer_rls.py`).
- **SP-3c livré** (2026-07-11) : le shell lit ses couches "feature" (sélecteur
  de couches carte, sources de données du builder) directement depuis le
  cœur (`GET /collections`, `GET/POST/PUT/DELETE /collections/{id}/items`) ;
  `pg_featureserv` retiré du compose (10→9 services) et de toute la doc ;
  les 13 specs E2E restent vertes sur des mocks re-câblés. **SP-3 est
  clos.** Prochain chantier : **SP-4** (formulaires dans le builder, spec
  déjà écrite —
  `docs/superpowers/specs/2026-07-10-sp4-formulaires-builder-design.md`).
```

- [ ] **Step 4: Vérifier qu'aucune référence ne subsiste dans les fichiers vivants**

Run: `grep -rln "featureserv\|FEATURESERV" docker-compose.yml README.md CLAUDE.md shell/.env* shell/playwright.config.ts shell/src shell/e2e`
Expected: aucune sortie (0 résultat). Les mentions dans `docs/vision/`, `docs/archive/`, `docs/superpowers/specs/2026-07-09-sp3-collections-features-design.md` et les plans datés antérieurs sont des documents historiques — ne pas les modifier.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml README.md CLAUDE.md
git commit -m "chore: retrait de pg_featureserv du compose et de la documentation (SP-3c)"
```

---

## Couverture spec → tâches (auto-vérification)

- §6 "`itemClient.ts` : `fetchFeatureservSources` → `fetchCoreCollections`" → Task 1.
- §6 "`buildFeaturesUrl` pointe sur le cœur" → Task 2.
- §6 "`types.ts` : `LayerSource.service: "martin" | "core"`" → Task 1.
- §6 "`DataSource.service` idem (valeur `"featureserv"` migrée...)" → non applicable : `DataSource.service` est un `string` libre non branché par aucune logique (vérifié — `buildFeaturesUrl`/`queryDataSource` ne lisent jamais `source.service`, seul `source.layer`/`source.query` comptent) ; aucune migration de configs existantes n'est nécessaire, une valeur `"featureserv"` déjà stockée continue de fonctionner sans effet. Seul le littéral par défaut d'une *nouvelle* source change (Task 2, `DataSourcePanel.tsx`), par cohérence.
- §6 "`config.ts`/`App.tsx`/`.env*` : suppression de `VITE_FEATURESERV_URL`" → Task 2 (config.ts/App.tsx) + Task 3 (`.env.e2e`).
- §6 "E2E : `mocks.ts` remplace... les 13 restent vertes" → Task 3.
- §6 "`docker-compose.yml` : retrait de `pg-featureserv`... README/CLAUDE.md mis à jour" → Task 4.
- §9 critère "Après SP-3c : `docker compose up` sans pg_featureserv ; les 13 specs E2E passent ; ... zéro occurrence de `VITE_FEATURESERV_URL`" → Task 4 Step 2/4 + Task 3 Step 3.
- §9 autres critères (CRUD via l'API OGC, `GET /collections/{cid}/schema`, visibilité Martin, `audit_log`, RLS) → déjà couverts et testés par SP-3b, aucune tâche de ce plan ne les retouche.

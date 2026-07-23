# SP-4a — Widget Formulaire (création seule) : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un nouveau widget « Formulaire » dans le builder, capable de rendre un formulaire de saisie depuis le schéma introspecté d'une collection (`GET /collections/{id}/schema`, déjà livré par SP-3a), avec un panneau d'overrides visuel (label, ordre, masquage, validation par champ), une validation client + serveur cohérente, et une action d'écriture (`POST /collections/{id}/items`, déjà livré par SP-3b) — première sous-phase de SP-4, cf. [SP-4 — Formulaires dans le builder](../specs/2026-07-10-sp4-formulaires-builder-design.md) §1.

**Architecture:** Un widget de plus dans le registre existant (`shell/src/builder/registry.ts`), suivant exactement le patron déjà en place pour `list`/`table`/`map` (`registerWidget({ type, label, defaultProps, defaultSize, events, actions, PropsPanel, Component })`, `shell/src/builder/widgets/data.tsx`/`mapWidget.tsx`). Le schéma de collection est introspecté une seule fois, **au moment du design** dans le panneau de propriétés (`PropsPanel`), et le résultat (liste de champs fusionnée avec les overrides) est figé dans `props.fields` du `WidgetItem` — le composant en mode `runtime`/`preview` ne réinterroge jamais le schéma, il lit `props.fields` comme n'importe quel autre widget lit ses `props` (cohérent avec la règle CLAUDE.md n°2 : un objet de plateforme est un document déclaratif, pas de logique cachée). L'écriture passe par trois nouvelles méthodes de `ItemClient` (`getCollectionSchema`, `createFeature`, et — posées mais pas encore câblées à un widget, cf. spec §1 — `updateFeature`/`deleteFeature`), qui parlent au cœur déjà livré par SP-3b (`POST/PUT/DELETE /collections/{cid}/items[/{fid}]`).

**Tech Stack:** React 19 + TypeScript + Vitest + Testing Library + MSW (tests unitaires), `@tanstack/react-query` (déjà utilisé partout dans le shell), FastAPI (cœur — **aucune modification** dans ce plan, tout le contrat serveur consommé ici est déjà livré par SP-3a/SP-3b).

## Global Constraints

- **`itemClient.ts` (`shell/src/api/itemClient.ts`) est le sas** (CLAUDE.md règle n°1) : toute nouvelle méthode d'écriture/lecture passe par lui, jamais par un composant appelant `fetch` directement.
- **Aucun changement backend.** Toutes les routes consommées (`GET /collections/{id}/schema`, `POST/PUT/DELETE /collections/{id}/items[/{fid}]`) sont déjà livrées et testées côté cœur (SP-3a/SP-3b) — vérifié directement dans `core/app/collections/routes.py`, `core/app/collections/schema_json.py`, `core/app/features/routes.py`, `core/app/features/validation.py`. Ce plan est un chantier front pur.
- **Le payload d'écriture est un GeoJSON Feature complet**, pas juste `{properties, geometry}` : `core/app/features/validation.py` rejette tout payload dont `feature.get("type") != "Feature"` (`_err("", "invalid_feature", ...)`). Toute méthode `createFeature`/`updateFeature` du client envoie donc `{ type: "Feature", properties: {...}, geometry: ... | null }`.
- **FastAPI enveloppe les erreurs sous `{"detail": ...}`** (aucun exception handler custom dans `core/app/main.py`) : un 400 renvoie `{"detail": {"errors": [{field,code,message}, ...]}}` (`core/app/features/routes.py:70`, `_validation_error`), un 403/404/409 renvoie `{"detail": "<message texte>"}`. Le client doit lire `body.detail.errors` pour un 400 et `body.detail` (string) pour les autres échecs.
- **Schéma introspecté au design, jamais au runtime.** `GET /collections/{id}/schema` n'est appelé que dans le `PropsPanel` du Formulaire, une fois, via un bouton explicite « Charger les champs du schéma » (pas de `useEffect` implicite qui écraserait un travail en cours) ; le résultat fusionné avec les overrides est stocké dans `props.fields` (+ `props.geometryType`). Si la collection change de schéma après coup, `props.fields` ne se resynchronise pas automatiquement — simplification assumée pour SP-4a, non testée, à documenter si un besoin réel apparaît.
- **Validation client, portée volontairement restreinte** : `requis` s'applique à tout type ; `min`/`max` uniquement aux types `integer`/`number` ; `motif` (regex) uniquement au type `string`. C'est une lecture stricte de la formulation spec §2 (« requis/min-max/motif ») qui évite d'inventer une sémantique min/max pour les chaînes ou les dates (hors périmètre, non demandé).
- **Géométrie : point uniquement dans ce plan.** La spec (§2, §9) autorise explicitement le repli sur point-seul si l'effort déborde, et de reporter ligne/polygone à SP-4b. Ce plan implémente ce repli directement : seul un `geometry.type === "Point"` (introspecté via `schema.geometry`) affiche deux champs numériques longitude/latitude ; toute autre géométrie (ligne, polygone, ou absente) n'affiche aucun champ géométrie et soumet `geometry: null` — accepté sans erreur par `validate_feature` (aucune règle de géométrie obligatoire côté serveur, vérifié dans `core/app/features/validation.py`).
- **Rafraîchissement après écriture : invalidation large, volontaire.** Après un `createFeature` réussi, le widget invalide le préfixe `["datasource"]` entier de TanStack Query (`DataProvider`, `shell/src/builder/DataContext.tsx`, clé `["datasource", s.id, merged.query]`) — pas seulement la collection concernée. La spec §5 exige « toutes les data sources de la même collection, sur tous les widgets » et interdit le cache partiel/l'optimistic update ; une invalidation plus large que nécessaire satisfait cette exigence sans introduire de logique de correspondance collection↔data source. Assumé comme simplification, pas un oubli.
- **Pas de bibliothèque de glisser-déposer.** Aucune dépendance drag-and-drop n'existe dans `shell/package.json` ; le réordonnancement des champs (spec §2, « ordre par glisser-déposer ») utilise l'API HTML5 native (`draggable`, `onDragStart`/`onDragOver`/`onDrop`), sans nouvelle dépendance.
- Docs et messages utilisateur en français (labels, erreurs) ; code/identifiants en anglais (CLAUDE.md).
- TDD systématique ; commits conventional en français ; `cd shell && npm run test` et `npm run build` (`tsc --noEmit` + vite build) verts à la fin de chaque tâche.
- **Hors périmètre de ce plan** (différé à SP-4b/SP-4c par la spec §1) : édition depuis sélection (`loadRecord`, émission `itemSelected` par Table/Carte), câblage `updateFeature`/`deleteFeature` à un widget, template galerie « Application de saisie », spec E2E Playwright. Ces méthodes sont *ajoutées* à `ItemClient` dans ce plan (Task 1, cf. spec §1 : « Nouvelles méthodes... posées ici ») mais restent non appelées par le widget Formulaire.

---

## Task 1: `ItemClient` — schéma de collection + écriture de features

**Files:**
- Modify: `shell/src/api/types.ts:67` (nouveaux types, insérés juste après `LayerSource`), `:69-88` (interface `ItemClient`)
- Modify: `shell/src/api/itemClient.ts:32` (nouvelle classe d'erreur + helper, insérés après `STAT_KEYS`), `:372-394` (fin de l'objet retourné par `createItemClient`, ajout des 4 nouvelles méthodes)
- Modify: `shell/src/api/itemClient.test.ts` (ajout en fin de fichier, après la ligne 548)

**Interfaces:**
- Produces: `ItemClient.getCollectionSchema(collectionId): Promise<CollectionSchema>`, `.createFeature(collectionId, feature): Promise<{id: string|number}>`, `.updateFeature(collectionId, fid, feature): Promise<void>`, `.deleteFeature(collectionId, fid): Promise<void>` ; types `CollectionSchema`, `CollectionSchemaField`, `CollectionFieldType`, `FieldError`, `GeoJSONFeatureInput` (tous exportés depuis `types.ts`) ; classe `FeatureValidationError` (exportée depuis `itemClient.ts`, porte `errors: FieldError[]`). Tasks 3-7 consomment ces méthodes et types.
- Consumes: rien de nouveau — `coreUrl`/`getToken` existent déjà dans les opts de `createItemClient`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts`, modifier l'import existant (ligne 3) pour ajouter `FeatureValidationError` :

```ts
import { createItemClient, FeatureValidationError } from "./itemClient";
```

Puis ajouter en fin de fichier :

```ts
test("getCollectionSchema returns the introspected fields", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/schema", () =>
      HttpResponse.json({
        collection: "incidents",
        pk: "id",
        geometry: { column: "geom", type: "Point", srid: 4326 },
        fields: [
          { name: "titre", type: "string", required: true, maxLength: 120 },
          { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
          { name: "nb_victimes", type: "integer", required: false },
        ],
      }),
    ),
  );
  const schema = await makeClient().getCollectionSchema("incidents");
  expect(schema.geometry).toEqual({ column: "geom", type: "Point", srid: 4326 });
  expect(schema.fields).toHaveLength(3);
  expect(schema.fields[0]).toEqual({ name: "titre", type: "string", required: true, maxLength: 120 });
});

test("createFeature sends a GeoJSON Feature with the bearer token and returns the new id", async () => {
  let auth: string | null = null;
  let body: unknown;
  server.use(
    http.post("https://core.test/collections/incidents/items", async ({ request }) => {
      auth = request.headers.get("authorization");
      body = await request.json();
      return HttpResponse.json({ id: 42 }, { status: 201 });
    }),
  );
  const result = await makeClient("abc").createFeature("incidents", {
    type: "Feature",
    properties: { titre: "Fuite d'eau" },
    geometry: null,
  });
  expect(auth).toBe("Bearer abc");
  expect(body).toEqual({ type: "Feature", properties: { titre: "Fuite d'eau" }, geometry: null });
  expect(result).toEqual({ id: 42 });
});

test("createFeature throws FeatureValidationError with field errors on 400", async () => {
  server.use(
    http.post("https://core.test/collections/incidents/items", () =>
      HttpResponse.json(
        { detail: { errors: [{ field: "titre", code: "missing_required", message: "'titre' is required" }] } },
        { status: 400 },
      ),
    ),
  );
  const err = await makeClient()
    .createFeature("incidents", { type: "Feature", properties: {}, geometry: null })
    .catch((e) => e);
  expect(err).toBeInstanceOf(FeatureValidationError);
  expect((err as FeatureValidationError).errors).toEqual([
    { field: "titre", code: "missing_required", message: "'titre' is required" },
  ]);
});

test("createFeature throws a plain Error with the server message on 403", async () => {
  server.use(
    http.post("https://core.test/collections/incidents/items", () =>
      HttpResponse.json({ detail: "collection is not editable" }, { status: 403 }),
    ),
  );
  await expect(
    makeClient().createFeature("incidents", { type: "Feature", properties: {}, geometry: null }),
  ).rejects.toThrow("collection is not editable");
});

test("updateFeature sends a PUT and resolves on 204", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/collections/incidents/items/7", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().updateFeature("incidents", "7", {
    type: "Feature",
    properties: { titre: "Mise à jour" },
    geometry: null,
  });
  expect(body).toEqual({ type: "Feature", properties: { titre: "Mise à jour" }, geometry: null });
});

test("updateFeature throws a plain Error with the server message on 404", async () => {
  server.use(
    http.put("https://core.test/collections/incidents/items/999", () =>
      HttpResponse.json({ detail: "feature not found" }, { status: 404 }),
    ),
  );
  await expect(
    makeClient().updateFeature("incidents", "999", { type: "Feature", properties: {}, geometry: null }),
  ).rejects.toThrow("feature not found");
});

test("deleteFeature sends a DELETE and resolves on 204", async () => {
  let method: string | null = null;
  server.use(
    http.delete("https://core.test/collections/incidents/items/7", ({ request }) => {
      method = request.method;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteFeature("incidents", "7");
  expect(method).toBe("DELETE");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `getCollectionSchema`/`createFeature`/`updateFeature`/`deleteFeature` n'existent pas sur l'objet retourné par `createItemClient` (TypeError: `... is not a function`), et `FeatureValidationError` n'est exporté nulle part (erreur d'import TypeScript).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, juste après le type `LayerSource` (ligne 67), insérer :

```ts
export type CollectionFieldType =
  | "string" | "integer" | "number" | "boolean" | "date" | "datetime" | "enum" | "unsupported";

export type CollectionSchemaField = {
  name: string;
  type: CollectionFieldType;
  required: boolean;
  maxLength?: number;
  values?: string[];
};

export type CollectionSchema = {
  collection: string;
  pk: string;
  geometry: { column: string; type: string | null; srid: number } | null;
  fields: CollectionSchemaField[];
};

export type FieldError = { field: string; code: string; message: string };

export type GeoJSONFeatureInput = {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: unknown | null;
};
```

Dans l'interface `ItemClient` (lignes 69-88), après `featuresUrl(source: DataSource): string;`, ajouter :

```ts
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
  createFeature(collectionId: string, feature: GeoJSONFeatureInput): Promise<{ id: string | number }>;
  updateFeature(collectionId: string, fid: string, feature: GeoJSONFeatureInput): Promise<void>;
  deleteFeature(collectionId: string, fid: string): Promise<void>;
```

Dans `shell/src/api/itemClient.ts`, importer les nouveaux types en tête de fichier (ligne 1, ajouter à la liste existante) : `FieldError`, `GeoJSONFeatureInput`, `CollectionSchema`. Puis, juste après la déclaration de `STAT_KEYS` (ligne 32), ajouter :

```ts
export class FeatureValidationError extends Error {
  errors: FieldError[];
  constructor(errors: FieldError[]) {
    super("feature validation failed");
    this.name = "FeatureValidationError";
    this.errors = errors;
  }
}

async function requestFeatureWrite<T>(
  url: string,
  method: string,
  token: string | undefined,
  body?: GeoJSONFeatureInput,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 400) {
    const data = (await res.json().catch(() => null)) as { detail?: { errors?: FieldError[] } } | null;
    throw new FeatureValidationError(data?.detail?.errors ?? []);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: unknown } | null;
    const message = typeof data?.detail === "string" ? data.detail : `Request failed: ${res.status} ${method} ${url}`;
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
```

Dans l'objet retourné par `createItemClient` (juste après `queryDataSource`, qui clôt l'objet à la ligne 394), ajouter avant la fermeture `};` :

```ts
    async getCollectionSchema(collectionId: string): Promise<CollectionSchema> {
      return request<CollectionSchema>("GET", `/collections/${collectionId}/schema`);
    },

    async createFeature(collectionId: string, feature: GeoJSONFeatureInput): Promise<{ id: string | number }> {
      return requestFeatureWrite<{ id: string | number }>(
        `${coreUrl}/collections/${collectionId}/items`, "POST", getToken(), feature,
      );
    },

    async updateFeature(collectionId: string, fid: string, feature: GeoJSONFeatureInput): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`, "PUT", getToken(), feature,
      );
    },

    async deleteFeature(collectionId: string, fid: string): Promise<void> {
      await requestFeatureWrite<void>(
        `${coreUrl}/collections/${collectionId}/items/${fid}`, "DELETE", getToken(),
      );
    },
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (tous les tests, y compris les 7 nouveaux)

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient — schéma de collection et écriture de features (SP-4a)"
```

---

## Task 2: `DataSourceState` — exposer la collection liée (`layer`)

**Files:**
- Modify: `shell/src/api/types.ts:135-140` (`DataSourceState`)
- Modify: `shell/src/builder/DataContext.tsx:32-37`
- Modify: `shell/src/builder/DataContext.test.tsx:20-37` (premier test)

**Interfaces:**
- Produces: `DataSourceState.layer?: string` — la collection (`DataSource.layer`) liée à cette source, quand elle en a une. Task 6 le lit via `ctx.data?.layer` pour savoir quelle collection cibler à l'écriture, sans re-brancher `dataSources` dans `WidgetContext`.
- Consumes: rien de nouveau.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `shell/src/builder/DataContext.test.tsx`, remplacer le premier test (lignes 20-37) par :

```tsx
test("resolves sources and exposes their state", async () => {
  const client = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: {} }]),
    featuresUrl: vi.fn().mockReturnValue("https://fs/parcs/items.json"),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DataProvider sources={sources}>
          <Probe />
        </DataProvider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText(/records:1/)).toBeInTheDocument());
  expect(screen.getByText(/url:https:\/\/fs\/parcs\/items.json/)).toBeInTheDocument();
});
```

(le rendu ne change pas — modifier plutôt `Probe`, lignes 13-18, pour exposer `layer`) :

```tsx
function Probe() {
  const states = useDataStates();
  const s = states["ds1"];
  if (!s || s.loading) return <p>loading</p>;
  return <p>records:{s.records.length} url:{s.url} layer:{s.layer}</p>;
}
```

Et ajouter à la fin du premier test :

```ts
  expect(screen.getByText(/layer:parcs/)).toBeInTheDocument();
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: FAIL sur la nouvelle assertion `layer:parcs` — `DataSourceState` ne porte pas encore de champ `layer`, donc `s.layer` vaut `undefined` et le texte rendu est `layer:` (vide).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, `DataSourceState` (lignes 135-140) :

```ts
export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  layer?: string;
  url?: string;
};
```

Dans `shell/src/builder/DataContext.tsx`, dans la boucle qui construit `states` (lignes 32-37) :

```ts
  const states: Record<string, DataSourceState> = {};
  sources.forEach((s, i) => {
    const r = results[i];
    const merged = { ...s, query: { ...s.query, ...(filters[s.id] ?? {}) } };
    states[s.id] = {
      loading: r.isLoading,
      error: r.isError,
      records: r.data ?? [],
      layer: s.layer,
      url: s.type === "features" ? client.featuresUrl(merged) : undefined,
    };
  });
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS (56+ fichiers — `layer` étant optionnel, aucun des `state()`/fixtures existants dans `mapWidget.test.tsx`/`data.test.tsx`/`indicator.test.tsx`/`chart.test.tsx`/`text.test.tsx` n'est cassé par son absence)

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/api/types.ts src/builder/DataContext.tsx src/builder/DataContext.test.tsx
git commit -m "feat(shell): DataSourceState expose la collection liée (layer) — préparation du widget Formulaire"
```

---

## Task 3: Widget Formulaire — squelette + chargement des champs depuis le schéma

**Files:**
- Create: `shell/src/builder/widgets/form.tsx`
- Create: `shell/src/builder/widgets/form.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx:1-9` (import), `:138-143` (appel dans `registerBuiltinWidgets`)

**Interfaces:**
- Produces: type `FormField` (exporté depuis `form.tsx`) — `{ name, type, label, order, hidden, required, maxLength?, values?, min?, max?, pattern? }` ; fonction `registerFormWidget()`. `props.fields: FormField[]` et `props.geometryType: string | null` sont les deux clés de `WidgetItem.props` que Tasks 4-7 lisent/écrivent.
- Consumes: `ItemClient.getCollectionSchema` (Task 1), `DataSourceSelect` (existant, `shell/src/builder/DataSourceSelect.tsx`), `registerWidget`/`WidgetDefinition` (existant, `shell/src/builder/registry.ts`).

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `shell/src/builder/widgets/form.test.tsx` :

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const schema: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "titre", type: "string", required: true, maxLength: 120 },
    { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
    { name: "nb_victimes", type: "integer", required: false },
  ],
};

const dataSources: DataSource[] = [{ id: "ds1", type: "features", service: "core", layer: "incidents", query: {} }];

function renderPanel(
  props: Record<string, unknown>,
  onChange = vi.fn(),
  clientOverrides: Partial<ItemClient> = {},
) {
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Panel = getWidget("form")!.PropsPanel;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Panel props={props} dataSources={dataSources} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange, client };
}

test("form widget is registered with submitted/failed events and a reset action", () => {
  const def = getWidget("form")!;
  expect(def.label).toBe("Formulaire");
  expect(def.events).toEqual(["submitted", "failed"]);
  expect(def.actions).toEqual(["reset"]);
  expect(def.defaultProps).toEqual({ dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null });
});

test("props panel offers a button to load fields once the schema resolves", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: [], submitLabel: "Enregistrer", geometryType: null });
  const button = await screen.findByRole("button", { name: "Charger les champs du schéma" });
  await userEvent.click(button);
  expect(onChange).toHaveBeenCalledWith({
    dataSourceId: "ds1",
    submitLabel: "Enregistrer",
    geometryType: "Point",
    fields: [
      { name: "titre", type: "string", label: "titre", order: 0, hidden: false, required: true, maxLength: 120 },
      { name: "gravite", type: "enum", label: "gravite", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
      { name: "nb_victimes", type: "integer", label: "nb_victimes", order: 2, hidden: false, required: false },
    ],
  });
});

test("props panel hides the load button once fields are already loaded", () => {
  renderPanel({
    dataSourceId: "ds1",
    fields: [{ name: "titre", type: "string", label: "Titre", order: 0, hidden: false, required: true }],
    submitLabel: "Enregistrer",
    geometryType: null,
  });
  expect(screen.queryByRole("button", { name: "Charger les champs du schéma" })).not.toBeInTheDocument();
});

test("props panel shows an error when the schema fails to load", async () => {
  renderPanel(
    { dataSourceId: "ds1", fields: [], submitLabel: "Enregistrer", geometryType: null },
    vi.fn(),
    { getCollectionSchema: vi.fn().mockRejectedValue(new Error("nope")) },
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(/schéma introuvable/i);
});

test("props panel shows nothing schema-related when no data source is bound", () => {
  renderPanel({ dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null });
  expect(screen.queryByRole("button", { name: "Charger les champs du schéma" })).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — `getWidget("form")` renvoie `undefined` (le widget n'est pas encore enregistré), donc `getWidget("form")!.PropsPanel` lève une erreur de déréférencement.

- [ ] **Step 3: Implémenter**

Créer `shell/src/builder/widgets/form.tsx` :

```tsx
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { useItemClient } from "../../api/ItemClientProvider";
import type { CollectionSchema, DataSource } from "../../api/types";

export type FormField = {
  name: string;
  type: CollectionSchema["fields"][number]["type"];
  label: string;
  order: number;
  hidden: boolean;
  required: boolean;
  maxLength?: number;
  values?: string[];
  min?: number;
  max?: number;
  pattern?: string;
};

function fieldsFromSchema(schema: CollectionSchema): FormField[] {
  return schema.fields.map((f, i) => ({
    name: f.name,
    type: f.type,
    label: f.name,
    order: i,
    hidden: false,
    required: f.required,
    ...(f.maxLength !== undefined ? { maxLength: f.maxLength } : {}),
    ...(f.values !== undefined ? { values: f.values } : {}),
  }));
}

function FormPropsPanel({
  props,
  onChange,
  dataSources,
}: {
  props: Record<string, unknown>;
  onChange: (props: Record<string, unknown>) => void;
  dataSources: DataSource[];
}) {
  const client = useItemClient();
  const dataSourceId = String(props.dataSourceId ?? "");
  const fields = (props.fields as FormField[] | undefined) ?? [];
  const source = dataSources.find((s) => s.id === dataSourceId);
  const collectionId = source?.layer ?? "";
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
    enabled: collectionId !== "",
  });

  return (
    <div className="flex flex-col gap-2 text-sm">
      <DataSourceSelect
        value={dataSourceId}
        dataSources={dataSources.filter((s) => s.type === "features")}
        onChange={(id) => onChange({ ...props, dataSourceId: id, fields: [], geometryType: null })}
      />
      {collectionId !== "" && schemaQuery.isLoading && (
        <p className="text-xs text-[var(--gs-color-muted)]">Chargement du schéma…</p>
      )}
      {collectionId !== "" && schemaQuery.isError && (
        <p role="alert" className="text-xs text-red-600">Schéma introuvable pour « {collectionId} ».</p>
      )}
      {collectionId !== "" && schemaQuery.data && fields.length === 0 && (
        <button
          type="button"
          className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
          onClick={() =>
            onChange({
              ...props,
              fields: fieldsFromSchema(schemaQuery.data),
              geometryType: schemaQuery.data.geometry?.type ?? null,
            })
          }
        >
          Charger les champs du schéma
        </button>
      )}
    </div>
  );
}

function FormComponent() {
  return <p className="text-xs text-[var(--gs-color-muted)]">Formulaire (à suivre)</p>;
}

export function registerFormWidget(): void {
  registerWidget({
    type: "form",
    label: "Formulaire",
    defaultProps: { dataSourceId: "", fields: [], submitLabel: "Enregistrer", geometryType: null },
    defaultSize: { w: 4, h: 6 },
    events: ["submitted", "failed"],
    actions: ["reset"],
    PropsPanel: FormPropsPanel,
    Component: FormComponent,
  });
}
```

Dans `shell/src/builder/widgets/index.tsx`, ajouter l'import (ligne 9, après `registerNavigationWidget`) :

```ts
import { registerFormWidget } from "./form";
```

Et l'appel dans `registerBuiltinWidgets` (bloc lignes 138-143) :

```ts
  registerDataWidgets();
  registerIndicatorWidget();
  registerMapWidget();
  registerFilterWidget();
  registerChartWidget();
  registerNavigationWidget();
  registerFormWidget();
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx src/builder/widgets/index.tsx
git commit -m "feat(shell): widget Formulaire — squelette + chargement des champs depuis le schéma (SP-4a)"
```

---

## Task 4: Widget Formulaire — panneau d'overrides (label, ordre, masquage, validation)

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (ajout du composant `FieldOverrides`, câblé dans `FormPropsPanel`)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: rien de nouveau exporté — `FieldOverrides` reste interne à `form.tsx`. Modifie la forme des entrées de `props.fields` en place (label/hidden/required/min/max/pattern/order), consommée telle quelle par Task 5+.
- Consumes: `FormField` (Task 3).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter l'import `fireEvent` (compléter la ligne d'import existante) :

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
```

Puis ajouter en fin de fichier :

```tsx
const loadedFields = [
  { name: "titre", type: "string" as const, label: "titre", order: 0, hidden: false, required: true, maxLength: 120 },
  { name: "gravite", type: "enum" as const, label: "gravite", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
  { name: "nb_victimes", type: "integer" as const, label: "nb_victimes", order: 2, hidden: false, required: false },
];

test("field overrides let you rename a field's label", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  const input = await screen.findByLabelText("Label du champ titre");
  await userEvent.clear(input);
  await userEvent.type(input, "Titre de l'incident");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "titre").label).toBe("Titre de l'incident");
});

test("field overrides toggle hidden and required", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await userEvent.click(await screen.findByLabelText("Masquer nb_victimes"));
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "nb_victimes").hidden).toBe(true);
});

test("field overrides set min/max on a numeric field", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await userEvent.type(await screen.findByLabelText("Min nb_victimes"), "0");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "nb_victimes").min).toBe(0);
});

test("field overrides set a validation pattern on a string field", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await userEvent.type(await screen.findByLabelText("Motif titre"), "^[A-Z]");
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.find((f: { name: string }) => f.name === "titre").pattern).toBe("^[A-Z]");
});

test("field overrides do not offer min/max/pattern for an enum field", async () => {
  renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  await screen.findByLabelText("Label du champ gravite");
  expect(screen.queryByLabelText("Min gravite")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Motif gravite")).not.toBeInTheDocument();
});

test("dragging a field row onto another reorders the list and renumbers order", async () => {
  const { onChange } = renderPanel({ dataSourceId: "ds1", fields: loadedFields, submitLabel: "Enregistrer", geometryType: "Point" });
  const rows = await screen.findAllByRole("listitem");
  const dataTransfer = { setData: vi.fn() };
  fireEvent.dragStart(rows[0], { dataTransfer });
  fireEvent.drop(rows[2], { dataTransfer });
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.map((f: { name: string; order: number }) => [f.name, f.order])).toEqual([
    ["gravite", 0],
    ["nb_victimes", 1],
    ["titre", 2],
  ]);
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — aucun de ces éléments (`Label du champ titre`, `Masquer nb_victimes`, `Min nb_victimes`, `Motif titre`, `role="listitem"`) n'existe encore, `FormPropsPanel` ne rend que le sélecteur de source et le bouton de chargement.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, ajouter (avant `FormPropsPanel`) :

```tsx
const overrideInputCls = "h-8 w-full rounded border border-slate-300 px-2 text-xs";

function FieldOverrides({
  fields,
  onChange,
}: {
  fields: FormField[];
  onChange: (fields: FormField[]) => void;
}) {
  const sorted = [...fields].sort((a, b) => a.order - b.order);

  function patch(name: string, changes: Partial<FormField>) {
    onChange(fields.map((f) => (f.name === name ? { ...f, ...changes } : f)));
  }

  function reorder(fromIndex: number, toIndex: number) {
    if (fromIndex === toIndex) return;
    const next = [...sorted];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    onChange(next.map((f, i) => ({ ...f, order: i })));
  }

  let dragIndex: number | null = null;

  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((f, i) => (
        <li
          key={f.name}
          draggable
          onDragStart={(e) => {
            dragIndex = i;
            e.dataTransfer.setData("text/plain", String(i));
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (dragIndex !== null) reorder(dragIndex, i);
            dragIndex = null;
          }}
          className="flex cursor-move flex-col gap-1 rounded border border-slate-200 p-1.5"
        >
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-slate-400" aria-hidden="true">⠿</span>
            <input
              aria-label={`Label du champ ${f.name}`}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
            <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
              <input
                type="checkbox"
                aria-label={`Masquer ${f.name}`}
                checked={f.hidden}
                onChange={(e) => patch(f.name, { hidden: e.target.checked })}
              />
              Masqué
            </label>
            {f.type !== "unsupported" && (
              <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
                <input
                  type="checkbox"
                  aria-label={`Requis ${f.name}`}
                  checked={f.required}
                  onChange={(e) => patch(f.name, { required: e.target.checked })}
                />
                Requis
              </label>
            )}
          </div>
          {(f.type === "integer" || f.type === "number") && (
            <div className="flex gap-1">
              <input
                aria-label={`Min ${f.name}`}
                type="number"
                placeholder="min"
                className={overrideInputCls}
                value={f.min ?? ""}
                onChange={(e) => patch(f.name, { min: e.target.value === "" ? undefined : Number(e.target.value) })}
              />
              <input
                aria-label={`Max ${f.name}`}
                type="number"
                placeholder="max"
                className={overrideInputCls}
                value={f.max ?? ""}
                onChange={(e) => patch(f.name, { max: e.target.value === "" ? undefined : Number(e.target.value) })}
              />
            </div>
          )}
          {f.type === "string" && (
            <input
              aria-label={`Motif ${f.name}`}
              placeholder="motif (regex, optionnel)"
              className={overrideInputCls}
              value={f.pattern ?? ""}
              onChange={(e) => patch(f.name, { pattern: e.target.value || undefined })}
            />
          )}
        </li>
      ))}
    </ul>
  );
}
```

Puis, dans `FormPropsPanel`, remplacer la dernière ligne du `return` (juste avant `</div>`, après le bouton « Charger les champs du schéma ») en ajoutant :

```tsx
      {fields.length > 0 && (
        <FieldOverrides fields={fields} onChange={(next) => onChange({ ...props, fields: next })} />
      )}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — panneau d'overrides (label, ordre, masquage, validation) (SP-4a)"
```

---

## Task 5: Widget Formulaire — rendu des champs et validation client

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (fonction `validateField`, rendu par type de champ, `FormComponent`)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `FormComponent` rend maintenant un vrai formulaire ; la soumission valide localement et affiche les erreurs mais **n'écrit rien encore** (Task 6 câble l'appel serveur). `ctx.data`/`ctx.bus` ne sont pas encore utilisés par `FormComponent` à ce stade.
- Consumes: `FormField` (Task 3).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter l'import `WidgetContext` (compléter les imports en tête de fichier) :

```tsx
import type { WidgetContext } from "../registry";
```

Puis ajouter en fin de fichier :

```tsx
const visibleFields = [
  { name: "titre", type: "string" as const, label: "Titre", order: 0, hidden: false, required: true },
  { name: "gravite", type: "enum" as const, label: "Gravité", order: 1, hidden: false, required: true, values: ["faible", "moyenne", "haute"] },
  { name: "nb_victimes", type: "integer" as const, label: "Victimes", order: 2, hidden: false, required: false, min: 0 },
  { name: "notes_internes", type: "string" as const, label: "Notes internes", order: 3, hidden: true, required: false },
];

function renderForm(fields = visibleFields, ctx: Partial<WidgetContext> = {}) {
  const Form = getWidget("form")!.Component;
  render(<Form props={{ dataSourceId: "ds1", fields, submitLabel: "Enregistrer" }} ctx={{ mode: "runtime", ...ctx } as WidgetContext} />);
}

test("form renders visible fields ordered, skipping hidden ones", () => {
  renderForm();
  const labels = screen.getAllByRole("textbox").map((el) => el.getAttribute("aria-label"));
  expect(labels).toContain("Titre");
  expect(screen.queryByLabelText("Notes internes")).not.toBeInTheDocument();
});

test("form shows a required error after blurring an empty required field", async () => {
  renderForm();
  const titre = screen.getByLabelText("Titre");
  await userEvent.click(titre);
  await userEvent.tab();
  expect(await screen.findByRole("alert")).toHaveTextContent("Champ requis");
});

test("form blocks submit and surfaces one error per invalid required field", async () => {
  renderForm();
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(screen.getAllByRole("alert")).toHaveLength(2); // titre + gravite, tous deux requis et vides
});

test("form validates a numeric field against its min bound", async () => {
  renderForm();
  const victimes = screen.getByLabelText("Victimes");
  await userEvent.type(victimes, "-1");
  await userEvent.tab();
  expect(await screen.findByText("Doit être ≥ 0")).toBeInTheDocument();
});

test("form validates a string field against its pattern", async () => {
  const fields = [{ name: "titre", type: "string" as const, label: "Titre", order: 0, hidden: false, required: false, pattern: "^[A-Z]" }];
  renderForm(fields);
  const titre = screen.getByLabelText("Titre");
  await userEvent.type(titre, "fuite");
  await userEvent.tab();
  expect(await screen.findByText("Format invalide")).toBeInTheDocument();
});

test("form renders an enum field as a select with its schema options", () => {
  renderForm();
  const select = screen.getByLabelText("Gravité");
  expect(select.tagName).toBe("SELECT");
  expect(screen.getByRole("option", { name: "haute" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — `FormComponent` rend toujours le texte statique « Formulaire (à suivre) », aucun champ/label/bouton n'existe.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, ajouter (avant `FormComponent`) :

```tsx
function validateField(field: FormField, value: unknown): string | null {
  const empty = value === undefined || value === null || value === "";
  if (field.required && empty) return "Champ requis";
  if (empty) return null;
  if (field.type === "integer" || field.type === "number") {
    const n = Number(value);
    if (Number.isNaN(n)) return "Nombre invalide";
    if (field.min !== undefined && n < field.min) return `Doit être ≥ ${field.min}`;
    if (field.max !== undefined && n > field.max) return `Doit être ≤ ${field.max}`;
  }
  if (field.type === "string") {
    if (field.maxLength !== undefined && String(value).length > field.maxLength) {
      return `${field.maxLength} caractères maximum`;
    }
    if (field.pattern && !new RegExp(field.pattern).test(String(value))) return "Format invalide";
  }
  if (field.type === "enum" && field.values && !field.values.includes(String(value))) return "Valeur invalide";
  return null;
}

const fieldInputCls = "h-9 rounded-md border border-slate-300 px-2 text-sm";

function FieldInput({
  field,
  value,
  onChange,
  onBlur,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
}) {
  if (field.type === "boolean") {
    return (
      <input type="checkbox" aria-label={field.label} checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)} onBlur={onBlur} />
    );
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <input type="number" aria-label={field.label} className={fieldInputCls}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} onBlur={onBlur} />
    );
  }
  if (field.type === "date") {
    return (
      <input type="date" aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
    );
  }
  if (field.type === "datetime") {
    return (
      <input type="datetime-local" aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
    );
  }
  if (field.type === "enum") {
    return (
      <select aria-label={field.label} className={fieldInputCls}
        value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur}>
        <option value=""></option>
        {(field.values ?? []).map((v) => <option key={v} value={v}>{v}</option>)}
      </select>
    );
  }
  return (
    <input type="text" aria-label={field.label} className={fieldInputCls}
      value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} />
  );
}
```

Puis remplacer entièrement `FormComponent` :

```tsx
function FormComponent({ props }: { props: Record<string, unknown> }) {
  const fields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported")
    .sort((a, b) => a.order - b.order);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});

  function errorFor(field: FormField): string | null {
    if (!touched[field.name]) return null;
    return validateField(field, values[field.name]);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const allTouched: Record<string, boolean> = {};
    fields.forEach((f) => { allTouched[f.name] = true; });
    setTouched(allTouched);
  }

  return (
    <form className="flex h-full flex-col gap-2 overflow-auto text-sm" onSubmit={handleSubmit}>
      {fields.map((f) => (
        <label key={f.name} className="flex flex-col gap-1">
          {f.label}{f.required ? " *" : ""}
          <FieldInput
            field={f}
            value={values[f.name]}
            onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
            onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
          />
          {errorFor(f) && <span role="alert" className="text-xs text-red-600">{errorFor(f)}</span>}
        </label>
      ))}
      <div className="mt-auto flex items-center gap-2">
        <button type="submit" className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white">
          {String(props.submitLabel ?? "Enregistrer")}
        </button>
      </div>
    </form>
  );
}
```

Ajouter `useState` à l'import React en tête de fichier :

```ts
import { useState } from "react";
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — rendu des champs et validation client (SP-4a)"
```

---

## Task 6: Widget Formulaire — écriture (`feature.create`), états et rafraîchissement

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (`FormComponent` — écriture, états, `reset`, événements)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: `FormComponent` appelle désormais `ItemClient.createFeature`, expose l'état `idle|pending|success|error`, invalide `["datasource"]`, émet `submitted`/`failed` sur le bus, répond à l'action bus `reset`.
- Consumes: `ItemClient.createFeature` (Task 1), `DataSourceState.layer` (Task 2), `useBusAction`/`ActionBus` (existant, `shell/src/builder/ActionBusContext.tsx`), `FeatureValidationError` (Task 1).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, modifier la ligne d'import `@testing-library/react` (posée en Task 3, étendue en Task 4) pour ajouter `waitFor` :

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
```

Ajouter deux nouveaux imports (le reste — `QueryClient`/`QueryClientProvider`/`ItemClient` — existe déjà depuis Task 3) :

```tsx
import { ActionBus } from "../ActionBus";
import { FeatureValidationError } from "../../api/itemClient";
```

Puis ajouter un nouveau helper et les tests, en fin de fichier :

```tsx
function renderConnectedForm({
  fields = visibleFields,
  client: clientOverrides = {},
  bus,
  widgetId = "form1",
  layer = "incidents",
}: {
  fields?: typeof visibleFields;
  client?: Partial<ItemClient>;
  bus?: ActionBus;
  widgetId?: string;
  layer?: string;
} = {}) {
  const client = {
    createFeature: vi.fn().mockResolvedValue({ id: 1 }),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields, submitLabel: "Enregistrer" }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer }, bus, widgetId } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client, invalidateSpy };
}

test("a valid submit calls createFeature with the bound collection and properties", async () => {
  const { client } = renderConnectedForm();
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith("incidents", {
      type: "Feature",
      properties: { titre: "Fuite d'eau", gravite: "haute" },
      geometry: null,
    }),
  );
});

test("a successful submit clears the form, invalidates data sources, and emits submitted", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "log", handler);
  bus.configure([{ id: "m", from: "form1", event: "submitted", to: "sink", action: "log" }]);
  const { invalidateSpy } = renderConnectedForm({ bus });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(handler).toHaveBeenCalledWith({ properties: { titre: "Fuite d'eau", gravite: "haute" } }));
  expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["datasource"] });
  expect(screen.getByLabelText("Titre")).toHaveValue("");
});

test("submit is disabled while the write is pending", async () => {
  let resolveWrite!: (v: { id: number }) => void;
  const createFeature = vi.fn(() => new Promise<{ id: number }>((resolve) => { resolveWrite = resolve; }));
  renderConnectedForm({ client: { createFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  resolveWrite({ id: 1 });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).not.toBeDisabled());
});

test("a 400 response maps field errors onto the matching inputs", async () => {
  // titre/gravité are both filled (client validation passes) — the server
  // still rejects on a rule the client doesn't know about (e.g. a uniqueness
  // constraint), proving the 400 mapping runs independently of client checks.
  const createFeature = vi.fn().mockRejectedValue(
    new FeatureValidationError([{ field: "titre", code: "duplicate", message: "un incident « Fuite d'eau » existe déjà" }]),
  );
  const bus = new ActionBus();
  const failed = vi.fn();
  bus.register("sink", "log", failed);
  bus.configure([{ id: "m", from: "form1", event: "failed", to: "sink", action: "log" }]);
  renderConnectedForm({ client: { createFeature }, bus });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("un incident « Fuite d'eau » existe déjà")).toBeInTheDocument();
  expect(failed).toHaveBeenCalled();
});

test("a generic write failure shows a fallback message without crashing", async () => {
  const createFeature = vi.fn().mockRejectedValue(new Error("collection is not editable"));
  renderConnectedForm({ client: { createFeature } });
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("Échec de l'enregistrement.")).toBeInTheDocument();
});

test("the reset bus action clears the form", async () => {
  // ActionBus.emit(widgetId, event) only routes through configured wiring
  // (from/event → to/action) — it does not invoke a widget's own registered
  // action directly. Mirror the mapWidget.test.tsx precedent: a source
  // widget ("btn1") emits an event wired to form1's "reset" action.
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "btn1", event: "clicked", to: "form1", action: "reset" }]);
  renderConnectedForm({ bus, widgetId: "form1" });
  await userEvent.type(screen.getByLabelText("Titre"), "Brouillon");
  bus.emit("btn1", "clicked");
  await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue(""));
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — `FormComponent` (signature `{ props }`, sans `ctx`) n'appelle aucun `ItemClient`, le clic sur « Enregistrer » ne fait qu'un `preventDefault` local ; aucune de ces assertions ne peut passer.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, remplacer la ligne d'import `import { useQuery } from "@tanstack/react-query";` (posée en Task 3) par :

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
```

Et ajouter ces nouveaux imports (`useItemClient` est déjà importé depuis Task 3, ne pas le dupliquer) :

```ts
import { useBusAction } from "../ActionBusContext";
import { FeatureValidationError } from "../../api/itemClient";
import type { WidgetContext } from "../registry";
```

Remplacer entièrement `FormComponent` par :

```tsx
function FormComponent({ props, ctx }: { props: Record<string, unknown>; ctx: WidgetContext }) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  const fields = ((props.fields as FormField[] | undefined) ?? [])
    .filter((f) => !f.hidden && f.type !== "unsupported")
    .sort((a, b) => a.order - b.order);
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});
  const [genericError, setGenericError] = useState(false);

  const write = useMutation({
    mutationFn: (properties: Record<string, unknown>) =>
      client.createFeature(ctx.data?.layer ?? "", { type: "Feature", properties, geometry: null }),
  });

  function resetTo() {
    setValues({});
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    write.reset();
  }
  useBusAction(ctx.bus, ctx.widgetId, "reset", resetTo);

  function errorFor(field: FormField): string | null {
    if (touched[field.name]) {
      const clientError = validateField(field, values[field.name]);
      if (clientError) return clientError;
    }
    return serverErrors[field.name] ?? null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const allTouched: Record<string, boolean> = {};
    fields.forEach((f) => { allTouched[f.name] = true; });
    setTouched(allTouched);
    const hasClientErrors = fields.some((f) => validateField(f, values[f.name]) !== null);
    if (hasClientErrors) return;
    setServerErrors({});
    setGenericError(false);
    const properties: Record<string, unknown> = {};
    fields.forEach((f) => {
      if (values[f.name] !== undefined) properties[f.name] = values[f.name];
    });
    try {
      await write.mutateAsync(properties);
      queryClient.invalidateQueries({ queryKey: ["datasource"] });
      ctx.bus?.emit(ctx.widgetId ?? "", "submitted", { properties });
      resetTo();
    } catch (err) {
      if (err instanceof FeatureValidationError) {
        const byField: Record<string, string> = {};
        err.errors.forEach((fe) => { byField[fe.field] = fe.message; });
        setServerErrors(byField);
      } else {
        setGenericError(true);
      }
      ctx.bus?.emit(ctx.widgetId ?? "", "failed", { message: err instanceof Error ? err.message : "unknown" });
    }
  }

  return (
    <form className="flex h-full flex-col gap-2 overflow-auto text-sm" onSubmit={handleSubmit}>
      {fields.map((f) => (
        <label key={f.name} className="flex flex-col gap-1">
          {f.label}{f.required ? " *" : ""}
          <FieldInput
            field={f}
            value={values[f.name]}
            onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
            onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
          />
          {errorFor(f) && <span role="alert" className="text-xs text-red-600">{errorFor(f)}</span>}
        </label>
      ))}
      <div className="mt-auto flex items-center gap-2">
        <button
          type="submit"
          disabled={write.isPending}
          className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white disabled:opacity-50"
        >
          {String(props.submitLabel ?? "Enregistrer")}
        </button>
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm" onClick={resetTo}>
          Réinitialiser
        </button>
      </div>
      {genericError && (
        <p role="alert" className="text-xs text-red-600">Échec de l'enregistrement.</p>
      )}
    </form>
  );
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — écriture feature.create, états et rafraîchissement (SP-4a)"
```

---

## Task 7: Widget Formulaire — champ géométrie (point)

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (`FormComponent` — rendu et soumission de la géométrie point)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout de tests, en fin de fichier)

**Interfaces:**
- Produces: rien de nouveau exporté — le comportement de `FormComponent` lit `props.geometryType` (déjà posé par Task 3) pour décider d'afficher deux champs numériques longitude/latitude, fusionnés en géométrie GeoJSON Point à la soumission.
- Consumes: `props.geometryType` (Task 3).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/widgets/form.test.tsx`, ajouter en fin de fichier :

```tsx
function renderConnectedFormWithGeometry(geometryType: string | null) {
  const client = { createFeature: vi.fn().mockResolvedValue({ id: 1 }) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds1", fields: visibleFields, submitLabel: "Enregistrer", geometryType }}
          ctx={{ mode: "runtime", data: { loading: false, error: false, records: [], layer: "incidents" } } as WidgetContext}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { client };
}

test("a Point collection shows longitude/latitude inputs", () => {
  renderConnectedFormWithGeometry("Point");
  expect(screen.getByLabelText("Longitude")).toBeInTheDocument();
  expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
});

test("a non-Point (or absent) geometry shows no geometry inputs", () => {
  renderConnectedFormWithGeometry("LineString");
  expect(screen.queryByLabelText("Longitude")).not.toBeInTheDocument();
  renderConnectedFormWithGeometry(null);
  expect(screen.queryByLabelText("Longitude")).not.toBeInTheDocument();
});

test("submitting with longitude/latitude filled sends a GeoJSON Point geometry", async () => {
  const { client } = renderConnectedFormWithGeometry("Point");
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.type(screen.getByLabelText("Longitude"), "2.35");
  await userEvent.type(screen.getByLabelText("Latitude"), "48.85");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith("incidents", {
      type: "Feature",
      properties: { titre: "Fuite d'eau", gravite: "haute" },
      geometry: { type: "Point", coordinates: [2.35, 48.85] },
    }),
  );
});

test("submitting a Point collection with empty coordinates sends a null geometry", async () => {
  const { client } = renderConnectedFormWithGeometry("Point");
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite d'eau");
  await userEvent.selectOptions(screen.getByLabelText("Gravité"), "haute");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(client.createFeature).toHaveBeenCalledWith(
      "incidents",
      expect.objectContaining({ geometry: null }),
    ),
  );
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: FAIL — aucun champ « Longitude »/« Latitude » n'est rendu, `createFeature` est toujours appelé avec `geometry: null` même quand des coordonnées sont saisies.

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, dans `FormComponent`, ajouter après la déclaration de `fields` :

```ts
  const geometryType = props.geometryType as string | null | undefined;
  const [lon, setLon] = useState<string>("");
  const [lat, setLat] = useState<string>("");
```

Dans `resetTo`, ajouter la remise à zéro des coordonnées :

```ts
  function resetTo() {
    setValues({});
    setTouched({});
    setServerErrors({});
    setGenericError(false);
    setLon("");
    setLat("");
    write.reset();
  }
```

Dans `handleSubmit`, juste avant la ligne `try {` (qui reste en place), insérer le calcul de la géométrie :

```ts
    const geometry =
      geometryType === "Point" && lon !== "" && lat !== ""
        ? { type: "Point", coordinates: [Number(lon), Number(lat)] }
        : null;
```

Puis, à l'intérieur du `try`, remplacer la ligne `await write.mutateAsync(properties);` par :

```ts
      await write.mutateAsync({ properties, geometry });
```

Enfin, la `mutationFn` doit accepter `{ properties, geometry }` au lieu de `properties` seul — mettre à jour sa signature :

```ts
  const write = useMutation({
    mutationFn: (input: { properties: Record<string, unknown>; geometry: unknown | null }) =>
      client.createFeature(ctx.data?.layer ?? "", { type: "Feature", properties: input.properties, geometry: input.geometry }),
  });
```

Enfin, dans le JSX, juste avant le bloc `<div className="mt-auto ...">`, ajouter :

```tsx
      {geometryType === "Point" && (
        <div className="flex gap-2">
          <label className="flex flex-1 flex-col gap-1">
            Longitude
            <input type="number" step="any" aria-label="Longitude" className={fieldInputCls}
              value={lon} onChange={(e) => setLon(e.target.value)} />
          </label>
          <label className="flex flex-1 flex-col gap-1">
            Latitude
            <input type="number" step="any" aria-label="Latitude" className={fieldInputCls}
              value={lat} onChange={(e) => setLat(e.target.value)} />
          </label>
        </div>
      )}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — champ géométrie point (SP-4a)"
```

---

## Couverture spec → tâches (auto-vérification)

- §1 SP-4a « Rendu depuis le schéma introspecté... panneau d'overrides visuel... dans le builder » → Tasks 3-4.
- §1 SP-4a « validation client et serveur » → Task 5 (client) ; serveur déjà couvert par SP-3b (`validate_feature`, non retouché ici) — le mapping des erreurs 400 vers les champs est fait en Task 6.
- §1 SP-4a « action `feature.create` et `form.reset` » → Task 6.
- §1 SP-4a « Nouvelles méthodes `ItemClient.createFeature/updateFeature/deleteFeature` posées ici (même si seules `createFeature`/`form.reset` sont câblées à un widget) » → Task 1 pose les trois méthodes ; seule `createFeature` est appelée par le widget (Task 6) ; `updateFeature`/`deleteFeature` restent non consommées, comme prescrit.
- §2 « Binding aux données... référence un `dataSourceId` exactement comme Table/Carte » → Tasks 3-4 (`DataSourceSelect` filtré sur `type: "features"`, identique à `mapWidget.tsx`).
- §2 « Géométrie du champ carte : point... si l'effort déborde, replier sur point-seul » → Task 7, repli assumé dès ce plan (cf. Global Constraints).
- §2 « Overrides de champ... panneau visuel complet dès SP-4a » → Task 4.
- §2 « Validation : deux couches, mêmes règles » → Task 5 (règles client) + Task 6 (mapping des erreurs serveur 400 sur les mêmes champs) ; le serveur applique déjà ces règles via `validate_feature` (SP-3b, non modifié).
- §5 « Rafraîchissement après écriture... toutes les data sources de la même collection... pas de cache partiel » → Task 6 (invalidation `["datasource"]`, cf. Global Constraints pour la justification de la portée large).
- §6 « États idle/pending/success/error... `role="alert"` » → Task 6.
- §3 architecture (bus, `ItemClient.createFeature`, émission `submitted`/`failed`) → Task 6.
- §7 stratégie de tests « Rendu du Formulaire depuis un schéma introspecté fixe... validation client... mapping des erreurs serveur 400... état idle/pending/success/error » → Tasks 3, 5, 6.
- §7 « émission/réception `itemSelected` → `loadRecord` sur un bus de test » → **hors périmètre de ce plan** (SP-4b, sélection→édition — la spec le classe explicitement dans SP-4b §1, pas SP-4a).
- §8 critères d'acceptation « créer une entité, la voir apparaître sur la carte et dans la table » → couvert fonctionnellement par Task 6 (invalidation large) ; la vérification bout-en-bout (E2E Playwright) est explicitement différée à SP-4c (§1, « template galerie + spec E2E »).
- §8 « un viewer ne voit pas les boutons d'écriture, le serveur refuse (403) » → le refus serveur est déjà testé côté cœur (SP-3b, `_get_writable`) ; Task 6 vérifie que le shell affiche un message d'échec générique sur un 403 (test « a generic write failure shows a fallback message ») — la vérification UI complète (masquage des boutons pour un viewer) est explicitement listée dans la spec §1 comme relevant de SP-4c.
- §9 risques « le plus gros SP front... SP-4a livre d'abord un Formulaire autonome » → confirmé par la structure de ce plan (aucune dépendance à un binding de sélection non construit).

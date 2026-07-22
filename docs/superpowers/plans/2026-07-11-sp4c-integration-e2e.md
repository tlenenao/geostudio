# SP-4c — Intégration et E2E : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clore SP-4 : un template galerie « Application de saisie » (Formulaire + Carte + Table pré-câblés), une spec E2E Playwright « déclarer un incident » couvrant le critère d'acceptation complet de la feuille de route, et la vérification qu'un `viewer` ne voit pas les boutons d'écriture tandis qu'une écriture forcée est refusée par le serveur (403) — cf. [SP-4 — Formulaires dans le builder](../specs/2026-07-10-sp4-formulaires-builder-design.md) §1.

**Architecture:** Le template ajoute une troisième source de données au widget Formulaire (SP-4a/4b) sans nouveau mécanisme : `Template` (jusqu'ici layout-only) gagne des `dataSources`/`messages` optionnels, seedés par `createConfigItem` exactement comme `layout` l'est déjà. La vérification viewer nécessite la seule vraie pièce nouvelle du plan : aujourd'hui rien, côté shell, ne sait si l'utilisateur courant peut écrire dans une collection — le refus serveur (403) existe déjà et est déjà testé, mais rien ne permet de **masquer** le bouton en amont. Cette pièce (`canWrite` par utilisateur, exposé par le cœur, consommé par le Formulaire) est ajoutée en configuration ouverte (fail-open) : l'affichage du bouton est une commodité UX, pas la frontière de sécurité — celle-ci reste le 403 serveur, inchangé.

**Tech Stack:** FastAPI + pytest (cœur, Task 1), React 19 + TypeScript + Vitest (Task 2-3), Playwright (Tasks 4-5, `VITE_AUTH_MODE=mock`).

## Global Constraints

- **Aucune régression sur le mécanisme d'autorisation existant.** `can()` (`core/app/sharing/authorization.py`) et `_get_writable` (`core/app/features/routes.py`) ne changent pas — le refus serveur (403) sur une écriture non autorisée existe déjà et est déjà testé (`core/tests/test_features_routes_write.py::test_viewer_write_is_403_editor_ok`). Ce plan expose seulement, en lecture, le résultat de `can()` pour que le shell puisse l'afficher.
- **`canWrite` est fail-open côté client** : `const canWrite = permissionQuery.data ?? true;` — tant que la requête de permission n'a pas résolu (ou échoue), le bouton reste visible. Décision délibérée : la frontière de sécurité réelle est le 403 serveur (inchangé) ; masquer le bouton n'est qu'une commodité UX. Un défaut fail-closed casserait la synchronicité de ~30 tests SP-4a/4b existants qui cliquent « Enregistrer » sans attendre une résolution asynchrone — fail-open préserve ce comportement sans aucune modification de ces tests.
- **Une seule permission `canWrite` gate à la fois la création/modification ET la suppression.** `can()` exige déjà le même rôle `"editor"` pour `action="write"` et `action="delete"` (`core/app/sharing/authorization.py`, `role_check({"editor"})` partagé) — pas de notion de « peut modifier mais pas supprimer » dans ce modèle de rôles, donc un seul indicateur suffit ; à revoir si un modèle de permissions plus fin apparaît plus tard.
- **`Template` reste rétrocompatible** : `dataSources`/`messages` sont optionnels ; les deux templates existants (« Deux colonnes », « Tableau de bord basique ») ne les définissent pas et continuent de seeder `dataSources: []`/`messages: []` comme aujourd'hui.
- **Le Formulaire du template utilise un `submitLabel` distinct** (`"Déclarer l'incident"`, pas la valeur par défaut `"Enregistrer"`) — sans ça, le bouton de soumission du Formulaire et le bouton d'enregistrement du builder porteraient le même nom accessible, rendant `page.getByRole("button", { name: "Enregistrer" })` ambigu en E2E (Playwright échoue en mode strict sur plusieurs correspondances), y compris en mode édition où le contenu du widget est visuellement non cliquable (`pointer-events-none`, `GridCanvas.tsx:51`) mais reste présent dans l'arbre d'accessibilité.
- **Nom de collection E2E : `incidents`**, réutilisant exactement le nom déjà utilisé par les fixtures Python (`core/tests/test_collections_routes.py:14`, `core/tests/test_features_routes_write.py`), avec les champs `titre` (string, requis) et `gravite` (enum `faible|moyenne|haute`, requis) — mêmes noms que les fixtures de test unitaire du Formulaire (SP-4a/4b), pour rester cohérent avec le reste de la feature.
- **Aucune assertion sur le rendu pixel de la carte en E2E** — cohérent avec le reste de la suite (aucune spec existante n'inspecte le canvas MapLibre) ; le critère d'acceptation « apparaît sur la carte » est déjà couvert par les tests unitaires du widget Carte (SP-4a/4b) qui vérifient le branchement `dataSourceId`→couche `feature`. L'E2E vérifie l'intégration bout-en-bout via la Table (DOM-testable) et l'état du Formulaire.
- **« Écriture forcée » (scénario viewer) vérifiée par un appel direct** (`page.evaluate(() => fetch(...))`), pas par un clic UI — le bouton étant légitimement masqué, forcer l'écriture reproduit fidèlement un contournement de l'interface (ex. devtools), qui est le sens de « si forcé » dans le critère d'acceptation.
- Docs et messages utilisateur en français ; code/identifiants en anglais.
- TDD systématique ; commits conventional en français.
- `cd shell && npm run test` (Vitest) et `npm run build` verts après les Tasks 2-3 ; `cd shell && npm run e2e` vert après les Tasks 4-5 (13 specs existantes + les nouvelles, aucune régression). `cd core && uv run pytest` vert après la Task 1.

---

## Task 1: Cœur — exposer `canWrite` par utilisateur sur les collections

**Files:**
- Modify: `core/app/collections/routes.py` (`_collection_json`, nouvelle fonction `_can_write_collection`, 4 sites d'appel : `register_collection`, `list_collections`, `get_collection`, `patch_collection`)
- Test: `core/tests/test_collections_routes.py` (ajout d'un test, en fin de fichier)

**Interfaces:**
- Produces: `GET /collections` et `GET /collections/{id}` (et implicitement `POST`/`PATCH /collections{,/{id}}`, qui renvoient aussi `_collection_json`) portent désormais un champ `"canWrite": bool` — `True` si l'utilisateur courant a le droit d'écrire dans cette collection (propriétaire, admin, ou rôle `editor` du groupe partagé) **et** que `collection.editable` est vrai ; `False` sinon (y compris utilisateur anonyme).
- Consumes: `can()` (existant, `core/app/sharing/authorization.py`), `repo.get_access_facts` (existant, `core/app/collections/repository.py`).

- [ ] **Step 1: Écrire le test qui échoue**

Dans `core/tests/test_collections_routes.py`, ajouter en fin de fichier :

```python
def test_canWrite_reflects_the_requesting_users_write_access(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "title": "Incidents", "isPublic": True})

    # admin (propriétaire de la collection qu'il vient de créer) : canWrite=True
    assert client.get("/collections/incidents").json()["canWrite"] is True
    assert client.get("/collections").json()["collections"][0]["canWrite"] is True

    # regular : lisible car isPublic=True (comme un viewer), mais aucun rôle
    # editor sur le groupe de partage de la collection → canWrite=False
    _as(app, regular)
    assert client.get("/collections/incidents").json()["canWrite"] is False
    assert client.get("/collections").json()["collections"][0]["canWrite"] is False
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_collections_routes.py::test_canWrite_reflects_the_requesting_users_write_access -v`
Expected: FAIL — `KeyError: 'canWrite'` (le champ n'existe pas encore dans la réponse JSON).

- [ ] **Step 3: Implémenter**

Dans `core/app/collections/routes.py`, juste après `_collection_json` (actuellement lignes 81-86), ajouter :

```python
def _can_write_collection(session, user, col) -> bool:
    if user is None:
        return False
    return col.editable and can(
        session, user_id=user.id, action="write", item=repo.get_access_facts(col),
        kind="collection", actor_is_admin=user.is_admin,
    )
```

Remplacer `_collection_json` pour qu'elle prenne le flag calculé en paramètre plutôt que de le recalculer elle-même (elle reste ainsi pure, sans dépendance à `session`/`can()`) :

```python
def _collection_json(col, can_write: bool) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": col.editable,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
        "canWrite": can_write,
    }
```

Puis mettre à jour les 4 sites d'appel. Dans `register_collection` (le `return _collection_json(col)` en fin de fonction) :

```python
    return _collection_json(col, _can_write_collection(session, user, col))
```

Dans `list_collections` :

```python
    return {"collections": [_collection_json(c, _can_write_collection(session, user, c)) for c in cols]}
```

Dans `get_collection` (la ligne `body = _collection_json(col)`) :

```python
    body = _collection_json(col, _can_write_collection(session, user, col))
```

Dans `patch_collection` (le `return _collection_json(col)` en fin de fonction) :

```python
    return _collection_json(col, _can_write_collection(session, user, col))
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: PASS (tous les tests du fichier, y compris les préexistants — `_collection_json` change de signature mais chaque appelant est déjà mis à jour).

Run: `cd core && uv run pytest`
Expected: PASS (291+ tests — aucune régression ailleurs ; `_collection_json` n'est appelée que depuis `core/app/collections/routes.py`).

- [ ] **Step 5: Commit**

```bash
cd core
git add app/collections/routes.py tests/test_collections_routes.py
git commit -m "feat(core): collections — expose canWrite par utilisateur (SP-4c)"
```

---

## Task 2: Shell — `ItemClient.getCollectionPermission` + le Formulaire masque ses boutons d'écriture

**Files:**
- Modify: `shell/src/api/types.ts` (interface `ItemClient`)
- Modify: `shell/src/api/itemClient.ts` (implémentation)
- Modify: `shell/src/api/itemClient.test.ts` (ajout de tests, en fin de fichier)
- Modify: `shell/src/builder/widgets/form.tsx` (`FormComponent` — requête de permission, masquage conditionnel)
- Modify: `shell/src/builder/widgets/form.test.tsx` (ajout d'un test, en fin de fichier)

**Interfaces:**
- Produces: `ItemClient.getCollectionPermission(collectionId: string): Promise<boolean>`.
- Consumes: `GET /collections/{id}` (Task 1, champ `canWrite`).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/itemClient.test.ts`, ajouter en fin de fichier :

```ts
test("getCollectionPermission returns the canWrite flag", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({ id: "incidents", title: "Incidents", canWrite: true }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(true);
});

test("getCollectionPermission defaults to false when the field is absent", async () => {
  server.use(
    http.get("https://core.test/collections/incidents", () =>
      HttpResponse.json({ id: "incidents", title: "Incidents" }),
    ),
  );
  expect(await makeClient().getCollectionPermission("incidents")).toBe(false);
});
```

Dans `shell/src/api/types.ts`, l'interface `ItemClient` reçoit une nouvelle méthode (préparée ici, câblée au Step 3) :

```ts
  getCollectionPermission(collectionId: string): Promise<boolean>;
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t getCollectionPermission`
Expected: FAIL — `makeClient().getCollectionPermission is not a function`.

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, ajouter la méthode à l'interface `ItemClient`, juste après `getCollectionSchema(collectionId: string): Promise<CollectionSchema>;` :

```ts
  getCollectionPermission(collectionId: string): Promise<boolean>;
```

Dans `shell/src/api/itemClient.ts`, ajouter la méthode dans l'objet retourné par `createItemClient`, juste après `getCollectionSchema` :

```ts
    async getCollectionPermission(collectionId: string): Promise<boolean> {
      const data = await request<{ canWrite?: boolean }>("GET", `/collections/${collectionId}`);
      return data.canWrite ?? false;
    },
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit (partiel — la suite du Formulaire vient au Step 6-9 ci-dessous, même tâche)**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient.getCollectionPermission (SP-4c)"
```

- [ ] **Step 6: Écrire le test qui échoue (Formulaire)**

D'abord, dans `shell/src/builder/widgets/form.test.tsx`, stubber `getCollectionPermission` par défaut dans les deux helpers qui montent `FormComponent` avec un vrai `ItemClient` mocké — sans ça, `FormComponent` appellerait une méthode absente du mock sur chacun des ~30 tests existants du fichier (react-query avale l'erreur sans faire planter le rendu grâce au défaut fail-open `?? true`, mais logue un warning dans chaque test — à éviter). Dans `renderConnectedForm` (l'objet `client` construit au début de la fonction), ajouter :

```ts
  const client = {
    createFeature: vi.fn().mockResolvedValue({ id: 1 }),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
    ...clientOverrides,
  } as unknown as ItemClient;
```

Et dans `renderConnectedFormWithGeometry` :

```ts
  const client = {
    createFeature: vi.fn().mockResolvedValue({ id: 1 }),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
  } as unknown as ItemClient;
```

Puis ajouter le nouveau test en fin de fichier :

```tsx
test("hides the write buttons once the collection permission resolves to canWrite=false", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "table1", event: "itemSelected", to: "form1", action: "loadRecord" }]);
  const getCollectionPermission = vi.fn().mockResolvedValue(false);
  const { client } = renderConnectedForm({ client: { getCollectionPermission }, bus });
  await waitFor(() => expect(client.getCollectionPermission).toHaveBeenCalledWith("incidents"));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument());
  bus.emit("table1", "itemSelected", { id: 7, properties: { titre: "Fuite existante", gravite: "moyenne" } });
  await screen.findByText(/Modification de l'enregistrement #7/);
  expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
  // Réinitialiser/Annuler restent visibles : ce ne sont pas des actions d'écriture.
  expect(screen.getByRole("button", { name: "Réinitialiser" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Annuler" })).toBeInTheDocument();
});
```

- [ ] **Step 7: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "hides the write buttons"`
Expected: FAIL — `FormComponent` n'appelle pas encore `getCollectionPermission` et affiche toujours « Enregistrer »/« Supprimer » inconditionnellement.

- [ ] **Step 8: Implémenter**

Dans `shell/src/builder/widgets/form.tsx`, dans `FormComponent`, ajouter ces deux déclarations n'importe où après les déclarations d'état existantes (`fields`, `allFields`, `geometryType`, `lon`, `lat`, `values`, `touched`, `serverErrors`, `genericError`, `editingId`, `loadedGeometry`), mais **avant** la mutation `write` qui les consomme :

```ts
  const collectionId = ctx.data?.layer ?? "";
  const permissionQuery = useQuery({
    queryKey: ["collection-permission", collectionId],
    queryFn: () => client.getCollectionPermission(collectionId),
    enabled: collectionId !== "",
  });
  const canWrite = permissionQuery.data ?? true;
```

(`client` est déjà disponible via `useItemClient()`, `useQuery` déjà importé depuis `@tanstack/react-query`.)

Remplacer les usages de `ctx.data?.layer ?? ""` dans `write`/`remove`'s `mutationFn` par `collectionId` (déjà calculé ci-dessus) — dans la mutation `write` :

```ts
  const write = useMutation({
    mutationFn: async (input: { properties: Record<string, unknown>; geometry: unknown | null }) => {
      const feature = { type: "Feature" as const, properties: input.properties, geometry: input.geometry };
      if (editingId !== null) {
        await client.updateFeature(collectionId, String(editingId), feature);
      } else {
        await client.createFeature(collectionId, feature);
      }
    },
  });
```

et dans `remove` :

```ts
  const remove = useMutation({
    mutationFn: () => client.deleteFeature(collectionId, String(editingId)),
  });
```

Dans le JSX, remplacer le bloc des boutons submit/réinitialiser :

```tsx
      <div className="mt-auto flex items-center gap-2">
        {canWrite && (
          <button
            type="submit"
            disabled={write.isPending}
            className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {String(props.submitLabel ?? "Enregistrer")}
          </button>
        )}
        <button type="button" className="rounded border border-slate-300 px-3 py-1.5 text-sm" onClick={resetTo}>
          Réinitialiser
        </button>
      </div>
```

Et le bouton Supprimer dans le bandeau d'édition :

```tsx
      {editingId !== null && (
        <p className="text-xs text-[var(--gs-color-muted)]">
          Modification de l'enregistrement #{String(editingId)}
          <button type="button" className="ml-2 text-xs underline" onClick={resetTo}>Annuler</button>
          {canWrite && (
            <button
              type="button"
              className="ml-2 text-xs text-red-600 underline"
              disabled={remove.isPending}
              onClick={handleDelete}
            >
              Supprimer
            </button>
          )}
        </p>
      )}
```

- [ ] **Step 9: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
Expected: PASS — tous les tests, y compris ceux de SP-4a/4b (le défaut fail-open `?? true` garantit qu'un mock client qui ne stub pas `getCollectionPermission` continue d'afficher les boutons, la requête échouant silencieusement sans jamais résoudre `permissionQuery.data`).

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
cd shell
git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "feat(shell): widget Formulaire — masque ses boutons d'écriture si canWrite=false (SP-4c)"
```

---

## Task 3: Builder — gabarit « Application de saisie »

**Files:**
- Modify: `shell/src/builder/templates.ts` (type `Template`, nouveau gabarit)
- Modify: `shell/src/api/itemClient.ts:` fonction `createConfigItem` (seed `dataSources`/`messages` depuis le template)
- Modify: `shell/src/api/itemClient.test.ts` (ajout d'un test, en fin de fichier)
- Modify: `shell/src/builder/templates.test.ts` (ajout d'un test, en fin de fichier)

**Interfaces:**
- Produces: `Template.dataSources?: DataSource[]`, `Template.messages?: ActionMessage[]` ; gabarit `TEMPLATES` gagne l'entrée `id: "application-de-saisie"`.
- Consumes: `DataSource`/`ActionMessage`/`WidgetItem` (existants, `shell/src/api/types.ts`).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/templates.test.ts`, ajouter en fin de fichier :

```ts
test("application-de-saisie template wires a Formulaire, une Carte et une Table sur la même source", () => {
  const tpl = getTemplate("application-de-saisie")!;
  expect(tpl.kind).toBe("app");
  expect(tpl.dataSources).toHaveLength(1);
  const ds = tpl.dataSources![0];
  expect(ds).toMatchObject({ type: "features", service: "core", layer: "incidents" });
  const widgetTypes = tpl.layout.items.map((i) => i.widget).sort();
  expect(widgetTypes).toEqual(["form", "map", "table"]);
  tpl.layout.items.forEach((item) => {
    if (item.widget === "form" || item.widget === "map" || item.widget === "table") {
      expect(item.props.dataSourceId).toBe(ds.id);
    }
  });
  const formItem = tpl.layout.items.find((i) => i.widget === "form")!;
  expect(formItem.props.submitLabel).toBe("Déclarer l'incident");
  expect(tpl.messages).toHaveLength(1);
  const tableItem = tpl.layout.items.find((i) => i.widget === "table")!;
  expect(tpl.messages![0]).toMatchObject({
    from: tableItem.id, event: "itemSelected", to: formItem.id, action: "loadRecord",
  });
});
```

Dans `shell/src/api/itemClient.test.ts`, ajouter en fin de fichier :

```ts
test("createConfigItem seeds dataSources and messages from a template that defines them", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "application-de-saisie" });
  expect(body.config.dataSources).toHaveLength(1);
  expect(body.config.dataSources[0]).toMatchObject({ type: "features", layer: "incidents" });
  expect(body.config.messages).toHaveLength(1);
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/templates.test.ts src/api/itemClient.test.ts -t "application-de-saisie|seeds dataSources"`
Expected: FAIL — `getTemplate("application-de-saisie")` renvoie `undefined` ; `createConfigItem` ne seed jamais `dataSources`/`messages` depuis un template (toujours `[]`).

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/templates.ts`, étendre le type `Template` :

```ts
import type { ActionMessage, AppLayout, DataSource, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
  layout: AppLayout;
  theme?: Theme;
  dataSources?: DataSource[];
  messages?: ActionMessage[];
};
```

Ajouter, avant `export const TEMPLATES`, le gabarit « Application de saisie » :

```ts
const INCIDENT_DATA_SOURCE_ID = "tpl-incident-ds";

const INCIDENT_APP_DATA_SOURCES: DataSource[] = [
  { id: INCIDENT_DATA_SOURCE_ID, type: "features", service: "core", layer: "incidents", query: {} },
];

const INCIDENT_APP_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    {
      id: "tpl-incident-form", widget: "form", x: 0, y: 0, w: 4, h: 6,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID, fields: [], submitLabel: "Déclarer l'incident", geometryType: null },
    },
    {
      id: "tpl-incident-map", widget: "map", x: 4, y: 0, w: 8, h: 4,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID },
    },
    {
      id: "tpl-incident-table", widget: "table", x: 4, y: 4, w: 8, h: 2,
      props: { dataSourceId: INCIDENT_DATA_SOURCE_ID, columns: [], pageSize: 10 },
    },
  ],
};

const INCIDENT_APP_MESSAGES: ActionMessage[] = [
  { id: "tpl-incident-msg", from: "tpl-incident-table", event: "itemSelected", to: "tpl-incident-form", action: "loadRecord" },
];
```

Ajouter l'entrée dans `TEMPLATES` :

```ts
export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
  {
    id: "application-de-saisie", name: "Application de saisie", kind: "app",
    layout: INCIDENT_APP_LAYOUT, dataSources: INCIDENT_APP_DATA_SOURCES, messages: INCIDENT_APP_MESSAGES,
  },
];
```

Dans `shell/src/api/itemClient.ts`, dans `createConfigItem`, remplacer `dataSources: []`/`messages: []` par le seed depuis le template :

```ts
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: template?.dataSources ?? [],
        layout: template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: template?.messages ?? [],
      };
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/templates.test.ts src/api/itemClient.test.ts`
Expected: PASS (tous les tests des deux fichiers, y compris les préexistants — les deux anciens gabarits ne définissant pas `dataSources`/`messages`, leur seed continue de produire `[]`).

Run: `cd shell && npm run test`
Expected: PASS

Run: `cd shell && npm run build`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd shell
git add src/builder/templates.ts src/builder/templates.test.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): gabarit « Application de saisie » — Formulaire+Carte+Table pré-câblés (SP-4c)"
```

---

## Task 4: E2E — mocks `incidents` + spec « déclarer un incident »

**Files:**
- Modify: `shell/e2e/mocks.ts` (nouvelles routes pour la collection `incidents`)
- Create: `shell/e2e/incident-form.spec.ts`

**Interfaces:**
- Consumes: tout le widget Formulaire (SP-4a/4b/SP-4c Tasks 1-3), le gabarit « Application de saisie » (Task 3).

- [ ] **Step 1: Écrire (étendre) le mock — c'est la « spécification » de cette tâche**

Dans `shell/e2e/mocks.ts`, ajouter à l'intérieur de `mockCore(page)`, après le bloc `**/collections/parcs/items*` existant (avant la fermeture de la fonction) :

```ts
  // Collection "incidents" — schéma introspecté, permission d'écriture, et
  // CRUD complet avec état en mémoire (pour que la Table reflète les écritures
  // du Formulaire au fil du scénario "déclarer un incident").
  const incidentRecords = new Map<string, { properties: Record<string, unknown>; geometry: unknown }>();
  let nextIncidentId = 1;

  await page.route("**/collections/incidents", async (route) => {
    await route.fulfill({
      json: {
        id: "incidents", title: "Incidents", description: "", tableName: "incidents",
        isPublic: false, editable: true, geometryType: null, srid: null, pkColumn: "id",
        canWrite: true,
      },
    });
  });

  await page.route("**/collections/incidents/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "incidents", pk: "id", geometry: null,
        fields: [
          { name: "titre", type: "string", required: true, maxLength: 120 },
          { name: "gravite", type: "enum", required: true, values: ["faible", "moyenne", "haute"] },
        ],
      },
    });
  });

  await page.route("**/collections/incidents/items*", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        json: {
          type: "FeatureCollection",
          features: [...incidentRecords.entries()].map(([id, r]) => ({
            type: "Feature", id: Number(id), properties: r.properties, geometry: r.geometry,
          })),
        },
      });
    } else if (method === "POST") {
      const body = await route.request().postDataJSON();
      const id = String(nextIncidentId++);
      incidentRecords.set(id, { properties: body.properties, geometry: body.geometry });
      await route.fulfill({ status: 201, json: { id: Number(id) } });
    } else {
      await route.fallback();
    }
  });

  await page.route("**/collections/incidents/items/*", async (route) => {
    const method = route.request().method();
    const id = route.request().url().split("/").pop() ?? "";
    if (method === "PUT") {
      const body = await route.request().postDataJSON();
      incidentRecords.set(id, { properties: body.properties, geometry: body.geometry });
      await route.fulfill({ status: 204, body: "" });
    } else if (method === "DELETE") {
      incidentRecords.delete(id);
      await route.fulfill({ status: 204, body: "" });
    } else {
      await route.fallback();
    }
  });
```

- [ ] **Step 2: Écrire la spec E2E qui échoue**

Créer `shell/e2e/incident-form.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("déclarer un incident : créer sans code, créer/voir/modifier/supprimer une entité", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // Créer l'app depuis le gabarit, sans code.
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Déclarer un incident");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Sélectionner le widget Formulaire pré-câblé et charger son schéma.
  await page.getByRole("button", { name: "Sélectionner widget-tpl-incident-form" }).click();
  await page.getByRole("button", { name: "Charger les champs du schéma" }).click();
  await expect(page.getByLabel("Label du champ titre")).toBeVisible();

  // Enregistrer la configuration du builder (bouton du builder, distinct du
  // bouton de soumission du Formulaire — cf. Global Constraints).
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : créer une entité.
  await page.goto("/apps/9");
  await page.getByLabel("titre").fill("Fuite d'eau");
  await page.getByLabel("gravite").selectOption("haute");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();

  // Apparaît dans la Table (rafraîchissement après écriture, SP-4a §5).
  await expect(page.getByText("Fuite d'eau")).toBeVisible();

  // Modifier depuis la sélection Table → Formulaire.
  await page.getByText("Fuite d'eau").click();
  await expect(page.getByText(/Modification de l'enregistrement #1/)).toBeVisible();
  const titreInput = page.getByLabel("titre");
  await titreInput.fill("Fuite d'eau (résolue)");
  await page.getByRole("button", { name: "Déclarer l'incident" }).click();
  await expect(page.getByText("Fuite d'eau (résolue)")).toBeVisible();
  await expect(page.getByText("Fuite d'eau", { exact: true })).toBeHidden();

  // Supprimer (confirmation native auto-acceptée).
  page.on("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByText("Fuite d'eau (résolue)")).toBeHidden();
  await expect(page.getByText(/Modification de l'enregistrement/)).toBeHidden();
});
```

- [ ] **Step 3: Lancer la spec, vérifier l'échec attendu**

Run: `cd shell && npx playwright test incident-form.spec.ts`
Expected: FAIL au premier point qui dépendait des changements de ce plan (typiquement l'absence de `**/collections/incidents/schema` ou le gabarit inexistant, selon que Step 1 a déjà été appliqué). Confirmer que l'échec provient bien de code non encore présent — pas d'une faute de frappe dans les sélecteurs — en relisant le message d'erreur Playwright (élément introuvable nommé).

- [ ] **Step 4: Confirmer le succès**

Run: `cd shell && npx playwright test incident-form.spec.ts`
Expected: PASS

Run: `cd shell && npm run e2e`
Expected: PASS — 14 specs vertes (les 13 existantes + celle-ci).

- [ ] **Step 5: Commit**

```bash
cd shell
git add e2e/mocks.ts e2e/incident-form.spec.ts
git commit -m "test(shell): e2e — scénario complet « déclarer un incident » (SP-4c)"
```

---

## Task 5: E2E — un viewer ne voit pas les boutons d'écriture, une écriture forcée est refusée (403)

**Files:**
- Modify: `shell/e2e/incident-form.spec.ts` (ajout d'un second test, en fin de fichier)

**Interfaces:**
- Consumes: `canWrite` (Tasks 1-2), les mocks `incidents` (Task 4).

- [ ] **Step 1: Écrire la spec qui échoue**

Dans `shell/e2e/incident-form.spec.ts`, ajouter en fin de fichier :

```ts
test("un viewer ne voit pas les boutons d'écriture ; une écriture forcée est refusée (403)", async ({ page }) => {
  await mockCore(page);
  // Surcharge posée APRÈS mockCore : Playwright privilégie la route la plus
  // récemment enregistrée qui matche, donc ceci l'emporte sur le
  // "**/collections/incidents" (canWrite:true) déjà enregistré par mockCore.
  await page.route("**/collections/incidents", async (route) => {
    await route.fulfill({
      json: {
        id: "incidents", title: "Incidents", description: "", tableName: "incidents",
        isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id",
        canWrite: false,
      },
    });
  });
  await page.route("**/collections/incidents/items*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 403, json: { detail: "write access required" } });
    } else {
      await route.fallback();
    }
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("application-de-saisie");
  await dialog.getByLabel("Titre").fill("Déclarer un incident (viewer)");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Déclarer l'incident" })).not.toBeVisible();

  // Écriture forcée (contournement de l'UI, ex. devtools) : le serveur refuse.
  const status = await page.evaluate(async () => {
    const res = await fetch("https://core.test/collections/incidents/items", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "Feature", properties: { titre: "Forcé", gravite: "haute" }, geometry: null }),
    });
    return res.status;
  });
  expect(status).toBe(403);
});
```

- [ ] **Step 2: Lancer la spec, vérifier l'échec attendu**

Run: `cd shell && npx playwright test incident-form.spec.ts -g "un viewer"`
Expected: FAIL avant l'implémentation des Tasks 1-2 de ce plan (bouton toujours visible, `canWrite` inexistant) ; PASS si les Tasks 1-2 sont déjà en place au moment de l'exécution de cette Task 5 (cas normal, exécution séquentielle du plan) — dans ce cas, ce Step sert de non-régression : lancer la spec juste après l'avoir écrite confirme qu'elle passe bien pour la bonne raison (vérifier qu'un `console.log` temporaire ou un breakpoint montre bien `canWrite:false` reçu, pas un faux positif dû à un délai réseau).

- [ ] **Step 3: Confirmer le succès**

Run: `cd shell && npx playwright test incident-form.spec.ts`
Expected: PASS — les deux tests du fichier.

Run: `cd shell && npm run e2e`
Expected: PASS — 14 specs vertes.

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/incident-form.spec.ts
git commit -m "test(shell): e2e — viewer sans boutons d'écriture, 403 sur écriture forcée (SP-4c)"
```

---

## Couverture spec → tâches (auto-vérification)

- §1 SP-4c « Template galerie "Application de saisie" (Formulaire + Carte + Table pré-câblés) » → Task 3.
- §1 SP-4c « spec E2E Playwright "déclarer un incident" (critère d'acceptation complet de la feuille de route) » → Task 4.
- §1 SP-4c « vérification UI viewer (boutons d'écriture masqués, 403 serveur si forcé) » → Tasks 1, 2, 5 (le 403 lui-même était déjà couvert côté cœur avant ce plan — `test_viewer_write_is_403_editor_ok` — Task 5 vérifie l'intégration bout-en-bout shell+cœur, pas une nouvelle capacité serveur).
- §8 critère d'acceptation « une app "déclarer un incident" (formulaire + carte + table) créée dans le builder sans code ; en runtime : créer une entité, la voir apparaître sur la carte et dans la table, la modifier depuis la sélection table→formulaire, la supprimer » → Task 4 (carte non asserted en pixels, cf. Global Constraints — couverte par les tests unitaires SP-4a/4b du widget Carte).
- §8 « un viewer ne voit pas les boutons d'écriture et le serveur refuse ses écritures (403) » → Task 5.
- §9 risques (aucun risque spécifique à SP-4c listé dans la spec au-delà de ceux déjà couverts par SP-4a/4b) → sans objet.
- Élément hors spec littérale, ajouté par ce plan après clarification avec l'utilisateur : l'exposition de `canWrite` (Task 1) est un choix de portée explicite (option « pleine portée » retenue plutôt que « refus serveur seul ») — documenté ici, pas une extension silencieuse.

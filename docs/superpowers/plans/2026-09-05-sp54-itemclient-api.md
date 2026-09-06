# SP-54 — API shell (ItemClient) : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Combler 6 trous de surface `ItemClient`/MCP identifiés par la
revue SP-42 : GAP-38 (schéma AppConfig dupliqué, jamais consommé par le
shell), GAP-65 (`getMe()` tronqué, cache dataset sans TTL), GAP-40 + volet
collections de GAP-47 (recherche hybride des collections jamais exposée),
GAP-47 reste (`query_features` MCP sans `geom_intersects`), GAP-42 + volet
groupes de GAP-65 (créer un groupe, y ajouter un membre), GAP-12 (liens de
partage à échéance, chantier 4.23).

**Architecture:** 7 tâches, dans l'ordre du moins au plus risqué défini par
la spec §8. Chaque tâche pose son filet de test avant de toucher le code
(TDD).

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest (cœur),
TypeScript/React + Vitest (shell), MCP (`mcp.server.fastmcp`).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp54-itemclient-api-design.md` (sections
citées : §1 GAP-42/65-groupes, §2 GAP-65 reste, §3 GAP-40/47-collections,
§4 GAP-47 reste, §5 GAP-38, §6 GAP-12, §7 coordination SP-51, §8 ordre).

## Global Constraints

- **Coordination SP-51 (spec §7) — à lire avant de lancer ce plan ou
  SP-51 en parallèle.** Chevauchement confirmé sur `shell/src/api/base.ts`
  (Tâche 3 de ce plan y ajoute le TTL de `datasetCache` ; SP-51 n'y touche
  pas) et probable sur `shell/src/api/types.ts` (ce plan y ajoute 7
  méthodes `ItemClient` cumulées sur les tâches ; SP-51 y ajoute
  `sampleDataSourceField`, sans rapport fonctionnel).
  **Recommandation : séquencer ce plan et le plan SP-51 (ordre indifférent)
  ou les confier à la même session/agent si une exécution simultanée est
  souhaitée.** Ne pas lancer deux implémenteurs différents en parallèle
  sans l'un des deux garde-fous — précédent CLAUDE.md « Sessions
  concurrentes sur le même arbre ».
- **`ItemClient` reste le sas unique** (règle n°1 CLAUDE.md) : chaque
  méthode ajoutée est additive, aucune signature existante n'est changée
  de façon cassante (`listCollections` gagne un paramètre **optionnel**).
- **Config déclarative** (règle n°2 CLAUDE.md) : un lien de partage à
  échéance est un enregistrement audité, pas un état caché — toute
  décision de révocation passe par une ligne de base, jamais par un
  drapeau en mémoire.
- **TDD systématique**, filet avant code, sur les deux surfaces (cœur +
  shell) à chaque fois qu'une tâche touche les deux.
- **Suite complète rejouée avant de clore chaque tâche** :
  `cd core && uv run pytest` et `cd shell && npx vitest run` (piège
  CLAUDE.md n°6 — jamais un sous-ensemble avant la clôture, même si les
  étapes intermédiaires ciblent un fichier).
- **Toute migration testée sur base non vide, dans les deux sens** (piège
  CLAUDE.md n°8) — Tâche 7 (GAP-12) uniquement, seule tâche de ce plan qui
  ajoute une migration.
- Commits **conventional**, français, un sujet par commit.
- **Régénérer la spec OpenAPI + types TS** dès qu'une route ou un modèle
  de réponse change côté cœur (piège CLAUDE.md n°1) — nécessaire aux
  Tâches 4 (`q` sur `GET /collections`, déjà accepté côté route mais
  jamais documenté dans le schéma généré consommé par le shell), 6, et 7 :

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd shell && npm run gen:api-types
```

- **Conteneur `postgis-test` non tracké par Alembic** : après la migration
  de la Tâche 7, un `ALTER TABLE`/vérification manuelle peut être
  nécessaire sur ce conteneur avant de rejouer la suite complète (CLAUDE.md,
  suivi récurrent).
- **Hors périmètre explicite (spec §9)** : consommation anonyme d'un lien
  de partage, retrait de `getInstanceInfo()`/`useInstanceInfo()`, une
  recherche d'utilisateur non-admin dédiée, un service `sharing/service.py`
  partagé, l'élargissement sémantique de `search_catalog` existant.

---

## Task 1 (GAP-38) : schéma `AppConfig` factorisé + un consommateur shell

Risque : bas. Aucune route nouvelle, comportement HTTP identique (diff
`openapi.json` attendu vide pour cette tâche — seule la Tâche 4 en aval
change réellement une forme de réponse).

**Files:**
- Modify: `core/app/configs/schemas.py` (nouvelle fonction
  `app_config_json_schema()`)
- Modify: `core/app/schemas_routes.py`, `core/app/mcp/tools/__init__.py`
  (les deux appellent la fonction factorisée)
- Modify: `shell/src/api/types.ts` (ajoute `getAppConfigSchema` à
  `ItemClient`), `shell/src/api/domains/apps.ts` (implémentation)
- Test: `core/tests/test_mcp_schema.py` (vérifie toujours la route +
  ajoute un test de non-divergence route/ressource MCP),
  `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `app.configs.schemas.BuilderConfig.model_json_schema()`
  (inchangé).
- Produces: `core.app.configs.schemas::app_config_json_schema() -> dict`,
  `ItemClient.getAppConfigSchema(): Promise<Record<string, unknown>>`.

- [ ] **Step 1 : écrire le test de non-divergence côté cœur (avant la factorisation)**

```python
# core/tests/test_mcp_schema.py — ajouter à la suite du test existant
def test_rest_and_mcp_schema_never_diverge():
    from app.configs.schemas import app_config_json_schema
    from app.schemas_routes import get_app_config_schema

    # La ressource MCP (app/mcp/tools/__init__.py::app_config_schema) et la
    # route REST doivent appeler la même fonction — ce test compare leurs
    # sorties directement, sans dépendre du protocole MCP.
    assert get_app_config_schema() == app_config_json_schema()
```

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (fonction inexistante)**

```bash
cd core && uv run pytest tests/test_mcp_schema.py -v
```

- [ ] **Step 3 : factoriser dans `configs/schemas.py`, appeler depuis les deux points d'entrée**

```python
# core/app/configs/schemas.py — ajouter en fin de fichier
def app_config_json_schema() -> dict:
    """Schéma JSON de BuilderConfig — source unique, consommée par
    GET /schemas/app-config (schemas_routes.py) et la ressource MCP
    schema://app-config (mcp/tools/__init__.py). Les deux existaient
    jusqu'ici en deux implémentations parallèles qui rappelaient chacune
    model_json_schema() indépendamment (GAP-38, SP-42)."""
    return BuilderConfig.model_json_schema()
```

```python
# core/app/schemas_routes.py
from app.configs.schemas import app_config_json_schema

@router.get("/schemas/app-config")
def get_app_config_schema() -> dict:
    return app_config_json_schema()
```

```python
# core/app/mcp/tools/__init__.py
from app.configs.schemas import app_config_json_schema

@server.resource("schema://app-config")
def app_config_schema() -> dict:
    """JSON Schema for AppConfig/DashboardConfig — validate before
    calling create_item or save_app_config."""
    return app_config_json_schema()
```

- [ ] **Step 4 : lancer les tests cœur, vérifier zéro régression**

```bash
cd core && uv run pytest tests/test_mcp_schema.py -v
```

- [ ] **Step 5 : écrire le test shell avant l'ajout de la méthode**

```ts
// shell/src/api/itemClient.test.ts
test("getAppConfigSchema récupère le schéma JSON depuis le cœur", async () => {
  server.use(
    http.get("https://core.test/schemas/app-config", () =>
      HttpResponse.json({ title: "BuilderConfig", type: "object", properties: {} }),
    ),
  );
  const schema = await makeClient().getAppConfigSchema();
  expect(schema.type).toBe("object");
  expect(schema.properties).toBeDefined();
});
```

- [ ] **Step 6 : ajouter la méthode à `ItemClient`/`apps.ts`**

```ts
// shell/src/api/types.ts — interface ItemClient
getAppConfigSchema(): Promise<Record<string, unknown>>;
```

```ts
// shell/src/api/domains/apps.ts
async getAppConfigSchema(): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("GET", "/schemas/app-config");
},
```

Ajouter `"getAppConfigSchema"` au `Pick<ItemClient, ...>` de tête de
fichier (`AppsMethods`).

- [ ] **Step 7 : lancer le test shell, vérifier qu'il passe, puis la suite du fichier**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "getAppConfigSchema"
```

- [ ] **Step 8 : suites complètes**

```bash
cd core && uv run pytest
cd shell && npx vitest run
```

- [ ] **Step 9 : commit**

```bash
git add core/app/configs/schemas.py core/app/schemas_routes.py \
  core/app/mcp/tools/__init__.py core/tests/test_mcp_schema.py \
  shell/src/api/types.ts shell/src/api/domains/apps.ts \
  shell/src/api/itemClient.test.ts
git commit -m "$(cat <<'EOF'
refactor(core,shell): unifie le schéma JSON AppConfig, ajoute un consommateur shell

GAP-38 : GET /schemas/app-config et la ressource MCP schema://app-config
appelaient chacune model_json_schema() indépendamment — même source,
deux points d'implémentation qui pouvaient diverger silencieusement.
Factorise dans app_config_json_schema(), garanti identique par un test
dédié. ItemClient.getAppConfigSchema() donne au shell son premier
consommateur réel de cette route, jusqu'ici testée mais jamais exercée
en pratique.
EOF
)"
```

---

## Task 2 (GAP-65 / getMe) : `Me` porte `id`/`email`/`tenantId`/`capabilities`

Risque : bas. Extension additive d'un type de réponse déjà servi tel quel
par le cœur — aucune route ne change.

**Files:**
- Modify: `shell/src/api/types.ts` (`Me`, ajoute les 4 champs +
  `MeCapabilities`)
- Modify: `shell/src/api/domains/identity.ts` (`getMe()` lit les 4 champs)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `core/app/auth/routes.py::MeResponse` (inchangé — sert déjà
  ces 4 champs).
- Produces: rien de nouveau consommé ailleurs — extension de lecture pure.

- [ ] **Step 1 : écrire le test avant l'extension**

```ts
// shell/src/api/itemClient.test.ts
test("getMe lit id/email/tenantId/capabilities en plus des champs existants", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1", tenantId: "t1", tenantSlug: "acme", username: "alice",
        email: "alice@example.com", firstName: "Alice", lastName: "A",
        role: { id: "r1", name: "Créateur", slug: "creator" },
        privileges: ["maps.manage"], version: "1.2.3",
        capabilities: {
          readOnly: false, etlEnabled: true, exportEnabled: true,
          appExportEnabled: false, tileset3dEnabled: false,
          terrain3dEnabled: false, copilotEnabled: false, adminToolsEnabled: false,
        },
      }),
    ),
  );
  const me = await makeClient().getMe();
  expect(me.id).toBe("u1");
  expect(me.email).toBe("alice@example.com");
  expect(me.tenantId).toBe("t1");
  expect(me.capabilities.etlEnabled).toBe(true);
});
```

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (champs absents du type/lecture)**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "getMe lit id/email"
```

- [ ] **Step 3 : étendre le type `Me` et `getMe()`**

```ts
// shell/src/api/types.ts
export type MeCapabilities = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
  adminToolsEnabled: boolean;
};

export type Me = {
  id: string;
  tenantId: string;
  tenantSlug: string;
  username: string;
  email: string | null;
  firstName: string;
  lastName: string;
  role: RoleSummary;
  privileges: string[];
  version: string;
  capabilities: MeCapabilities;
};
```

```ts
// shell/src/api/domains/identity.ts
async getMe(): Promise<Me> {
  const data = await request<{
    id: string;
    tenantId: string;
    tenantSlug: string;
    username: string;
    email: string | null;
    firstName: string;
    lastName: string;
    role: RoleSummary;
    privileges: string[];
    version: string;
    capabilities: MeCapabilities;
  }>("GET", `/me`);
  return {
    id: data.id,
    tenantId: data.tenantId,
    tenantSlug: data.tenantSlug,
    username: data.username,
    email: data.email,
    firstName: data.firstName,
    lastName: data.lastName,
    role: data.role,
    privileges: data.privileges,
    version: data.version,
    capabilities: data.capabilities,
  };
},
```

- [ ] **Step 4 : lancer le test, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "getMe lit id/email"
```

- [ ] **Step 5 : chercher d'autres tests qui construisent un `Me`/mock à la main (piège de fixture incomplète, cf. spec SP-43 §1.5)**

```bash
grep -rln "role: {" shell/src --include=*.test.ts* | xargs grep -l "username:" 2>/dev/null
grep -rn "mockMe\b" shell/e2e/mocks.ts
```

Si `shell/e2e/mocks.ts::mockMe` existe déjà (précédent SP-30l cité par la
spec SP-43), vérifier qu'il porte déjà les 4 champs — sinon les y ajouter
dans cette même tâche (ne pas laisser un mock E2E redevenir incomplet
comme `mockCollection` l'était avant SP-43 Étape 3).

- [ ] **Step 6 : suites complètes**

```bash
cd shell && npx vitest run
cd shell && npm run e2e
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/api/types.ts shell/src/api/domains/identity.ts \
  shell/src/api/itemClient.test.ts shell/e2e/mocks.ts
git commit -m "$(cat <<'EOF'
feat(shell): getMe() lit id/email/tenantId/capabilities

GAP-65 (1/3) : GET /me sert ces 4 champs depuis longtemps (MeResponse,
core/app/auth/routes.py) mais Me/getMe() ne les déclarait ni ne les
lisait — perdus silencieusement. capabilities reste un doublon
délibéré de GET /instance (documenté côté cœur, test de non-divergence
dédié) : useInstanceInfo() n'est pas retiré, cette tâche ajoute
seulement la lecture manquante.
EOF
)"
```

---

## Task 3 (GAP-65 / cache dataset) : TTL + invalidation manuelle

Risque : bas à moyen. Ne doit rien changer pour les appelants existants
(`resolveDataset` reste transparente pour `getDatasetConfig`/
`queryDataSource`/`exportDataSource`/`featuresUrl`, tous inchangés).

**Files:**
- Modify: `shell/src/api/base.ts` (`datasetCache` porte un TTL,
  `invalidateDatasetCache` ajoutée à `ItemClientBase`)
- Modify: `shell/src/api/types.ts` (`invalidateDatasetCache` ajoutée à
  `ItemClient`)
- Modify: `shell/src/api/domains/datasets.ts` (expose la méthode, la
  câble à l'objet retourné)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `Date.now()` (horloge injectable en test via `vi.useFakeTimers()`,
  patron Vitest déjà présent ailleurs dans ce dépôt — vérifier avant
  d'écrire le test, ne pas supposer).
- Produces: `ItemClient.invalidateDatasetCache(pk?: string): void`.

- [ ] **Step 1 : écrire le test de TTL avant la modification**

```ts
// shell/src/api/itemClient.test.ts
test("resolveDataset (via getDatasetConfig) refait un fetch après expiration du TTL", async () => {
  vi.useFakeTimers();
  try {
    let calls = 0;
    server.use(
      http.get("https://core.test/configs/by-item/ds1", () => {
        calls += 1;
        return HttpResponse.json({
          id: "cfg", itemId: "ds1", kind: "dataset",
          config: { kind: "dataset", dataset: { source: "collection", collectionId: "communes", columns: {} } },
        });
      }),
    );
    const client = makeClient();
    await client.getDatasetConfig("ds1");
    expect(calls).toBe(1);
    await client.getDatasetConfig("ds1"); // encore dans le TTL
    expect(calls).toBe(1);
    vi.advanceTimersByTime(5 * 60 * 1000 + 1);
    await client.getDatasetConfig("ds1"); // TTL expiré
    expect(calls).toBe(2);
  } finally {
    vi.useRealTimers();
  }
});

test("invalidateDatasetCache force un nouveau fetch avant expiration du TTL", async () => {
  let calls = 0;
  server.use(
    http.get("https://core.test/configs/by-item/ds1", () => {
      calls += 1;
      return HttpResponse.json({
        id: "cfg", itemId: "ds1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "communes", columns: {} } },
      });
    }),
  );
  const client = makeClient();
  await client.getDatasetConfig("ds1");
  client.invalidateDatasetCache("ds1");
  await client.getDatasetConfig("ds1");
  expect(calls).toBe(2);
});
```

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "TTL\|invalidateDatasetCache"
```

- [ ] **Step 3 : ajouter le TTL et l'invalidation dans `base.ts`**

```ts
// shell/src/api/base.ts
const DATASET_CACHE_TTL_MS = 5 * 60 * 1000;

type CachedDataset = { value: ResolvedDataset; expiresAt: number };
const datasetCacheInternal = new Map<string, CachedDataset>();

// datasetCache exposé par ItemClientBase garde la forme Map<string,
// ResolvedDataset> attendue par les call sites existants qui écrivent
// directement dedans (createDatasetItem/saveDatasetConfig dans
// datasets.ts) : on garde une Map "vue" synchronisée plutôt que de
// changer le type public, pour ne rien casser côté domains/datasets.ts
// dans cette tâche.
```

**⚠️ Note de conception, à trancher au Step 3, ne pas deviner** : deux
approches possibles pour ne pas casser `datasets.ts::createDatasetItem`/
`saveDatasetConfig`, qui écrivent aujourd'hui directement
`datasetCache.set(pk, resolved)` (une `ResolvedDataset` nue, pas un
`{value, expiresAt}`) :

(a) Garder `datasetCache: Map<string, ResolvedDataset>` **inchangée** dans
`ItemClientBase`, et ajouter un **second** Map interne, privé à `base.ts`
(`expiryByPk: Map<string, number>`), consulté uniquement par
`resolveDataset()` pour décider si l'entrée de `datasetCache` est encore
valide — un `set()` externe (depuis `datasets.ts`) ne pose jamais
d'expiration, ce qui est correct : une écriture fraîche après une
sauvegarde réussie n'a pas besoin d'expirer immédiatement.

(b) Changer le type de `datasetCache` lui-même vers
`Map<string, CachedDataset>`, et mettre à jour les deux call sites de
`datasets.ts` pour écrire `{ value: resolved, expiresAt: Date.now() +
DATASET_CACHE_TTL_MS }`.

**Retenu : (a)** — surface de modification plus petite (un seul fichier,
`base.ts`, au lieu de deux), et le type public `ItemClientBase.
datasetCache` ne change pas, donc aucun risque de rupture pour un
consommateur qui l'utiliserait autrement (recherche à faire au Step 3.1
avant de continuer, pour confirmer qu'aucun autre fichier ne lit
`datasetCache` directement en dehors de `base.ts`/`datasets.ts`).

```bash
grep -rn "datasetCache" shell/src --include=*.ts | grep -v test
```

```ts
// shell/src/api/base.ts — implémentation retenue (a)
const DATASET_CACHE_TTL_MS = 5 * 60 * 1000;
const datasetCacheExpiry = new Map<string, number>();

async function resolveDataset(pk: string): Promise<ResolvedDataset> {
  const cached = datasetCache.get(pk);
  const expiresAt = datasetCacheExpiry.get(pk);
  if (cached && expiresAt !== undefined && Date.now() < expiresAt) return cached;
  const data = await request<{ /* ... inchangé ... */ }>("GET", `/configs/by-item/${pk}`);
  const dataset = data.config?.dataset;
  if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
  const resolved: ResolvedDataset = { /* ... inchangé ... */ };
  datasetCache.set(pk, resolved);
  datasetCacheExpiry.set(pk, Date.now() + DATASET_CACHE_TTL_MS);
  return resolved;
}

function invalidateDatasetCache(pk?: string): void {
  if (pk === undefined) {
    datasetCache.clear();
    datasetCacheExpiry.clear();
    return;
  }
  datasetCache.delete(pk);
  datasetCacheExpiry.delete(pk);
}
```

Ajouter `invalidateDatasetCache` à `ItemClientBase` (type + objet
retourné par `createBase`).

- [ ] **Step 4 : exposer la méthode sur `ItemClient`**

```ts
// shell/src/api/types.ts — interface ItemClient
invalidateDatasetCache(pk?: string): void;
```

```ts
// shell/src/api/domains/datasets.ts — ajouter à DatasetsMethods et à l'objet retourné
invalidateDatasetCache(pk?: string): void {
  base.invalidateDatasetCache(pk);
},
```

- [ ] **Step 5 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "TTL\|invalidateDatasetCache"
```

- [ ] **Step 6 : suite complète du fichier + suite complète shell**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts
cd shell && npx vitest run
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/api/base.ts shell/src/api/types.ts \
  shell/src/api/domains/datasets.ts shell/src/api/itemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(shell): TTL + invalidation manuelle pour le cache dataset

GAP-65 (2/3) : datasetCache n'expirait jamais et n'était rafraîchi que
par une écriture passant par ce même ItemClient — un dataset modifié
ailleurs (autre onglet, pipeline en tâche de fond) restait stale
indéfiniment. Ajoute un TTL de 5 minutes et
ItemClient.invalidateDatasetCache(pk?), sans changer le type public
datasetCache ni les deux call sites existants qui y écrivent
directement (createDatasetItem/saveDatasetConfig).
EOF
)"
```

---

## Task 4 (GAP-40 + volet collections de GAP-47) : recherche hybride des collections

Risque : bas. Le paramètre `q` existe déjà de bout en bout côté cœur
(`list_visible_collections`, route `GET /collections`) — uniquement des
consommateurs à ajouter.

**Files:**
- Modify: `shell/src/api/types.ts` (`listCollections(params?: { q?:
  string })`)
- Modify: `shell/src/api/domains/collectionsAdmin.ts` (relaie `q`)
- Modify: `shell/src/pages/CollectionsAdminPage.tsx` (champ de recherche)
- Modify: `core/app/mcp/tools/catalog.py` (nouvel outil
  `search_collections`)
- Test: `shell/src/api/itemClient.test.ts`,
  `shell/src/pages/CollectionsAdminPage.test.tsx`,
  `core/tests/test_mcp_tools_catalog.py` (nom à vérifier avant d'écrire,
  ne pas supposer)

**Interfaces:**
- Consumes: `core/app/collections/repository.py::list_visible_collections`
  (inchangé — déjà paramétré par `q`).
- Produces: `ItemClient.listCollections(params?: { q?: string }):
  Promise<CollectionAdmin[]>` (signature élargie, rétrocompatible), outil
  MCP `search_collections(q, page, pageSize)`.

- [ ] **Step 1 : localiser le nom exact du fichier de test MCP existant du domaine catalog**

```bash
find core/tests -iname "*mcp*catalog*" -o -iname "*mcp_tools_catalog*"
grep -rln "search_catalog\|query_features" core/tests/*.py
```

Utiliser le(s) nom(s) réels trouvés — ne pas deviner
`test_mcp_tools_catalog.py`.

- [ ] **Step 2 : écrire le test cœur du nouvel outil MCP (avant de l'ajouter)**

```python
# core/tests/<fichier trouvé au Step 1>.py — nouveau test
@pytest.mark.asyncio
async def test_search_collections_returns_hybrid_ranked_collections(mcp_client, seeded_collections):
    # Adapter aux fixtures réelles du fichier (patron déjà utilisé par les
    # tests existants de search_catalog dans ce même fichier) — vérifier
    # le nom exact de la fixture qui seede des collections avant d'écrire.
    result = await mcp_client.call_tool("search_collections", {"q": "commune"})
    assert any(c["title"].lower().startswith("commune") for c in result["items"])
```

Lire d'abord 1-2 tests existants de `search_catalog` dans ce fichier pour
calquer exactement le patron de fixture/assertion (client MCP de test,
forme de la réponse) avant d'écrire celui-ci.

- [ ] **Step 3 : lancer le test, vérifier qu'il échoue (outil inexistant)**

- [ ] **Step 4 : ajouter `search_collections` à `mcp/tools/catalog.py`**

```python
# core/app/mcp/tools/catalog.py — imports supplémentaires
from app.collections import repository as collections_repo
from app.roles.privileges import Privilege
from app.roles.repository import has_privilege

class CollectionSearchResult(BaseModel):  # nécessite `from pydantic import BaseModel`
    id: str
    title: str
    description: str

# à l'intérieur de register(server, session_factory) :
@server.tool()
async def search_collections(
    ctx: Context, q: str | None = None, page: int = 1, pageSize: int = 12
) -> list[CollectionSearchResult]:
    """Search collections (hybrid trigram + vector ranking on q, same
    mechanism as search_catalog for items) — collections were never
    searchable from an agent before this tool (GAP-40/47)."""
    access_token = get_access_token()
    with request_scoped_session(session_factory) as session:
        user = resolve_actor(session, access_token)
        can_see_all = has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        cols = collections_repo.list_visible_collections(
            session,
            tenant_id=user.tenant_id,
            user_id=user.id,
            can_see_all=can_see_all,
            q=q,
        )
        start = (page - 1) * pageSize
        page_cols = cols[start : start + pageSize]
        return [
            CollectionSearchResult(id=c.id, title=c.title, description=c.description)
            for c in page_cols
        ]
```

Vérifier l'import exact de `has_privilege` (`core/app/roles/repository.py`
ou `core/app/roles/guards.py` — confirmé `core/app/collections/routes.py`
l'importe depuis un de ces deux modules, à lire avant d'écrire l'import).

- [ ] **Step 5 : lancer le test MCP, vérifier qu'il passe, puis la suite cœur**

```bash
cd core && uv run pytest tests/ -k "search_collections"
cd core && uv run pytest
```

- [ ] **Step 6 : régénérer OpenAPI/types TS (nouvel outil MCP n'a pas de route REST — diff attendu vide côté OpenAPI, mais confirmer)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

- [ ] **Step 7 : écrire le test shell avant d'élargir `listCollections`**

```ts
// shell/src/api/itemClient.test.ts
test("listCollections relaie q en paramètre de recherche", async () => {
  server.use(
    http.get("https://core.test/collections", ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("q")).toBe("commune");
      return HttpResponse.json({ collections: [] });
    }),
  );
  await makeClient().listCollections({ q: "commune" });
});

test("listCollections sans paramètre reste rétrocompatible", async () => {
  server.use(
    http.get("https://core.test/collections", ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.has("q")).toBe(false);
      return HttpResponse.json({ collections: [] });
    }),
  );
  await makeClient().listCollections();
});
```

- [ ] **Step 8 : lancer les tests, vérifier qu'ils échouent, puis élargir la signature**

```ts
// shell/src/api/types.ts
listCollections(params?: { q?: string }): Promise<CollectionAdmin[]>;
```

```ts
// shell/src/api/domains/collectionsAdmin.ts
async listCollections(params?: { q?: string }): Promise<CollectionAdmin[]> {
  const qs = params?.q ? `?q=${encodeURIComponent(params.q)}` : "";
  const data = await request<{ collections: CollectionAdmin[] }>("GET", `/collections${qs}`);
  return data.collections ?? [];
},
```

- [ ] **Step 9 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "listCollections"
```

- [ ] **Step 10 : ajouter un champ de recherche dans `CollectionsAdminPage.tsx`**

```bash
sed -n '1,40p' shell/src/pages/CollectionsAdminPage.tsx
sed -n '1,20p' shell/src/api/domains/collectionsAdmin.hooks.ts
```

Élargir `useCollectionsAdmin` pour accepter `{ q?: string }` (même patron
que `useGroups({ enabled })` existant), câbler un état local `q` +
`<input role="searchbox" aria-label="Rechercher une collection…">` (même
patron que `LayerPicker.tsx:103-111`), test dédié dans
`CollectionsAdminPage.test.tsx` avant l'implémentation (TDD, ne pas
inverser l'ordre).

- [ ] **Step 11 : suites complètes**

```bash
cd core && uv run pytest
cd shell && npx vitest run
cd shell && npm run e2e
```

- [ ] **Step 12 : commit**

```bash
git add core/app/mcp/tools/catalog.py core/tests/ \
  shell/src/api/types.ts shell/src/api/domains/collectionsAdmin.ts \
  shell/src/api/domains/collectionsAdmin.hooks.ts \
  shell/src/pages/CollectionsAdminPage.tsx \
  shell/src/pages/CollectionsAdminPage.test.tsx \
  shell/src/api/itemClient.test.ts core/openapi.json \
  shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core,shell): recherche hybride des collections (shell + MCP)

GAP-40/47 : list_visible_collections() implémente déjà la recherche
RRF trigram+vecteur derrière q, et GET /collections l'accepte déjà —
le trou était entièrement côté consommateur. listCollections(params?)
relaie q (rétrocompatible), CollectionsAdminPage gagne un champ de
recherche, et search_collections (MCP) donne enfin à un agent la
jumelle collections de search_catalog (qui exclut les collections par
design, docstring inchangée).
EOF
)"
```

---

## Task 5 (GAP-47 reste) : `query_features` (MCP) relaie `geom_intersects`

Risque : bas. Paramètre déjà supporté par `select_features()` — relais
pur, même validation d'erreur que la route REST.

**Files:**
- Modify: `core/app/mcp/tools/catalog.py` (`query_features` gagne
  `geomIntersects`)
- Test: fichier trouvé à la Tâche 4 Step 1

**Interfaces:**
- Consumes: `core/app/features/repository.py::select_features(...,
  geom_intersects=...)` (inchangé), `FilterError` (déjà importé dans ce
  fichier).
- Produces: rien de nouveau — extension de paramètre sur un outil
  existant.

- [ ] **Step 1 : écrire le test avant l'extension**

```python
@pytest.mark.asyncio
async def test_query_features_relays_geom_intersects(mcp_client, seeded_collection_with_polygon):
    result = await mcp_client.call_tool(
        "query_features",
        {
            "collectionId": "communes",
            "geomIntersects": {"type": "Point", "coordinates": [2.35, 48.85]},
        },
    )
    assert len(result["features"]) >= 1
```

Adapter à la fixture réelle (une collection avec au moins une géométrie
connue qui intersecte le point de test) — lire les fixtures existantes du
fichier avant d'inventer une géométrie.

- [ ] **Step 2 : lancer le test, vérifier qu'il échoue (paramètre ignoré/inexistant)**

- [ ] **Step 3 : ajouter `geomIntersects` à `query_features`**

```python
# core/app/mcp/tools/catalog.py
@server.tool()
async def query_features(
    ctx: Context,
    collectionId: str,
    bbox: str | None = None,
    geomIntersects: dict | None = None,
    filters: dict[str, str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """... (docstring existante) + geomIntersects: a GeoJSON geometry
    object (already parsed, unlike the REST route's query-string form) —
    relayed to select_features exactly like bbox/filters."""
    access_token = get_access_token()
    with request_scoped_session(session_factory) as session:
        user = resolve_actor(session, access_token)
        col = require_collection_read(session, user=user, collection_id=collectionId)
        try:
            info = introspect_table(session, col.table_name)
        except TableNotFound as exc:
            raise ValueError("collection backing table not found") from exc
        except UnsupportedTable as exc:
            raise ValueError(exc.reason) from exc
        parsed_bbox = _parse_bbox_tuple(bbox) if bbox else None
        try:
            with rls_scope(session, col.tenant_id):
                page = select_features(
                    session,
                    info,
                    limit=min(limit, 1000),
                    offset=offset,
                    bbox=parsed_bbox,
                    geom_intersects=geomIntersects,
                    filters=filters or None,
                )
        except FilterError as exc:
            raise ValueError(f"unknown filter field: {exc.field}") from exc
        return {
            "type": "FeatureCollection",
            "features": page.features,
            "numberMatched": page.number_matched,
            "numberReturned": page.number_returned,
        }
```

- [ ] **Step 4 : lancer le test, vérifier qu'il passe, puis la suite cœur**

```bash
cd core && uv run pytest tests/ -k "query_features"
cd core && uv run pytest
```

- [ ] **Step 5 : commit**

```bash
git add core/app/mcp/tools/catalog.py core/tests/
git commit -m "$(cat <<'EOF'
feat(core): query_features (MCP) relaie geom_intersects

GAP-47 : select_features() supporte déjà l'intersection géométrique,
et la route REST équivalente la relaie déjà — query_features (MCP) ne
proposait qu'un bbox grossier. Un agent peut désormais reproduire le
filtre spatial exact dont dépend le cross-filter carte côté produit.
EOF
)"
```

---

## Task 6 (GAP-42 + volet groupes de GAP-65) : créer un groupe, ajouter un membre

Risque : moyen. Routes cœur déjà testées ; surface neuve côté shell (UI +
2 méthodes `ItemClient`) et MCP (3 outils). Piège à respecter : `add_member`
ne réussit que pour le créateur du groupe (404 sinon, comportement
délibéré, ne pas le masquer).

**Files:**
- Modify: `shell/src/api/types.ts` (`createGroup`, `addGroupMember`)
- Modify: `shell/src/api/domains/items.ts` (implémentation, à côté de
  `listGroups`)
- Modify: `shell/src/shell/ShareForm.tsx` (formulaire de création de
  groupe + contrôle d'ajout de membre)
- Modify: `core/app/mcp/tools/sharing.py` (`list_groups`, `create_group`,
  `add_group_member`)
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/shell/ShareForm.test.tsx`
  (créer si absent — vérifier d'abord), `core/tests/test_mcp_tools_sharing.py`

- [ ] **Step 1 : écrire le test cœur des 3 nouveaux outils MCP (avant de les ajouter)**

```python
# core/tests/test_mcp_tools_sharing.py
@pytest.mark.asyncio
async def test_create_group_then_add_member_via_mcp(mcp_client, other_tenant_user):
    created = await mcp_client.call_tool("create_group", {"name": "Équipe SIG"})
    assert created["name"] == "Équipe SIG"
    groups = await mcp_client.call_tool("list_groups", {})
    assert any(g["id"] == created["id"] for g in groups)
    await mcp_client.call_tool(
        "add_group_member", {"groupId": created["id"], "userId": other_tenant_user.id}
    )


@pytest.mark.asyncio
async def test_add_group_member_by_non_creator_raises(mcp_client, foreign_group):
    with pytest.raises(ValueError):
        await mcp_client.call_tool(
            "add_group_member", {"groupId": foreign_group.id, "userId": "someone"}
        )
```

Adapter aux fixtures réelles du fichier (`mcp_client`, utilisateur d'un
autre tenant/un groupe créé par quelqu'un d'autre) — lire les tests
existants de `get_sharing`/`set_sharing` dans ce même fichier avant
d'inventer des noms de fixture.

- [ ] **Step 2 : lancer les tests, vérifier qu'ils échouent (outils inexistants)**

- [ ] **Step 3 : ajouter les 3 outils à `mcp/tools/sharing.py`**

```python
# core/app/mcp/tools/sharing.py — imports supplémentaires
from app.audit.writer import write_audit
from app.sharing import repository as sharing_repo


class GroupRead(BaseModel):  # nécessite `from pydantic import BaseModel`
    id: str
    name: str


# à l'intérieur de register(server, session_factory) :
@server.tool()
async def list_groups(ctx: Context) -> list[GroupRead]:
    """List sharing groups for the caller's tenant — mirrors GET /groups."""
    access_token = get_access_token()
    with request_scoped_session(session_factory) as session:
        user = resolve_actor(session, access_token)
        return [
            GroupRead(id=g.id, name=g.name)
            for g in sharing_repo.list_groups(session, tenant_id=user.tenant_id)
        ]


@server.tool()
async def create_group(ctx: Context, name: str) -> GroupRead:
    """Create a sharing group — mirrors POST /groups."""
    if is_read_only_mode():
        raise ValueError("Mode démo : lecture seule, écritures désactivées.")
    access_token = get_access_token()
    with request_scoped_session(session_factory) as session:
        user = resolve_actor(session, access_token)
        group = sharing_repo.create_group(
            session, tenant_id=user.tenant_id, name=name, created_by=user.id
        )
        write_audit(
            session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
            action="group.create", object_type="group", object_id=group.id,
            payload={"name": name},
        )
        return GroupRead(id=group.id, name=group.name)


@server.tool()
async def add_group_member(ctx: Context, groupId: str, userId: str) -> None:
    """Add a member to a sharing group — mirrors POST /groups/{id}/members.
    Only the group's creator may add a member (repository-enforced) —
    raises rather than silently no-op-ing on a foreign group."""
    if is_read_only_mode():
        raise ValueError("Mode démo : lecture seule, écritures désactivées.")
    access_token = get_access_token()
    with request_scoped_session(session_factory) as session:
        user = resolve_actor(session, access_token)
        ok = sharing_repo.add_member(
            session, tenant_id=user.tenant_id, group_id=groupId, user_id=userId, caller_id=user.id,
        )
        if not ok:
            raise ValueError("group or user not found, or you are not the group's creator")
        write_audit(
            session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
            action="group.add_member", object_type="group", object_id=groupId,
            payload={"userId": userId},
        )
```

- [ ] **Step 4 : lancer les tests MCP, vérifier qu'ils passent, puis la suite cœur**

```bash
cd core && uv run pytest tests/test_mcp_tools_sharing.py -v
cd core && uv run pytest
```

- [ ] **Step 5 : écrire les tests shell avant les nouvelles méthodes `ItemClient`**

```ts
// shell/src/api/itemClient.test.ts
test("createGroup crée un groupe (POST /groups)", async () => {
  server.use(
    http.post("https://core.test/groups", async ({ request }) => {
      const body = (await request.json()) as { name: string };
      expect(body.name).toBe("Équipe SIG");
      return HttpResponse.json({ id: "g1", name: "Équipe SIG" }, { status: 201 });
    }),
  );
  const group = await makeClient().createGroup("Équipe SIG");
  expect(group).toEqual({ id: "g1", title: "Équipe SIG" });
});

test("addGroupMember pose un message clair sur un 404", async () => {
  server.use(
    http.post("https://core.test/groups/g1/members", () =>
      HttpResponse.json({ detail: "group or user not found" }, { status: 404 }),
    ),
  );
  await expect(makeClient().addGroupMember("g1", "u2")).rejects.toThrow(
    /groupe.*n'existe pas.*créateur/i,
  );
});
```

- [ ] **Step 6 : lancer les tests, vérifier qu'ils échouent**

- [ ] **Step 7 : ajouter les 2 méthodes**

```ts
// shell/src/api/types.ts — interface ItemClient
createGroup(name: string): Promise<Group>;
addGroupMember(groupId: string, userId: string): Promise<void>;
```

```ts
// shell/src/api/domains/items.ts
async createGroup(name: string): Promise<Group> {
  const data = await request<{ id: string; name: string }>("POST", `/groups`, { name });
  return { id: data.id, title: data.name };
},

async addGroupMember(groupId: string, userId: string): Promise<void> {
  try {
    await request<void>("POST", `/groups/${groupId}/members`, { userId });
  } catch (err) {
    if (err instanceof Error && err.message.includes("404")) {
      throw new Error(
        "Ce groupe n'existe pas, ou vous n'en êtes pas le créateur — seul le créateur d'un groupe peut y ajouter un membre.",
      );
    }
    throw err;
  }
},
```

Ajouter `"createGroup"`/`"addGroupMember"` au `Pick<ItemClient, ...>` de
tête de fichier.

- [ ] **Step 8 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/api/itemClient.test.ts -t "createGroup\|addGroupMember"
```

- [ ] **Step 9 : lire `ShareForm.tsx` et son test existant (s'il existe), écrire les tests UI avant l'ajout**

```bash
find shell/src/shell -iname "ShareForm.test.tsx"
```

```ts
// shell/src/shell/ShareForm.test.tsx
test("crée un nouveau groupe depuis le formulaire de partage", async () => {
  const createGroup = vi.fn().mockResolvedValue({ id: "g2", title: "Nouveau" });
  // ... render avec un ItemClient mocké portant createGroup ...
  fireEvent.change(screen.getByLabelText("Nom du nouveau groupe"), { target: { value: "Nouveau" } });
  fireEvent.click(screen.getByRole("button", { name: "Créer le groupe" }));
  await waitFor(() => expect(createGroup).toHaveBeenCalledWith("Nouveau"));
});

test("ajoute un membre à un groupe existant, affiche l'erreur si non-créateur", async () => {
  const addGroupMember = vi.fn().mockRejectedValue(new Error("Ce groupe n'existe pas, ou vous n'en êtes pas le créateur..."));
  // ... render ...
  fireEvent.change(screen.getByLabelText(/identifiant utilisateur/i), { target: { value: "u2" } });
  fireEvent.click(screen.getByRole("button", { name: /ajouter un membre/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/créateur/i);
});
```

- [ ] **Step 10 : lancer les tests, vérifier qu'ils échouent, puis ajouter l'UI dans `ShareForm.tsx`**

Ajouter, à la suite de la liste des groupes existants : un champ
« Nom du nouveau groupe » + bouton « Créer le groupe » (invalide la
`useGroups()` query React Query après succès, patron déjà établi ailleurs
dans ce dépôt pour une création suivie d'un rafraîchissement de liste —
vérifier le patron exact, ex. `queryClient.invalidateQueries` dans un
hook `useCreateGroup`, symétrique de `useCreateCollection` déjà présent
dans `collectionsAdmin.hooks.ts`) ; et, par groupe, un champ « Identifiant
utilisateur » + bouton « Ajouter un membre », avec l'aide contextuelle
notée en spec §1.2 (« l'auteur du groupe uniquement peut y ajouter un
membre »).

- [ ] **Step 11 : lancer les tests, vérifier qu'ils passent, puis la suite du fichier**

```bash
cd shell && npx vitest run src/shell/ShareForm.test.tsx
```

- [ ] **Step 12 : suites complètes**

```bash
cd core && uv run pytest
cd shell && npx vitest run
cd shell && npm run e2e
```

- [ ] **Step 13 : commit**

```bash
git add core/app/mcp/tools/sharing.py core/tests/test_mcp_tools_sharing.py \
  shell/src/api/types.ts shell/src/api/domains/items.ts \
  shell/src/api/domains/items.hooks.ts shell/src/shell/ShareForm.tsx \
  shell/src/shell/ShareForm.test.tsx shell/src/api/itemClient.test.ts
git commit -m "$(cat <<'EOF'
feat(core,shell): créer un groupe de partage et y ajouter un membre

GAP-42/65 : les routes POST /groups et POST /groups/{id}/members
existaient et étaient testées côté cœur, mais aucune UI/MCP ne les
exposait — ShareForm.tsx ne pouvait qu'afficher des groupes déjà créés
hors produit. Ajoute createGroup/addGroupMember (ItemClient) et
create_group/add_group_member/list_groups (MCP), calqués directement
sur app.sharing.repository (même patron que la route REST, pas de
service partagé créé). add_member reste réservé au créateur du groupe
(404 si non — comportement délibéré, message clair côté shell plutôt
que masqué) ; le formulaire demande un userId exact, GET /users étant
admin-only (ADMIN_USERS_MANAGE), indisponible à un partageur ordinaire.
EOF
)"
```

---

## Task 7 (GAP-12) : liens de partage à échéance

Risque : le plus élevé de ce plan — nouvelle table, migration, nouveau
mécanisme de jeton révocable (premier du dépôt à combiner TTL **et**
révocation avant expiration, cf. spec §6.1).

**Files:**
- Create: `core/alembic/versions/0035_share_links.py`, `core/app/sharing/
  share_links.py` (jeton, calqué sur `auth/export_tokens.py`)
- Modify: `core/app/sharing/models.py` (`ShareLink`), `core/app/sharing/
  repository.py` (create/list/revoke/resolve), `core/app/sharing/
  routes.py` (3 routes)
- Modify: `shell/src/api/types.ts`, `shell/src/api/domains/items.ts` (ou
  un nouveau `domains/shareLinks.ts` si la taille le justifie — à trancher
  au Step 6, patron déjà établi par le découpage SP-43 : un domaine par
  responsabilité cohérente)
- Modify: `shell/src/shell/ShareForm.tsx` (section « Liens à échéance »)
- Test: `core/tests/test_share_links_repository.py`,
  `core/tests/test_share_links_routes.py`,
  `core/tests/test_share_links_migration_alembic.py` (patron
  `test_metadata_migration_alembic.py`, upgrade→insert→downgrade→upgrade
  sur base non vide, piège CLAUDE.md n°8), `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: patron `core/app/auth/export_tokens.py` (JWT HS256, TTL,
  distinction absence-de-secret vs jeton-invalide → 401 jamais 500) —
  **adapté**, pas recopié : TTL configurable par appelant (jours, pas une
  constante ~2min), claims incluent l'`id` de la ligne `share_link` pour
  permettre la vérification de révocation en base à chaque résolution.
- Produces: `core/app/sharing/share_links.py::mint_share_link_token(*,
  share_link_id, tenant_id, item_id, ttl_seconds) -> str`,
  `decode_share_link_token(token) -> ShareLinkTokenClaims`.

- [ ] **Step 1 : localiser le secret à utiliser (nouvelle variable d'env ou réutilisation)**

```bash
grep -n "CORE_EXPORT_TOKEN_SECRET" core/app/**/*.py core/.env.example 2>/dev/null
```

**Décision, à trancher avant le Step 2** : ne pas réutiliser
`CORE_EXPORT_TOKEN_SECRET` (secrets à portée fonctionnelle distincte,
mélanger les deux rendrait une rotation de l'un impossible sans invalider
l'autre) — nouvelle variable `CORE_SHARE_LINK_TOKEN_SECRET`, même patron
de lecture (`os.environ[...]`, `KeyError` → 401 jamais 500), à ajouter à
`.env.example` et à `core/tests/test_deployability.py` (grep de ce
fichier pour le patron exact d'ajout d'une variable documentée — piège
CLAUDE.md déjà payé une fois sur `.env.example` incomplet pour
`VITE_AUTH_MODE`).

- [ ] **Step 2 : écrire le test de migration (avant de créer la table)**

```python
# core/tests/test_share_links_migration_alembic.py
# Patron : test_metadata_migration_alembic.py (throwaway_database_url,
# upgrade -> INSERT une ligne -> downgrade -> upgrade, sur base non vide
# dans les deux sens, piège CLAUDE.md n°8).
def test_share_link_migration_upgrade_downgrade_upgrade_on_non_empty_db(throwaway_database_url):
    ...
```

- [ ] **Step 3 : lancer le test, vérifier qu'il échoue (migration inexistante)**

- [ ] **Step 4 : écrire la migration + le modèle**

```python
# core/alembic/versions/0035_share_links.py
"""share_link table — GAP-12, chantier 4.23."""
def upgrade() -> None:
    op.create_table(
        "share_link",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("tenant_id", sa.String, nullable=False, index=True),
        sa.Column("item_id", sa.String, nullable=False, index=True),
        sa.Column("created_by", sa.String, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("share_link")
```

```python
# core/app/sharing/models.py — ajouter
class ShareLink(Base):
    __tablename__ = "share_link"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

Vérifier le nom exact de la base déclarative (`from app.db import Base`,
même import que les autres modèles de ce module) avant d'écrire — ne pas
deviner (piège CLAUDE.md n°3, cf. spec SP-43 Tâche 1 Step 1 qui a dû
faire la même vérification).

- [ ] **Step 5 : lancer le test de migration dans les deux sens, sur base non vide**

```bash
cd core && uv run pytest tests/test_share_links_migration_alembic.py -v
```

- [ ] **Step 6 : écrire les tests du jeton (avant `share_links.py`)**

```python
# core/tests/test_share_links_repository.py (ou un fichier dédié
# test_share_link_tokens.py — trancher selon la taille finale)
def test_mint_and_decode_round_trip(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "test-secret")
    token = mint_share_link_token(share_link_id="sl1", tenant_id="t1", item_id="i1", ttl_seconds=86400)
    claims = decode_share_link_token(token)
    assert claims.share_link_id == "sl1"

def test_decode_without_secret_raises_not_crashes(monkeypatch):
    monkeypatch.delenv("CORE_SHARE_LINK_TOKEN_SECRET", raising=False)
    with pytest.raises(ShareLinkTokenError):
        decode_share_link_token("whatever")
```

- [ ] **Step 7 : lancer, vérifier l'échec, puis écrire `share_links.py` (calqué sur `export_tokens.py`, TTL paramétrable, claim `share_link_id`)**

```bash
cd core && uv run pytest tests/test_share_link_tokens.py -v   # ou le nom choisi au Step 6
```

Reprendre `core/app/auth/export_tokens.py` presque à l'identique
(`_secret()`, `mint_*`, `is_*`, `decode_*`, même distinction 401/500) en
adaptant : `_TYP = "share_link"`, claims `{typ, share_link_id, tenant_id,
item_id, iat, exp}` (pas de `user_id` — un lien de partage n'authentifie
pas un utilisateur donné, contrairement au jeton d'export), TTL passé en
argument sans défaut fixe (l'appelant — la route de création — choisit,
bornée par une constante max serveur, ex. `_MAX_TTL_SECONDS = 30 * 86400`,
levée si dépassée).

- [ ] **Step 8 : lancer les tests du jeton, vérifier qu'ils passent**

- [ ] **Step 9 : écrire les tests du repository (create/list/revoke/resolve, avant de l'écrire)**

```python
# core/tests/test_share_links_repository.py
def test_create_list_revoke_share_link(session, tenant, user, item): ...
def test_resolve_rejects_revoked_link_even_before_token_expiry(session, tenant, user, item):
    # Le point qui distingue ce mécanisme de export_tokens.py (§6.1 spec) :
    # un jeton valide ET non expiré doit néanmoins être rejeté si la ligne
    # share_link correspondante porte revoked_at non NULL.
    ...
```

- [ ] **Step 10 : lancer, vérifier l'échec, puis écrire le repository**

```python
# core/app/sharing/repository.py — ajouter
def create_share_link(session, *, tenant_id, item_id, created_by, ttl_seconds) -> ShareLink: ...
def list_share_links(session, *, tenant_id, item_id) -> list[ShareLink]: ...
def revoke_share_link(session, *, tenant_id, link_id) -> bool: ...
def get_active_share_link(session, *, tenant_id, link_id) -> ShareLink | None:
    """None si absent, révoqué, ou expiré (double vérification : la ligne
    ET le TTL du jeton, cf. spec §6.1 — la ligne prime si elle diverge du
    TTL du jeton, ex. un jeton pas encore expiré mais révoqué)."""
```

- [ ] **Step 11 : lancer, vérifier que les tests du repository passent**

- [ ] **Step 12 : écrire les tests des 3 routes (avant de les écrire), puis les routes**

```python
# core/tests/test_share_links_routes.py
def test_create_share_link_requires_write_access(client): ...
def test_revoke_share_link(client): ...
def test_resolve_revoked_link_returns_401_even_before_expiry(client): ...
```

```python
# core/app/sharing/routes.py — ajouter 3 routes
@router.post("/items/{item_id}/share-links")
def create_share_link_route(...): ...

@router.delete("/items/{item_id}/share-links/{link_id}")
def revoke_share_link_route(...): ...

@router.get("/share-links/{token}")
def resolve_share_link_route(...): ...
```

Chacune audite (`share_link.create`/`share_link.revoke`/
`share_link.access`), suit le patron `_require_*` déjà établi dans ce
fichier pour l'autorisation d'écriture sur l'item concerné.

- [ ] **Step 13 : lancer les tests des routes, vérifier qu'ils passent, puis la suite cœur complète**

```bash
cd core && uv run pytest tests/test_share_links_routes.py -v
cd core && uv run pytest
```

- [ ] **Step 14 : régénérer OpenAPI/types TS**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd shell && npm run gen:api-types
```

- [ ] **Step 15 : écrire les tests shell (avant les 3 méthodes `ItemClient`), puis les implémenter**

```ts
test("createShareLink crée un lien avec une échéance", async () => {
  server.use(
    http.post("https://core.test/items/it1/share-links", () =>
      HttpResponse.json({ url: "https://core.test/share-links/eyJ...", expiresAt: "2026-10-05T00:00:00Z" }, { status: 201 }),
    ),
  );
  const link = await makeClient().createShareLink("it1", 30);
  expect(link.url).toContain("/share-links/");
});
```

```ts
// shell/src/api/types.ts
createShareLink(itemId: string, ttlDays: number): Promise<{ url: string; expiresAt: string }>;
listShareLinks(itemId: string): Promise<{ id: string; expiresAt: string; revoked: boolean }[]>;
revokeShareLink(itemId: string, linkId: string): Promise<void>;
```

Ajouter l'implémentation dans `shell/src/api/domains/items.ts` (à côté de
`getSharing`/`setSharing`) — sauf si sa taille finale (3 méthodes + types)
justifie un fichier dédié `domains/shareLinks.ts`, à trancher en tâche
selon le volume réel une fois écrit (cohérent avec le découpage par
domaine de SP-43, pas une règle a priori).

- [ ] **Step 16 : lancer les tests shell, vérifier qu'ils passent**

- [ ] **Step 17 : ajouter la section « Liens à échéance » dans `ShareForm.tsx`**

Formulaire : choix du TTL (jours, borné côté UI à la constante max
serveur), bouton « Créer un lien », liste des liens existants avec statut
(actif/expiré/révoqué) et bouton « Révoquer » par ligne active. Test
avant l'UI (TDD), même discipline que la Tâche 6.

- [ ] **Step 18 : suites complètes**

```bash
cd core && uv run pytest
cd shell && npx vitest run
cd shell && npm run e2e
```

- [ ] **Step 19 : commit(s)**

Découper en plusieurs commits cohérents (migration+modèle ; jeton ;
repository ; routes ; shell) plutôt qu'un seul commit géant, chacun
suivant le patron des tâches précédentes de ce plan.

```bash
git commit -m "$(cat <<'EOF'
feat(core): liens de partage à échéance — table, jeton révocable, routes

GAP-12 (chantier 4.23) : seul le partage groupe/rôle plat existait.
Reprend le patron du jeton d'export éphémère (SP-17a,
auth/export_tokens.py) en l'adaptant : TTL choisi par l'auteur (jours,
pas ~2 min), et surtout révocation avant expiration — absente du
patron d'origine (aucun précédent de jeton révocable dans ce dépôt) —
via une vérification de la ligne share_link en base à chaque
résolution, qui prime sur le TTL du jeton lui-même.
EOF
)"
```

---

## Vérification finale du plan

- [ ] Suite pytest complète (`cd core && uv run pytest`) et suite Vitest
  complète (`cd shell && npx vitest run`).
- [ ] `npm run build` (shell) et les portes de qualité cœur
  (`ruff check`, `ruff format --check`, `mypy --strict` sur les modules
  concernés si `sharing`/`configs` y figurent déjà, `lint-imports`).
- [ ] Suite E2E complète (`npm run e2e`).
- [ ] Diff `core/openapi.json`/`shell/src/api/generated/core-schema.d.ts`
  non vide et cohérent avec les 3 nouvelles routes de la Tâche 7 (piège
  CLAUDE.md n°1 — classe d'oubli la plus fréquente du dépôt).
- [ ] Relire la spec §7 (coordination SP-51) avant de fusionner cette
  branche si le plan SP-51 a progressé en parallèle sur `base.ts`/
  `types.ts` — résoudre tout conflit par relecture des deux diffs.

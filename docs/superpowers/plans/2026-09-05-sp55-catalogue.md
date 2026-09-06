# SP-55 — Catalogue : tri, facettes, recherche spatiale, SEO : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer GAP-05 (tri/facettes catalogue), GAP-06 (recherche spatiale
catalogue) et GAP-07 (SEO des portails publics), les trois chantiers 4.7/4.8/
4.10 de la vague 4 (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
§7). Trois chantiers indépendants entre eux, traités dans le même plan parce
qu'ils partagent la même page (`CatalogPage.tsx`) et une partie de la même
route (`GET /items`).

**Architecture:** 10 tâches, dans l'ordre de risque croissant défini par la
spec §4 : GAP-05 (Tâches 1-3, additif pur, aucune migration), GAP-06
(Tâches 4-6, migration + point d'écriture partagé), GAP-07 (Tâches 7-9,
infrastructure Traefik/Docker Compose — jamais couverte par la suite
Vitest/pytest), puis clôture (Tâche 10).

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest (cœur),
TypeScript/React + Vitest + Playwright (shell), Traefik v3.0.4 + Docker
Compose (infra).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp55-catalogue-design.md` (sections
citées : §1 GAP-05, §2 GAP-06, §3 GAP-07, §4 ordre, §5 risques).

## Global Constraints

- **Aucune dépendance sur SP-43** : ce plan part de l'état réel du dépôt
  constaté le 2026-09-05 (`shell/src/api/domains/items.ts`,
  `shell/src/api/domains/items.hooks.ts` existent déjà comme fichiers
  séparés — vérifié, pas supposé).
- **TDD / filet-avant-code** : chaque tâche pose son test **avant**
  d'écrire le code qu'il protège.
- Commits **conventional**, français, un sujet par commit
  (`feat(core): ...`, `feat(shell): ...`, `test(core): ...`, `chore(infra): ...`).
- **Suite complète rejouée avant de clore chaque tâche qui touche une route
  ou un composant partagé** (piège CLAUDE.md n°6) : `cd core && uv run
  pytest`, `cd shell && npm run test`. `npm run e2e` au minimum en fin de
  Tâches 3, 6, 9 et à la clôture.
- **Toute migration testée sur base non vide, dans les deux sens** (piège
  CLAUDE.md n°8) — Tâche 4.
- **Tout filet de test ajouté doit être vérifié par falsification** (piège
  CLAUDE.md n°10) : injecter le défaut visé, confirmer l'échec, retirer
  l'injection, avant de continuer.
- **Régénérer la spec OpenAPI + types TS** (piège CLAUDE.md n°1) dès qu'une
  route change de forme — Tâches 1, 2, 4, 5, 7 changent des réponses ou
  ajoutent des routes, donc un diff **non vide** est attendu à chacune
  d'elles (contrairement à SP-43, où le diff vide était la norme).
- **Conteneur `postgis-test` non tracké par Alembic** : après la migration
  de la Tâche 4, un `ALTER TABLE` manuel peut être nécessaire sur ce
  conteneur avant de rejouer la suite qui en dépend.
- **Piège CLAUDE.md n°4 (revue de branche)** : à la clôture, vérifier
  explicitement que recherche (`q`) + tri + filtre mot-clé + filtre bbox
  composent correctement ensemble sur `GET /items` — pas seulement testés
  un par un tâche par tâche.
- **Vérifier chaque affirmation contre le code réel avant de la coder** —
  en particulier la signature exacte de `list_published_items` (Tâche 7) et
  la syntaxe réelle des middlewares Traefik v3 (Tâche 8), aucune des deux
  n'a été vérifiée à l'écriture de ce plan (cf. spec §5).

---

## Task 1 : tri + filtre owner/keyword sur `GET /items` (GAP-05)

**Files:**
- Modify: `core/app/items/repository.py::list_items` (lignes 241-331)
- Modify: `core/app/items/routes.py::list_items` (lignes 29-53)
- Test: `core/tests/test_items_repository.py`, `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes : rien de nouveau (mêmes tables/`join(User, ...)` déjà présents).
- Produces : `list_items(..., sort=None, owner=None, keywords=None)` — tous
  optionnels, défaut identique au comportement actuel quand omis.

- [ ] **Step 1 : écrire les tests de tri (avant le code)**

Dans `core/tests/test_items_repository.py`, à côté de
`test_list_items_search_and_type_filter` (ligne 284) : créer 3 items avec des
`title`/`created_at` distincts (mock via `session.flush()` puis
`item.created_at = ...` explicite si le modèle ne l'accepte pas en argument
de construction — vérifier `items_repo.create_item()` avant d'écrire le
test, ne pas supposer sa signature), appeler `list_items(..., sort="title_asc")`
puis `sort="date_asc"`, vérifier l'ordre des `pk` retournés. Un test sans
`sort` (défaut) doit rester identique au comportement actuel
(`test_list_items_scope_mine` etc. ne doivent PAS changer de résultat).

```bash
cd core && uv run pytest tests/test_items_repository.py -k sort -v
# attendu : ÉCHEC (TypeError, list_items() ne connaît pas encore `sort`)
```

- [ ] **Step 2 : écrire les tests de filtre owner/keyword**

Deux items possédés par deux utilisateurs différents (réutiliser le patron
`get_or_create_user` déjà dans `tenant_and_user`) ; `list_items(...,
owner="bob")` ne ramène que les items de bob, **dans la portée déjà
appliquée** (un test doit confirmer qu'`owner` ne réintroduit pas un item
invisible par ailleurs — ex. `scope="mine"` avec un `owner` différent de
l'utilisateur courant doit rester vide, pas planter ni tout retourner).
Items avec des `keywords=["a","b"]`/`["a"]`/`["b","c"]` : `keyword=["a"]`
ramène les deux premiers, `keyword=["a","b"]` (ET) ramène seulement le
premier.

```bash
cd core && uv run pytest tests/test_items_repository.py -k "owner or keyword" -v
```

- [ ] **Step 3 : implémenter dans `list_items`**

Ajouter les 3 paramètres. Pour `sort` : remplacer
`query.order_by(Item.created_at.desc())` (ligne 324) par un dispatch sur
`sort` (dict `{"date_desc": Item.created_at.desc(), "date_asc":
Item.created_at.asc(), "updated_desc": Item.updated_at.desc(), "title_asc":
Item.title.asc(), "title_desc": Item.title.desc()}`, défaut `"date_desc"`).
Pour le chemin RRF (lignes 291-316, actif seulement si `q` et Postgres) :
si `sort` est explicitement posé (pas `None`), trier `page_items`/`items`
en Python après le `by_id[...]` au lieu de suivre l'ordre `candidate_ids` —
écrire ce cas dans un test dédié
(`test_list_items_hybrid_search_respects_explicit_sort`, marqué
`@pytest.mark.postgis`, cf. patron `pg_session` déjà présent dans ce
fichier).

Pour `owner` : `query = query.where(User.username == owner)` (ajouté après
le bloc scope, jamais avant — respecter le commentaire ligne 286-289
existant).

Pour `keyword` : si posé, ne PAS appliquer `LIMIT/OFFSET` SQL — charger
toutes les lignes visibles (comme `list_published_items`, lignes 355-365),
filtrer en Python (`all(k in (item.keywords or []) for k in keywords)`),
paginer par slice Python, recalculer `total` après filtre. Commenter avec
la même justification d'échelle que `list_published_items` (ne pas
réinventer une deuxième formulation).

- [ ] **Step 4 : exposer les paramètres sur la route**

`core/app/items/routes.py::list_items` : ajouter `sort: str | None = None`,
`owner: str | None = None`, `keyword: list[str] | None = Query(default=None)`
(paramètre répété — FastAPI gère `list[str]` en query nativement, vérifier
avec un test d'intégration `?keyword=a&keyword=b` sur le client de test
avant de supposer que ça marche tel quel).

```bash
cd core && uv run pytest tests/test_items_repository.py tests/test_items_routes.py -v
```

- [ ] **Step 5 : falsifier un des filtres (ex. keyword ET vs OU)**

Modifier temporairement `all(...)` en `any(...)`, confirmer que
`test_list_items_filter_by_keyword_and` échoue, revert.

- [ ] **Step 6 : régénérer OpenAPI/types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Diff attendu **non vide** (nouveaux paramètres de requête sur `GET /items`).

- [ ] **Step 7 : commit**

```bash
git add core/app/items/repository.py core/app/items/routes.py core/tests/test_items_repository.py core/tests/test_items_routes.py core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): ajoute tri, filtre propriétaire et filtre mot-clé à GET /items

Ferme GAP-05 côté backend (chantier 4.7) : sort (date/titre), owner
(propriétaire arbitraire, distinct de scope=mine) et keyword (ET) sur
la liste du catalogue — chemin RRF hybride respecté quand un tri
explicite écrase l'ordre de pertinence par défaut.
EOF
)"
```

---

## Task 2 : endpoint `GET /items/facets` (GAP-05)

**Files:**
- Create: rien de nouveau — ajouter à `core/app/items/repository.py` et
  `core/app/items/routes.py` (mêmes fichiers que Tâche 1)
- Modify: `core/app/items/schemas.py` (nouveaux `ItemFacets`, `OwnerFacet`,
  `KeywordFacet`)
- Test: `core/tests/test_items_repository.py`, `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes : le même filtre scope/type/q/owner que `list_items` (sans
  pagination).
- Produces : `items_repo.get_facets(session, ..., ) -> ItemFacets`.

- [ ] **Step 1 : écrire le test du plafond et de l'agrégation (avant le code)**

Créer > 50 mots-clés distincts sur des items visibles, vérifier que
`facets.keywords` a au plus `_MAX_FACET_KEYWORDS` entrées, triées par
`count` décroissant. Vérifier aussi qu'un item invisible dans la portée
courante (autre tenant, ou `scope="mine"` d'un autre utilisateur) n'apparaît
dans aucun des deux comptes — même discipline visibilité-d'abord que
Tâche 1.

```bash
cd core && uv run pytest tests/test_items_repository.py -k facets -v
```

- [ ] **Step 2 : implémenter `get_facets`**

Réutilise la construction de requête de `list_items` jusqu'au filtre
scope/type/q/owner inclus (extraire un helper privé partagé si la
duplication devient gênante — au jugement de l'exécutant, pas une
obligation du plan), puis agrège en Python : `Counter` sur
`User.username` et sur `keywords` aplatis.

- [ ] **Step 3 : exposer la route**

`GET /items/facets`, mêmes query params que `list_items` sauf
`page`/`pageSize`/`sort` (non pertinents ici).

```bash
cd core && uv run pytest tests/test_items_repository.py tests/test_items_routes.py -v
```

- [ ] **Step 4 : falsifier le plafond**

Retirer temporairement le `[:_MAX_FACET_KEYWORDS]`, confirmer qu'un test
dédié échoue avec > 50 mots-clés, remettre.

- [ ] **Step 5 : régénérer OpenAPI/types TS + commit**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git add core/app/items/ core/openapi.json shell/src/api/generated/core-schema.d.ts core/tests/
git commit -m "$(cat <<'EOF'
feat(core): ajoute GET /items/facets (compteurs propriétaire/mot-clé)

Ferme GAP-05 côté facettes : agrégation Python (même hypothèse
d'échelle que list_published_items), plafond de 50 mots-clés.
EOF
)"
```

---

## Task 3 : frontend GAP-05 — tri, facettes, filtre propriétaire dans `CatalogPage`

**Files:**
- Modify: `shell/src/api/types.ts`, `shell/src/api/domains/items.ts`,
  `shell/src/api/domains/items.hooks.ts`, `shell/src/pages/CatalogPage.tsx`
- Test: `shell/src/pages/CatalogPage.test.tsx`, `shell/src/api/itemClient.test.ts`
- E2E: `shell/e2e/catalog.spec.ts`

**Interfaces:**
- Consumes : `GET /items` (Tâche 1) et `GET /items/facets` (Tâche 2), déjà
  disponibles côté cœur.
- Produces : `useItemFacets()` (nouveau hook), UI de tri/facettes dans le
  panneau `browse` de `CatalogPage`.

- [ ] **Step 1 : écrire le test caractéristique du client (avant le code)**

Dans `shell/src/api/itemClient.test.ts` : un test qui vérifie que
`listItems({ sort: "title_asc", owner: "bob", keywords: ["a", "b"] })`
sérialise `sort=title_asc&owner=bob&keyword=a&keyword=b` dans l'URL
appelée (mock `fetch`, même patron que les tests `listItems` existants).
Un test pour `getItemFacets(...)`.

```bash
cd shell && npm run test -- itemClient -t "facets|sort|owner|keyword"
# attendu : ÉCHEC (méthodes absentes)
```

- [ ] **Step 2 : étendre les types et le client**

`ListItemsParams` gagne `sort?`, `owner?`, `keywords?: string[]`. Nouveaux
types `OwnerFacet`, `KeywordFacet`, `ItemFacets`. `ItemClient` (interface)
gagne `getItemFacets(params): Promise<ItemFacets>`. Implémenter dans
`shell/src/api/domains/items.ts::createItemsMethods`.

- [ ] **Step 3 : nouveau hook**

`shell/src/api/domains/items.hooks.ts::useItemFacets(params, opts)`, même
patron que `useItems`.

- [ ] **Step 4 : écrire les tests `CatalogPage` (avant l'UI)**

Dans `CatalogPage.test.tsx`, à côté de `filters by scope` (ligne 101) :
un test qui change le tri et vérifie que `useItems` reçoit `sort` mis à
jour ; un test qui sélectionne un mot-clé de facette (mock
`useItemFacets` retournant des données fixes) et vérifie le filtre
appliqué ; un test qui sélectionne un propriétaire.

```bash
cd shell && npm run test -- CatalogPage -t "tri|facette|propriétaire"
```

- [ ] **Step 5 : implémenter l'UI**

Dans le panneau `browse` (`content` de l'objet `browse`, après le
sélecteur « Portée », ligne ~136) : `<select>` tri, `<select>` propriétaire
(peuplé par `useItemFacets`), chips mots-clés à bascule
(`aria-pressed={selected}`). État `sort`/`ownerFilter`/`selectedKeywords`
passés à `useItems`. Mettre à jour le volet `inspect` (Résumé) pour
afficher les filtres actifs.

- [ ] **Step 6 : E2E**

`shell/e2e/catalog.spec.ts` : un test qui trie par titre et vérifie l'ordre
d'affichage des cartes ; un test qui filtre par mot-clé et vérifie que
seuls les items correspondants restent visibles.

```bash
cd shell && npm run e2e -- catalog
```

- [ ] **Step 7 : suite complète + commit**

```bash
cd shell && npm run lint && npm run test && npm run build
git add shell/src/api/ shell/src/pages/CatalogPage.tsx shell/e2e/catalog.spec.ts
git commit -m "$(cat <<'EOF'
feat(shell): tri, facettes et filtre propriétaire dans le catalogue

Ferme GAP-05 (chantier 4.7) côté shell : sélecteur de tri, chips de
mots-clés et filtre propriétaire dans CatalogPage, alimentés par
GET /items/facets.
EOF
)"
```

---

## Task 4 : modèle bbox sur `Item` + point d'écriture unique (GAP-06)

**Files:**
- Create: migration Alembic (numéro à vérifier au moment de l'exécution,
  `0035` pressenti), `core/app/items/bbox.py`
- Modify: `core/app/items/models.py`, `core/app/items/schemas.py`,
  `core/app/configs/repository.py` (`create_config`, `update_config`,
  `rollback_config`)
- Test: `core/tests/test_items_bbox.py` (nouveau), vérifier
  `core/tests/test_configs_repository.py` reste vert.

**Interfaces:**
- Consumes: `app.collections.extent::table_extent` (réutilisé, pas
  dupliqué — spec §2.1), `app.collections.introspection_pg::introspect_table`.
- Produces: `app.items.bbox::recompute_item_bbox(session, *, item: Item,
  config: BuilderConfig, tenant_id: str) -> None` — posé sur les 4 colonnes
  de `item`, pas de commit.

- [ ] **Step 1 : localiser la signature exacte de `create_config`/`update_config`/`rollback_config`**

```bash
sed -n '1,290p' core/app/configs/repository.py
```

Confirmer où `Item` est déjà chargé dans chacune des 3 fonctions (pour
n'ajouter qu'un appel, pas un rechargement) avant d'écrire le code de la
Step 4.

- [ ] **Step 2 : écrire le test de `recompute_item_bbox` (avant le code)**

`core/tests/test_items_bbox.py`, `@pytest.mark.postgis` (nécessite une
vraie table PostGIS pour `table_extent`, cf. patron `pg_session` de
`test_items_repository.py`) : une collection avec des features connues, un
`BuilderConfig(kind="map", map=MapConfig(layers=[MapLayer(kind="feature",
collectionId=<id>, ...)]))`, appel à `recompute_item_bbox`, vérifier les 4
colonnes posées correspondent à l'emprise réelle. Un cas `kind != "map"` →
les 4 colonnes restent `None`. Un cas 2 collections (union des bbox). Un
cas collection vide (bbox `None` pour cette couche, ignorée dans l'union).

```bash
cd core && uv run pytest tests/test_items_bbox.py -v
# attendu : ÉCHEC (module inexistant)
```

- [ ] **Step 3 : migration**

```bash
cd core && uv run alembic revision -m "bbox sur items"
```

4 colonnes `Float, nullable=True` : `bbox_min_x`, `bbox_min_y`,
`bbox_max_x`, `bbox_max_y`. Tester `upgrade`/`downgrade`/`upgrade` sur une
base jetable **non vide** (au moins un item existant avant la migration) —
piège CLAUDE.md n°8.

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v  # si présent (SP-43), sinon ignorer
```

- [ ] **Step 4 : implémenter `recompute_item_bbox` et le câbler**

`core/app/items/bbox.py::recompute_item_bbox`. Appelé dans les 3 fonctions
de `configs/repository.py` juste avant que la transaction ne committe (ou
juste avant le `return`, selon où le commit réel a lieu — vérifier le
patron exact de commit de ce fichier avant d'ajouter l'appel, ne pas
supposer qu'un `session.commit()` explicite existe déjà à cet endroit).

```bash
cd core && uv run pytest tests/test_items_bbox.py tests/test_configs_repository.py -v
```

- [ ] **Step 5 : filet transverse REST + MCP**

Écrire (ou étendre un test existant) qui appelle
`app.mcp.tools.configs::save_app_config` (ou son équivalent testé,
`core/tests/test_mcp_configs*.py`) sur une config `kind="map"` avec un
`collectionId`, et vérifie que l'item récupéré ensuite a bien sa bbox
posée — **sans avoir jamais appelé la route HTTP** `PUT /configs/{id}`.
C'est le test qui prouve que le point de passage unique fonctionne
(spec §2.3) ; s'il faut passer par la route HTTP pour que la bbox se pose,
c'est que le câblage est fait au mauvais endroit — revenir à l'étape 4.

- [ ] **Step 6 : backfill**

Script/route de rattrapage (spec §2.5) qui itère les items `kind="map"`
existants et appelle `recompute_item_bbox` sur chacun, idempotent. Test :
un item créé avec l'ancien schéma (bbox `NULL` par construction) obtient
sa bbox après un passage du backfill, sans double-exécution problématique
si relancé deux fois.

- [ ] **Step 7 : falsifier le filet MCP (Step 5)**

Commenter temporairement l'appel à `recompute_item_bbox` dans
`update_config`, confirmer que le test de la Step 5 échoue (pas seulement
un test REST), remettre.

- [ ] **Step 8 : régénérer OpenAPI/types TS + suite complète + commit**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd ../core && uv run pytest
git add core/alembic/versions/ core/app/items/ core/app/configs/repository.py core/tests/ core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): calcule et persiste l'emprise spatiale d'un item carte

Ferme GAP-06 côté modèle (chantier 4.8) : 4 colonnes bbox sur Item,
recalculées au point d'écriture partagé de configs/repository.py
(create_config/update_config/rollback_config) — couvre à la fois les
routes REST et l'outil MCP save_app_config sans duplication, backfill
pour les items map déjà existants.
EOF
)"
```

---

## Task 5 : filtre spatial sur `GET /items` (GAP-06)

**Files:**
- Modify: `core/app/items/repository.py::list_items`, `core/app/items/routes.py`
- Test: `core/tests/test_items_repository.py`, `core/tests/test_items_routes.py`

**Interfaces:**
- Consumes: les 4 colonnes bbox posées par la Tâche 4.
- Produces: paramètre `bbox: str | None` sur `GET /items`
  (`"minX,minY,maxX,maxY"`).

- [ ] **Step 1 : vérifier le format `bbox` déjà utilisé par OGC API Features**

```bash
grep -n "bbox" core/app/features/routes.py | head -20
```

Réutiliser exactement le même format textuel de parsing s'il existe déjà
une fonction de parsing partageable — ne pas en écrire un deuxième
différent.

- [ ] **Step 2 : écrire le test d'intersection (avant le code)**

3 items avec des bbox stockées disjointes/qui se chevauchent
partiellement/totalement incluses ; `list_items(..., bbox=(...))` ne
ramène que les items dont le rectangle intersecte. Un item avec bbox
`None` (jamais calculée) n'apparaît jamais dans un filtre bbox posé. Un
test combinant `q` + `bbox` (chemin RRF) — spec §5, risque de composition.

```bash
cd core && uv run pytest tests/test_items_repository.py -k bbox -v
```

- [ ] **Step 3 : implémenter le filtre**

Ajouter la clause d'intersection (spec §2.4) après le filtre scope/owner,
avant `q`. Sur le chemin RRF, l'appliquer à `base_stmt` (avant l'appel à
`hybrid_search_ids`), pas en post-filtre sur `candidate_ids`.

- [ ] **Step 4 : exposer sur la route + régénérer OpenAPI/types TS**

```bash
cd core && uv run pytest tests/test_items_repository.py tests/test_items_routes.py -v
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 5 : commit**

```bash
git add core/app/items/ core/openapi.json shell/src/api/generated/core-schema.d.ts core/tests/
git commit -m "$(cat <<'EOF'
feat(core): filtre spatial bbox sur GET /items

Ferme GAP-06 côté filtre (chantier 4.8) : intersection de rectangles
sur les colonnes bbox persistées (Tâche 4), composé avec q/scope/tri.
EOF
)"
```

---

## Task 6 : dessin de rectangle + intégration `CatalogPage` (GAP-06)

**Files:**
- Create: `shell/src/pages/CatalogSpatialFilter.tsx`,
  `shell/src/pages/CatalogSpatialFilter.test.tsx`
- Modify: `shell/src/pages/CatalogPage.tsx`, `shell/src/api/types.ts`
  (`ListItemsParams.bbox`), `shell/src/api/domains/items.ts`
- E2E: `shell/e2e/catalog.spec.ts`

**Interfaces:**
- Consumes: `shell/src/map/basemaps.ts::DEFAULT_BASEMAP`, MapLibre GL (déjà
  une dépendance du dépôt).
- Produces: `CatalogSpatialFilter({ onChange: (bbox: [number, number,
  number, number] | null) => void })`.

- [ ] **Step 1 : écrire le test du composant (avant l'implémentation)**

`CatalogSpatialFilter.test.tsx` : monter le composant (mock MapLibre —
vérifier le patron de mock déjà utilisé pour MapLibre ailleurs dans le
dépôt, ex. `shell/src/map/*.test.tsx`, avant d'en écrire un nouveau),
simuler un clic-glisser, vérifier que `onChange` est appelé avec un
rectangle `[minLon, minLat, maxLon, maxLat]` cohérent avec les deux points
cliqués. Un test pour le bouton « Effacer » (`onChange(null)`).

```bash
cd shell && npm run test -- CatalogSpatialFilter
# attendu : ÉCHEC (fichier inexistant)
```

- [ ] **Step 2 : implémenter le composant**

Instance MapLibre autonome, fond `DEFAULT_BASEMAP`, gestion
`mousedown`/`mousemove`/`mouseup` dessinant un rectangle (pas de
dépendance à `measureSketch.ts` — logique bbox plus simple qu'un polygone
libre, spec §2.6). Rendu du rectangle via une source/couche GeoJSON
MapLibre ajoutée dynamiquement.

- [ ] **Step 3 : intégrer dans `CatalogPage`**

Sous les facettes de la Tâche 3, dans le panneau `browse`. État `bbox`
passé à `useItems({ ..., bbox: bboxToQueryString(bbox) })` (fonction utilitaire
à ajouter à `shell/src/api/domains/items.ts` ou un module partagé, au choix
de l'exécutant).

- [ ] **Step 4 : E2E**

```bash
cd shell && npm run e2e -- catalog
```

Un test qui dessine un rectangle (ou, si l'interaction souris réelle est
trop fragile en Playwright, un test qui invoque directement l'API du
composant via un sélecteur de test dédié — au jugement de l'exécutant, en
documentant le choix) et vérifie que seuls les items dont la bbox
intersecte restent affichés (nécessite des items de test avec bbox connue
— fixture E2E à étendre si besoin).

- [ ] **Step 5 : suite complète + commit**

```bash
cd shell && npm run lint && npm run test && npm run build
git add shell/src/pages/CatalogSpatialFilter.tsx shell/src/pages/CatalogSpatialFilter.test.tsx shell/src/pages/CatalogPage.tsx shell/src/api/ shell/e2e/catalog.spec.ts
git commit -m "$(cat <<'EOF'
feat(shell): recherche spatiale par rectangle dans le catalogue

Ferme GAP-06 côté shell (chantier 4.8) : CatalogSpatialFilter (dessin
de rectangle sur une carte MapLibre autonome, pas de dépendance à
measureSketch.ts), intégré à CatalogPage via ListItemsParams.bbox.
EOF
)"
```

---

## Task 7 : `sitemap.xml`/`robots.txt`/`social-preview` + `PUBLIC_BASE_URL` (GAP-07)

**Files:**
- Modify: `core/app/public/routes.py`
- Test: `core/tests/test_public_routes.py` (existant probable — vérifier le
  nom exact avant d'écrire, `find core/tests -iname "*public*"`)

**Interfaces:**
- Consumes: `items_repo.get_published_site_by_slug`,
  `items_repo.list_published_items` (vérifier si sa signature couvre
  « tous les sites publiés sans pagination visible » ou s'il faut une
  variante dédiée — spec §3.2, non tranché à l'écriture de ce plan).
- Produces: `GET /public/sitemap.xml`, `GET /public/robots.txt`,
  `GET /public/sites/{slug}/social-preview`.

- [ ] **Step 1 : vérifier la signature réelle de `list_published_items`**

```bash
sed -n '334,367p' core/app/items/repository.py
```

Décider : réutiliser tel quel avec une `page_size` volontairement large et
documentée, ou ajouter une fonction dédiée `list_all_published_items(...,
resource_type="site")` sans pagination. Documenter le choix dans un
commentaire au point d'appel.

- [ ] **Step 2 : écrire les tests des 3 endpoints (avant le code)**

Un test qui crée 2 sites publiés + 1 non publié, appelle
`GET /public/sitemap.xml`, vérifie que le XML contient exactement les 2
URLs publiées (jamais celle du site non publié — même discipline
« publié seulement » que le reste de `app/public/`). Un test
`GET /public/robots.txt` vérifie la présence de la ligne `Sitemap:`. Un
test `GET /public/sites/{slug}/social-preview` vérifie la présence de
`og:title`, `og:description`, `<link rel="canonical"`, avec les valeurs
issues du site créé ; un test 404 sur un slug inconnu ou un site non
publié.

```bash
cd core && uv run pytest tests/test_public_routes.py -k "sitemap or robots or social" -v
```

- [ ] **Step 3 : implémenter**

`_render_sitemap_xml`, `_render_social_preview_html` (échappement HTML des
champs utilisateur — `title`/`abstract` peuvent contenir des caractères
spéciaux, utiliser l'échappement de la bibliothèque standard, pas une
concaténation de chaînes brute). Lire `PUBLIC_BASE_URL` via
`os.environ["PUBLIC_BASE_URL"]` (pas de valeur par défaut silencieuse en
production — vérifier si ce module a déjà un patron de garde pour une
variable requise en prod mais optionnelle en dev, sinon suivre le patron
`os.environ["SHELL_BASE_URL"]` déjà utilisé sans défaut dans
`export/jobs.py`).

- [ ] **Step 4 : falsifier l'échappement HTML**

Créer un site dont le `title` contient `<script>` ; confirmer que la
réponse `social-preview` ne l'injecte pas tel quel (le test doit
explicitement chercher la séquence échappée, pas juste absence d'erreur
500).

- [ ] **Step 5 : câbler `PUBLIC_BASE_URL`**

`docker-compose.yml` (bloc `environment:` du service `core`),
`.env.example` (avec le commentaire distinguant explicitement
`PUBLIC_BASE_URL` de `SHELL_BASE_URL`/`CORE_BASE_URL` — spec §3.2). Un
défaut de développement cohérent avec `docker compose up` par défaut (à
tester réellement, pas juste écrit).

```bash
docker compose config | grep -A5 "PUBLIC_BASE_URL"
```

- [ ] **Step 6 : régénérer OpenAPI/types TS + commit**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git add core/app/public/routes.py core/tests/ core/openapi.json shell/src/api/generated/core-schema.d.ts docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(core): sitemap.xml, robots.txt et aperçu social pour /sites/{slug}

Ferme GAP-07 côté cœur (chantier 4.10) : trois routes publiques
rendues côté serveur (jamais exécutées côté client, nécessaire pour
les robots de prévisualisation qui n'exécutent pas de JS) ; nouvel
env PUBLIC_BASE_URL, distinct de SHELL_BASE_URL (usage interne
Docker réservé à export-worker) et de CORE_BASE_URL.
EOF
)"
```

---

## Task 8 : routage Traefik + vérification de câblage (GAP-07)

**Files:**
- Modify: `docker-compose.yml` (routeurs Traefik)
- Test: `core/tests/test_deployability.py` (vérifier lesquels s'appliquent
  déjà, en ajouter si le patron existant le permet)

**Interfaces:**
- Consumes: les 3 routes de la Tâche 7, exposées par le service `core`.
- Produces: routeurs Traefik `seo-static` et `seo-bots`, priorité
  supérieure au catch-all `shell` (priorité 1).

- [ ] **Step 1 : vérifier la syntaxe réelle des middlewares Traefik v3.0.4**

Piège CLAUDE.md n°3 — ne pas supposer `replacepathregex`/`headerregexp`
sans les avoir vérifiés contre la documentation Traefik v3 réelle (image
`traefik:v3.0.4` déjà épinglée dans `docker-compose.yml:697`). Consigner la
référence exacte utilisée dans un commentaire du compose.

- [ ] **Step 2 : écrire le test de non-régression des priorités (avant le changement)**

Si `test_deployability.py` a déjà un test de forme
`test_*_router_has_no_stripprefix_middleware` ou équivalent sur les
priorités (cf. `test_grafana_router_has_no_stripprefix_middleware`,
`test_admin_tool_router_is_gated_by_admin_auth`), écrire un test jumeau
pour `seo-static`/`seo-bots` : priorité strictement supérieure à 1
(catch-all shell), distincte de celle des routeurs admin (15).

```bash
cd core && uv run pytest tests/test_deployability.py -k seo -v
```

- [ ] **Step 3 : ajouter les labels Traefik**

Sur le service `core`, à côté des labels existants (`docker-compose.yml`
lignes ~346-358) : `seo-static` (`Path(`/sitemap.xml`) || Path(`/robots.txt`)`)
et `seo-bots` (`PathPrefix(`/sites/`) && HeaderRegexp(...)`), avec les
middlewares de réécriture de chemin de la spec §3.3.

- [ ] **Step 4 : vérification manuelle contre une stack réelle**

`docker compose config` ne suffit pas ici (le comportement Traefik réel —
matching de priorité, exécution du middleware de réécriture — ne se
prouve qu'à l'exécution) :

```bash
docker compose up -d traefik core shell
curl -s http://localhost/sitemap.xml | head -5
curl -s http://localhost/robots.txt
curl -s -A "facebookexternalhit/1.1" http://localhost/sites/<slug-existant>
curl -s -A "Mozilla/5.0 (real browser)" http://localhost/sites/<slug-existant> | head -5  # doit rester le SPA (index.html), pas le HTML minimal
```

Documenter le résultat réel dans le ledger de session — ne pas clore la
tâche sur la seule lecture du fichier compose.

- [ ] **Step 5 : commit**

```bash
git add docker-compose.yml core/tests/test_deployability.py
git commit -m "$(cat <<'EOF'
feat(infra): route sitemap/robots/aperçu social vers le cœur via Traefik

Ferme GAP-07 côté routage (chantier 4.10) : deux routeurs Traefik
(seo-static, seo-bots) au-dessus du catch-all shell (priorité 1),
vérifiés contre une stack réelle (docker compose up), pas seulement
docker compose config.
EOF
)"
```

---

## Task 9 : méta document pour le rendu JS (GAP-07)

**Files:**
- Create: `shell/src/shell/useDocumentMeta.ts`,
  `shell/src/shell/useDocumentMeta.test.ts`
- Modify: `shell/src/pages/SitePublicPage.tsx`

**Interfaces:**
- Consumes: `item.title`/`item.abstract` (déjà chargés par
  `SitePublicPage`).
- Produces: `useDocumentMeta({ title, description, canonicalUrl })`.

- [ ] **Step 1 : écrire le test du hook (avant le code)**

Monter un composant de test qui appelle `useDocumentMeta(...)`, vérifier
`document.title` et la présence d'un `<meta name="description">` /
`<link rel="canonical">` avec le bon contenu ; un test de démontage qui
vérifie le nettoyage (pas de balise orpheline après unmount, si c'est le
comportement choisi — sinon documenter explicitement pourquoi les balises
persistent, au jugement de l'exécutant).

```bash
cd shell && npm run test -- useDocumentMeta
```

- [ ] **Step 2 : implémenter et câbler dans `SitePublicPage`**

- [ ] **Step 3 : suite complète + commit**

```bash
cd shell && npm run test && npm run build
git add shell/src/shell/useDocumentMeta.ts shell/src/shell/useDocumentMeta.test.ts shell/src/pages/SitePublicPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): titre/description/canonical dynamiques sur /sites/{slug}

Ferme GAP-07 côté rendu JS (chantier 4.10) : complète le chemin robot
de la Tâche 7/8 pour l'onglet navigateur d'un humain et pour Googlebot
(qui exécute le JS avant indexation, contrairement aux robots de
prévisualisation de messagerie).
EOF
)"
```

---

## Clôture de plan

- [ ] **Suite complète finale** :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
  && npm run e2e
uvx pre-commit run --all-files
```

- [ ] **Vérification de composition (piège CLAUDE.md n°4)** : sur
  `GET /items`, un appel combinant `q` + `sort` + `keyword` + `bbox` en même
  temps produit un résultat cohérent — pas seulement chaque paramètre
  testé isolément dans les tâches précédentes.
- [ ] **Mettre à jour `CLAUDE.md`** (`### Livré`) avec une ligne SP-55 :
  tri/facettes/filtre propriétaire (GAP-05), emprise spatiale persistée +
  recherche par rectangle (GAP-06, point d'écriture unique
  `configs/repository.py` couvrant REST+MCP), sitemap/robots/aperçu social
  routés via Traefik vers le cœur (GAP-07, nouvel env `PUBLIC_BASE_URL`).
- [ ] **Documenter dans le suivi de clôture** le résultat réel de la
  vérification manuelle Traefik (Tâche 8, Step 4) — ne jamais la laisser
  implicite ou supposée à partir du seul `docker compose config`.

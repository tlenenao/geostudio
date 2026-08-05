# SP-14l — MCP analytique : `create_dataset`, `run_analytics_query`, `explain_dataset` (design)

> **Date : 2026-08-04 · Statut : validé (brainstorm)**
> Douzième sous-partie de **SP-14 — Analytics UX** (feuille de route, jalon
> M11), après **SP-14a — Datasets partagés**, **SP-14b — Contexte analytique
> global & cross-filter**, **SP-14c — Filtres typés & indicateur**,
> **SP-14d — Menu explorer & voir les entités**, **SP-14e — KPI riche &
> séries temporelles comparées**, **SP-14f — Nouveaux types de graphiques**,
> **SP-14g — Tableau croisé / pivot**, **SP-14h — Carte analytique**,
> **SP-14i — SQL Lab**, **SP-14j — Conteneurs** et **SP-14k — Source
> `arcgis`**. Traite le dernier élément explicitement listé « hors
> périmètre » par 14k (« Requête visuelle, MCP analytique. Sous-parties
> SP-14 ultérieures ») : **MCP analytique** — les trois outils `create_dataset`,
> `run_analytics_query`, `explain_dataset` prévus par la feuille de route
> §SP-14 (« MCP : outils `create_dataset`, `run_analytics_query`,
> `explain_dataset` »). **Requête visuelle** reste hors périmètre : elle
> dépend du moteur de pipeline livré par **SP-15** (A39, ETL no-code), qui
> n'existe pas encore — traitée après SP-15, pas comme sous-partie SP-14.

## 1. Objectif & non-buts

**Objectif.** Rendre les datasets analytiques (SP-14a…k) opérables par un
agent MCP, au même titre que les items/configs/features le sont déjà depuis
SP-2/SP-7 : un agent peut créer un dataset référençant une collection ou une
couche ArcGIS, découvrir ses champs interrogeables sans deviner, puis
l'interroger en agrégation structurée — sans jamais fabriquer de SQL
(cohérent avec A19). Ces trois outils sont un câblage MCP sur des chemins de
requête déjà validés côté cœur (`/collections/{id}/aggregate` depuis SP-11b,
`/datasets/{item_id}/arcgis/aggregate` depuis SP-14k, `POST /configs` depuis
SP-0/SP-1) — SP-14l n'introduit aucune nouvelle sémantique de requête,
seulement leur exposition en outils MCP.

**Non-buts explicites** :

- **`run_sql` (MCP)**. La feuille de route ne liste que les trois outils
  ci-dessus ; SQL Lab (SP-14i) reste un chemin REST réservé au rôle
  analyste dans l'UI, pas exposé en MCP ici. Un outil MCP `run_sql`
  soulèverait ses propres questions de surface d'abus (rôle analyste
  agent ?, quotas ?) — hors périmètre, sous-partie SP-14 ultérieure si le
  besoin émerge.
- **Requête visuelle** et **pipeline de transformations**. Dépendent du
  moteur SP-15 (A39), qui n'existe pas encore.
- **Statistiques par champ dans `explain_dataset`** (min/max/distinct
  count). Nécessiterait une requête d'agrégation par champ au moment de
  l'introspection — coût et nouveau chemin de code non justifiés tant
  qu'aucun agent réel n'en a exprimé le besoin ; un agent qui veut des
  bornes de valeurs peut déjà les obtenir via `run_analytics_query`
  (`groupBy`/`measures`) une fois le champ connu.
- **Métriques nommées CEL sur un dataset**. Toujours hors modèle
  (`DatasetPayload` n'a pas de champ `metrics` — reporté avec le pipeline
  SP-15/A39, cf. non-buts de SP-14a).
- **Modification/suppression d'un dataset existant en MCP**
  (`update_dataset`/`delete_dataset`). Non listés par la feuille de route ;
  `save_app_config` (générique, déjà existant) couvre déjà la mise à jour
  d'un config de n'importe quel `kind`, dataset inclus — pas de nouvel
  outil dédié nécessaire pour l'update. La suppression n'a pas
  d'équivalent MCP pour aucun `kind` aujourd'hui (pas seulement dataset) —
  cohérent de ne pas commencer par les datasets.

Le modèle reste additif : aucun outil MCP existant n'est modifié ; les 12
outils actuels (`whoami`, `list_items`, `search_catalog`, `query_features`,
`get_item`, `get_app_config`, `save_app_config`, `create_item`,
`create_form_app`, `get_sharing`, `set_sharing`, plus la resource
`schema://app-config`) sont inchangés.

## 2. `create_dataset`

```python
@server.tool()
async def create_dataset(
    ctx: Context,
    title: str,
    source: Literal["collection", "arcgis"],
    collectionId: str | None = None,
    arcgisItemId: str | None = None,
    columns: dict[str, DatasetColumnMeta] | None = None,
    timeField: str | None = None,
    reactsToExtent: bool = False,
) -> ItemRead
```

Mirrors `POST /configs` avec `kind="dataset"` (le chemin qu'emprunte déjà
`shell/src/api/itemClient.ts::createDatasetItem`), transposé au patron
`create_item`/`create_form_app` (deux appels internes plutôt que la route
HTTP : `items_repo.create_item` + `configs_repo.create_config`, mêmes
`write_audit` `item.create`/`config.create`).

- Gated par `is_read_only_mode()`, comme tout outil d'écriture — `"create_dataset"`
  ajouté à `READ_ONLY_TOOLS`.
- Construit un `DatasetPayload(source=..., collectionId=..., arcgisItemId=...,
  columns=columns or {}, timeField=timeField, reactsToExtent=reactsToExtent)` :
  le `model_validator` déjà présent sur `DatasetPayload` (SP-14a/k) rejette
  toute combinaison incohérente (les deux identifiants renseignés, ou
  aucun) — aucune revalidation à écrire ici.
- Wrappe dans `BuilderConfig(version=1, kind="dataset", dataset=payload)`.
- **Nouvelle fonction privée `_validate_dataset(session, config, user)`** —
  même patron que `_validate_extension_scope` (§`mcp/tools.py` existant) :
  appelle `app.configs.dataset_validation.validate_dataset_payload(session,
  config, user=user)` (le hook déjà utilisé par `POST /configs` et
  `PUT /configs/{by-item}`, qui vérifie — selon `source` — que la
  collection ou la couche ArcGIS moissonnée référencée est bien lisible
  par l'utilisateur) et traduit son `HTTPException(422, ...)` en
  `ValueError` (le tool body n'a pas de canal de statut HTTP, même
  rationale que `_validate_extension_scope`/`_require_access`).
  **Sans cet appel, `create_dataset` pourrait créer un dataset pointant
  vers une collection ou une couche ArcGIS invisible à l'utilisateur** —
  c'est le même garde-fou que la route REST, pas une vérification
  optionnelle.
- `resource_type="dataset"` (nouveau littéral pour `create_item`, jusqu'ici
  seul `create_item` (MCP) acceptait `Literal["app", "dashboard"]` — ce
  outil-ci est distinct, pas une extension du littéral de `create_item`,
  même choix que `create_form_app` qui a aussi son propre outil plutôt que
  d'étendre `create_item`).
- Retourne `ItemRead` (même forme que `create_item`/`create_form_app`).

## 3. `run_analytics_query`

```python
@server.tool()
async def run_analytics_query(ctx: Context, datasetId: str, query: AggregateRequestBody) -> dict
```

Réutilise `AggregateRequestBody` (déjà défini dans `app.analytics.aggregate`,
SP-11b) directement comme type de paramètre — même patron que
`save_app_config(config: BuilderConfig)` : l'agent reçoit exactement le même
contrat (`groupBy`, `split`, `measures`, `filters`, `bbox`, `bucket`, `bins`)
que les widgets `chart`/`indicator`/`table` du shell, sans schéma parallèle à
maintenir.

1. `_require_access(item_id=datasetId, action="read")` (accès au dataset —
   objet catalogué comme n'importe quel item).
2. Charge le config (`configs_repo.get_config_by_item`), vérifie
   `kind == "dataset"` et `config.dataset is not None` → sinon
   `ValueError("dataset not found")`.
3. Dispatch sur `payload.source` — **mirroring**, pas de nouvelle
   abstraction (cf. §choix d'architecture ci-dessous) :
   - **`"collection"`** : `_require_collection_read(collection_id=payload.collectionId)`
     (deuxième vérification indépendante — lire le dataset ne garantit pas
     de lire la collection sous-jacente, même raisonnement que SP-14k §6
     pour `arcgis` ; re-vérifié à chaque requête, pas seulement à la
     création, pour rester correct si le partage change entre-temps) ;
     `introspect_table` ; `run_collection_aggregate(conn, base_uri,
     tenant_id, collection_id, table_info, request=query)` avec le même
     `conn_factory`/`base_uri` que `POST /collections/{id}/aggregate`
     (`app.features.routes.get_duckdb_connection_factory`/
     `get_analytics_base_uri`, importés directement — ce sont de simples
     fonctions lisant `os.environ`, pas des dépendances FastAPI liées au
     cycle de requête HTTP). `UnknownAggregateField` → `ValueError`.
   - **`"arcgis"`** : réutilise `app.harvest.routes._resolve_arcgis_dataset`
     (déjà la fonction exacte qu'utilise `/datasets/{item_id}/arcgis/aggregate` —
     vérifie l'accès au dataset **et**, indépendamment, l'accès à l'item
     `external` moissonné sous-jacent) en traduisant son `HTTPException` en
     `ValueError` ; puis `live_query.translate_aggregate_query` +
     `fetch_query` + `aggregate_response`, identique à la route REST, y
     compris le rejet explicite (`ValueError`, ici ; `400` côté REST) de
     `bucket`/`split`/`bins` sur une source `arcgis` (pas d'équivalent côté
     API statistiques ArcGIS, cf. SP-14k §1).
4. Retourne `{"categoryKey": ..., "rows": ...}` — même forme que les deux
   routes REST équivalentes.

Pas d'écriture d'audit (même choix que les routes `aggregate_features`/
`query_features`, qui n'auditent pas non plus — seule `/analytics/sql`
audite, parce que le SQL libre est la seule des deux surfaces à risque
d'abus ; `run_analytics_query` reste entièrement structuré, même profil de
risque que `query_features`).

## 4. `explain_dataset`

```python
@server.tool()
async def explain_dataset(ctx: Context, datasetId: str) -> dict
```

Donne à un agent de quoi appeler `run_analytics_query` correctement sans
deviner un nom de champ — le même rôle que joue déjà le docstring de
`query_features` (« filters are structured field=value pairs ») mais rendu
introspectable au lieu de reposer sur la description de l'outil.

1. Même résolution d'accès + config que `run_analytics_query` (étapes 1-2).
2. Retourne :
   ```json
   {
     "title": "...",
     "source": "collection" | "arcgis",
     "timeField": "...", "reactsToExtent": true,
     "columns": { "champ": { "label": "...", "description": "...", "format": "..." } },
     "fields": [ { "name": "...", "type": "..." } ]
   }
   ```
   `columns` = métadonnées auteur telles que stockées dans `DatasetPayload`
   (peuvent être vides — rien ne les rend obligatoires). `fields` = schéma
   introspecté, résolu selon la source :
   - **`"collection"`** : `table_info_to_schema(introspect_table(...))` —
     exactement l'utilitaire déjà utilisé par `create_form_app`.
   - **`"arcgis"`** : un `GET {external_url}?f=json` **live** via
     `build_guarded_client()` (même garde d'egress SSRF que tout autre
     appel ArcGIS, SP-12d), dont on extrait `fields: [{name, alias, type}]`
     de la réponse JSON standard d'une couche ArcGIS. Rien n'est mis en
     cache ici : `run_analytics_query` interroge déjà la couche en direct à
     chaque appel côté `arcgis`, `explain_dataset` a le même profil.
3. Aucune statistique, aucun échantillonnage (cf. non-buts §1) : nom, type,
   métadonnées auteur — rien de plus.

## 5. Choix d'architecture : mirroring plutôt qu'extraction

Les 12 outils MCP existants suivent tous le même patron : chaque outil
**mirrors** la logique d'une route REST en import direct des fonctions
privées de la couche route (ex. `query_features` réutilise
`introspect_table`/`select_features`/`rls_scope`), plutôt que d'extraire un
module partagé entre REST et MCP. SP-14l suit ce même patron plutôt que
d'introduire un nouveau module `app/analytics/dataset_query.py` qui
centraliserait le dispatch `collection`/`arcgis` (une centralisation
qui existe déjà, de façon dupliquée, côté shell dans `itemClient.ts`, côté
`features/routes.py`, et côté `harvest/routes.py`).

**Décision : mirroring.** Diff strictement additif (aucun fichier route
existant modifié), cohérent avec les 12 précédents. Le coût est une
duplication de dispatch à trois endroits (shell, REST, MCP) au lieu de
deux — mais l'extraction est un refactor transverse indépendant de ce que
SP-14l doit livrer ; à faire quand la duplication cause un vrai bug, pas par
anticipation.

## 6. Permissions

Même vérification à double niveau que SP-14a §5/SP-14k §6, transposée aux
trois outils : lire le *dataset* (objet catalogué, `can()`) est indépendant
de lire les *données* qu'il référence (collection ou item `external`
moissonné). `create_dataset` vérifie l'accès aux données à la création
(`_validate_dataset`) ; `run_analytics_query`/`explain_dataset` le
revérifient à chaque appel, indépendamment de la lisibilité du dataset —
un dataset partagé plus largement que sa source ne donne donc jamais accès
aux données sous-jacentes, seulement à la référence (même garantie que la
route REST équivalente).

`run_analytics_query` ne requiert **pas** le rôle analyste : il exécute des
requêtes structurées avec le même profil de risque que
`/collections/{id}/aggregate` (qui n'a pas ce garde-fou), pas du SQL libre
comme `/analytics/sql` (qui l'a).

## 7. Compatibilité & tests

Compatibilité : additif pur — `create_dataset` est un outil MCP entièrement
nouveau, distinct de `create_item` (§2) ; aucun outil existant modifié ;
aucun schéma de config changé.

**Core (unitaires, `core/tests/test_mcp_tools_analytics.py`, patron de
`test_mcp_tools_create_form_app.py`/`test_mcp_tools_query_features.py`)** :

- `create_dataset` : source `collection` et `arcgis` valides → dataset créé
  + audité ; collection/couche ArcGIS invisible à l'utilisateur → `ValueError`
  (pas de fuite d'existence, même message que la route REST) ; mode
  lecture seule → `ValueError`, rien créé.
- `run_analytics_query` : source `collection` → résultat agrégé identique à
  l'appel direct de `run_collection_aggregate` ; source `arcgis` → résultat
  agrégé via un serveur ArcGIS mocké (même patron de test que SP-14k) ;
  `bucket`/`split`/`bins` sur source `arcgis` → `ValueError` ; dataset
  lisible mais collection/couche sous-jacente non lisible → `ValueError`,
  pas de fuite ; `datasetId` inexistant ou non-dataset → `ValueError`.
- `explain_dataset` : `fields` cohérents avec le schéma introspecté d'une
  collection de test ; `columns` reflète les métadonnées auteur telles que
  stockées ; source `arcgis` → `fields` extrait d'une réponse `f=json`
  mockée ; permissions identiques à `run_analytics_query`.

Aucun test shell/E2E nouveau : ces outils n'ont pas de surface UI — ils
sont exercés par un client MCP, comme les 12 existants (dont aucun n'a de
spec E2E Playwright dédiée). Les 82+ specs E2E existantes restent vertes
sans modification (aucune n'exerce le serveur MCP).

## 8. Risques

| Risque | Garde-fou |
|---|---|
| `create_dataset` sans `_validate_dataset` créerait une brèche (dataset pointant vers une source invisible à l'auteur) | Appel explicite obligatoire, testé (voir §7) — même hook que la route REST |
| Import de fonctions privées de route (`get_duckdb_connection_factory`, `_resolve_arcgis_dataset`) depuis `mcp/tools.py` | Autorisé par le contrat `import-linter` (« layered architecture » : `app.mcp` au-dessus de `app.features`/`app.harvest`) ; cohérent avec les imports déjà faits par `query_features`/`create_form_app` vers `app.features`/`app.collections` |
| `explain_dataset` sur `arcgis` fait un appel réseau live à chaque invocation | Même profil que `run_analytics_query` côté `arcgis` (déjà live, déjà garde d'egress) — pas un nouveau mode de panne |
| Duplication du dispatch `collection`/`arcgis` à un troisième endroit (MCP, en plus de shell et REST) | Choix assumé (§5) — mirroring cohérent avec les 12 outils existants, extraction différée à un besoin réel |
| Un agent MCP pourrait tenter d'itérer `run_analytics_query` avec des `groupBy` devinés au hasard avant d'appeler `explain_dataset` | Pas un nouveau risque : même exposition que `query_features` aujourd'hui (erreur `unknown_field` propre, pas de crash) ; `explain_dataset` réduit ce risque, ne l'élimine pas — hors périmètre de le bloquer davantage (ex. quota de tentatives) |

# SP-15a — Pipeline : socle headless + capacité optionnelle (design)

> **Date : 2026-08-05 · Statut : validé (brainstorm = étude de faisabilité)**
> Première sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**). Le brainstorm de ce chantier a déjà
> eu lieu et est tranché : voir l'étude de faisabilité
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> (Go cœur-first, runtime deux étages, roadmap phasée §5). Ce document ne
> couvre que sa **Phase 1** : le document `Pipeline`, le runtime étage 1
> (DuckDB in-process), l'exécution procrastinate, et — nouveau par rapport à
> la Phase 1 telle que décrite dans l'étude — **le cadrage de tout le
> chantier SP-15 comme capacité optionnelle activable/désactivable**, dès ce
> premier sous-plan plutôt qu'en aval. Les autres phases (canvas no-code,
> spatial + sidecar `qgis_process`, automatisation/triggers) sont **hors
> périmètre**, réservées à SP-15b et suivants.
>
> Références : feuille de route (§SP-15, A39, ligne 234-249 et 702-707) ·
> `CLAUDE.md` (règles d'architecture #1-4, arbitrages figés) · SP-14a
> (`2026-07-25-sp14a-datasets-partages-design.md`, patron de découpage en
> sous-parties d'un chantier trop large pour un plan unique) · SP-11b/SP-11c
> (runtime DuckDB analytique réutilisé) · SP-12c (`HarvestConnector`,
> abstraction étendue en Phase 3, pas ici) · SP-9 (`CORE_READ_ONLY_MODE`,
> patron de capacité togglable réutilisé pour la nouvelle capacité).

## 1. Objectif & non-buts

**Objectif.** Poser le socle headless du moteur ETL : un document déclaratif
`Pipeline` (graphe `reader → transform → writer`), un runtime étage 1 (DuckDB,
déjà présent depuis SP-11 ; les expressions `filter`/`derive` sont du SQL
DuckDB borné, pas du CEL — correction §5.1), une exécution asynchrone via
procrastinate, et un catalogue de 8 opérations de données pures. Auteur **via
MCP/JSON uniquement** — pas de canvas. Un agent (ou un appel API direct) doit
pouvoir créer un pipeline « nettoyer un CSV importé →
écrire dans une collection » et l'exécuter.

**Second objectif, propre à ce sous-plan** (répond à la demande explicite de
Tanguy de cadrer la brique ETL comme optionnelle dès le départ, pas seulement
pour le sidecar GPL de Phase 3) : faire de **l'ensemble du chantier SP-15**
une capacité instance-wide activable/désactivable par variable d'environnement
(`CORE_ETL_ENABLED`), dans l'esprit du profil compose `observability` et du
mode démo `CORE_READ_ONLY_MODE` (SP-9) — un déploiement existant qui monte en
version ne voit **rien de nouveau tant qu'il n'a pas explicitement activé la
capacité**, et l'installeur (`scripts/install.sh`, SP-Deploy-c) qui affiche
déjà une ligne « ETL no-code (SP-15) — à venir » peut désormais réellement la
proposer.

**Non-buts explicites** (reportés à SP-15b et suivants) :

- **Canvas no-code** (`PipelineBuilderPage`, drag & drop, inspecteur,
  aperçu de données) — Phase 2 de l'étude de faisabilité.
- **Transformers spatiaux** (reproject, buffer, intersection, within, H3) et
  **sidecar `qgis_process`** (profil compose `etl`, étage 2) — Phase 3.
- **`reader.connector`** (dlt, REST/Postgres), **`refreshPolicy`**
  (interval/scheduled) et **triggers événementiels** — Phase 3/4.
- **`transform.sql`** (échappatoire DuckDB brut réservé au rôle analyste,
  sandboxé comme `POST /analytics/sql`) — Phase 4, inutile tant qu'il n'y a
  pas de canvas pour l'exposer prudemment.
- **Fusion/push-down** de plusieurs nœuds en une seule requête DuckDB
  (optimisation) — l'exécution Phase 1 est **nœud-par-nœud, matérialisation
  systématique** (mitigation D4 de l'étude), suffisante pour un MVP moteur.
- **Interface de gestion des capacités instance** (écran admin pour activer
  des toggles) — hors périmètre : `CORE_ETL_ENABLED` est une variable
  d'environnement au démarrage, pas un réglage runtime en base.

Le modèle reste additif : rien ici ne doit devoir être défait pour ajouter le
canvas, le spatial, les connecteurs ou les triggers ensuite.

## 2. Rappel : ce que SP-15 subsume, ce que SP-14 garde

L'amendement A39 (feuille de route, ligne 702-707) est déjà tranché, rappelé
ici pour mémoire de session (ne pas re-débattre, CLAUDE.md) :

- Le « pipeline de transformations déclaratif » évoqué dans le brainstorm
  Analytics (SP-14/A28) **migre entièrement ici**. Le document `Pipeline` de
  SP-15, avec un nœud `writer.dataset` (ajouté en Phase 3, cf. étude §3.2
  point 4), **est** ce pipeline.
- SP-14 garde l'UX analytique pure (requête visuelle, contexte global,
  cross-filter, SQL Lab) et **consommera** les datasets produits par ce
  moteur — pas de deuxième moteur de transformation (règle d'architecture
  #3). SP-14a (`DatasetPayload.source: Literal["collection"]`) n'est pas
  modifié par ce sous-plan : un dataset alimenté par un pipeline est un
  développement de SP-15b/c qui ajoutera une valeur `"pipeline"` à ce
  littéral union, pas ici.

## 3. La brique ETL comme capacité optionnelle

### 3.1 Le flag : `CORE_ETL_ENABLED`

Nouvelle fonction dans `core/app/auth/dependency.py`, **exactement le même
patron** que `is_read_only_mode` (ligne 19-23 du fichier, lue à chaque appel
sans cache pour que les tests basculent via `monkeypatch` sans recréer
l'app) :

```python
def is_etl_enabled() -> bool:
    """CORE_ETL_ENABLED (SP-15) — capacité instance-wide optionnelle, même
    convention que is_read_only_mode : lue à chaque appel, sans cache."""
    return os.environ.get("CORE_ETL_ENABLED", "false").lower() == "true"
```

**Défaut : `false`.** Un déploiement qui met à jour son image cœur sans
toucher son `.env` ne voit apparaître ni route, ni entrée MCP, ni (plus
tard) menu — cohérent avec le principe « une capacité lourde qui monte en
version ne s'active jamais silencieusement ». `.env.example` documente la
variable juste après `CORE_READ_ONLY_MODE`.

### 3.2 Où le flag agit

| Surface | Comportement si `CORE_ETL_ENABLED=false` |
|---|---|
| `GET /instance` | `etlEnabled: false` dans la réponse (§3.3) |
| `POST /configs` avec `kind: "pipeline"` | `403` (même mécanique que `is_read_only_mode` dans le middleware — dépendance FastAPI dédiée, pas un test ad hoc dans chaque route) |
| Toutes les routes `/pipelines/*` (§7) | `404` — le routeur n'est monté que si le flag est actif (voir `main.py`, patron d'inclusion conditionnelle des routeurs déjà utilisé pour l'extension registry SP-8c) |
| Outils MCP `create_pipeline`/`run_pipeline`/`explain_pipeline` | non enregistrés sur le serveur MCP (le serveur lit le flag une fois au démarrage du process ; cohérent avec le fait que ces process redémarrent au déploiement) |
| Worker procrastinate | `app.pipelines.jobs` reste importé (le worker est un process partagé, pas la peine de le reconfigurer) mais aucune tâche ne peut jamais y être déférée puisque les routes qui déferraient sont elles-mêmes coupées en amont — pas de garde redondante dans la tâche elle-même |
| Shell (futur, SP-15b+) | lira `etlEnabled` depuis `/instance` (comme `readOnly` est déjà lu, cf. `shell/src/api/instanceClient` — nom exact à vérifier en Phase 2) pour masquer toute entrée « Nouveau pipeline » ; **aucun changement shell dans ce sous-plan**, il n'y a pas encore d'UI à masquer, mais le contrat `/instance` est posé maintenant pour que SP-15b n'ait rien à redessiner |

**Choix de conception : coupure serveur, pas seulement cosmétique.** Une
capacité optionnelle qui ne masquerait qu'un bouton shell resterait
accessible par appel API direct ou par un agent MCP mal informé — c'est le
même raisonnement que `CORE_READ_ONLY_MODE`, qui bloque les écritures au
niveau du middleware, pas seulement au niveau du bouton grisé du shell.

### 3.3 `GET /instance`

Extension additive de `core/app/instance/routes.py` (fichier existant,
2 lignes de logique aujourd'hui) :

```python
@router.get("/instance")
def get_instance_info() -> dict:
    return {"readOnly": is_read_only_mode(), "etlEnabled": is_etl_enabled()}
```

Pas de schéma Pydantic dédié à casser : la route retourne déjà un `dict` nu.

### 3.4 Docker Compose : rien de nouveau dans ce sous-plan

Le sidecar `qgis-worker` et le profil compose `etl` (étage 2, Phase 3) ne
sont **pas** introduits ici — le runtime étage 1 tourne dans le `worker`
existant (`docker-compose.yml`, service `worker`, déjà démarré par défaut).
`CORE_ETL_ENABLED` est donc **indépendant des profils compose** : c'est un
interrupteur applicatif (route/MCP), pas un interrupteur d'infrastructure.
Les deux se rejoignent en Phase 3 : le profil `etl` contrôlera le sidecar
GPL, `CORE_ETL_ENABLED` contrôlera l'exposition de toute la fonctionnalité —
un déploiement peut activer `CORE_ETL_ENABLED=true` sans jamais démarrer le
profil `etl`, et se limiter aux transformers étage 1.

`scripts/install.sh` (SP-Deploy-c) n'a **rien à modifier ici** : sa ligne
`(ETL no-code (SP-15) — à venir, pas encore disponible dans ce dépôt)` reste
correcte tant qu'aucun profil compose `etl` n'existe (Phase 3). Le
`CORE_ETL_ENABLED` applicatif est un réglage `.env` orthogonal, hors du menu
de profils de l'installeur — noté ici pour que SP-15c (qui introduira le
profil `etl`) sache qu'il devra probablement proposer les deux réglages
ensemble dans le prompt installeur, pas juste le profil.

## 4. Modèle de données

### 4.1 Le document `Pipeline` — un `BuilderConfig.kind` de plus

Réutilisation stricte du patron kind-discriminé (`core/app/configs/schemas.py`,
déjà étendu pour `"site"` en SP-13a puis `"dataset"`/`"bookmark"` en
SP-13a/14a/14m) — **pas de nouveau mécanisme d'item**, un pipeline est un
item comme les autres :

```python
class BuilderConfig(BaseModel):
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline"]
    # ...
    pipeline: PipelinePayload | None = None   # miroir de dataset: DatasetPayload | None
```

`_require_kind_payload` (lignes 186-196) gagne une branche `"pipeline"` →
exige `pipeline`. `core/app/configs/routes.py` continue de fixer
`resource_type = request.config.kind` (ligne 81, inchangé).

```python
class PipelineNode(BaseModel):
    id: str
    kind: Literal["reader", "transform", "writer"]
    op: str                      # "reader.collection", "transform.filter", "writer.export"…
    x: int = 0
    y: int = 0                   # idiome LayoutItem — inutilisé tant qu'il n'y a pas de canvas,
                                 # posé maintenant pour que SP-15b n'ait pas à migrer le schéma
    params: dict[str, Any] = {}  # validé contre le manifeste de l'op, §5.2
    title: str | None = None

class PipelineEdge(BaseModel):
    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None      # CEL, routage conditionnel — idiome Message.when (A8) ;
                                 # accepté dans le schéma dès Phase 1 par cohérence de modèle,
                                 # mais non-interprété par le compilateur (§6) avant Phase 3/4

class PipelinePayload(BaseModel):
    nodes: list[PipelineNode]
    edges: list[PipelineEdge]

    @model_validator(mode="after")
    def _validate_graph(self) -> "PipelinePayload":
        # unicité des ids de nœuds, arêtes référençant des nœuds existants,
        # au moins un reader et un writer — DAG-acyclique vérifié séparément
        # à l'exécution (§6.1), pas dupliqué ici (cf. leçon round-trip visibleWhen SP-5b :
        # la validation structurelle légère vit dans le schéma, la validation
        # sémantique lourde (types de ports, DAG) vit dans le compilateur)
        ...
```

**Pourquoi accepter `x`/`y` et `when` dès Phase 1 sans les utiliser** : ajouter
ces champs plus tard casserait la compatibilité ascendante des pipelines créés
via MCP en Phase 1 (un pipeline « nettoyer CSV » créé aujourd'hui doit encore
se charger dans le canvas de SP-15b sans migration). C'est le même choix que
SP-13a a fait pour `LayoutItem.x/y` avant que l'éditeur drag-and-drop existe.

### 4.2 Validation serveur — `core/app/configs/pipeline_validation.py`

Nouveau fichier, miroir exact de `dataset_validation.py` (import dans
`configs/routes.py`, appelé aux mêmes trois points create/update, ligne
76/127/227) :

- DAG acyclique (tri topologique, rejeté si cycle).
- Chaque `node.op` existe dans le catalogue (§5), chaque `node.params` valide
  contre le manifeste Pydantic de l'op (erreurs de champ précises, pas un
  simple booléen — même esprit que les erreurs `visibleWhen`/CEL déjà
  remontées ligne à ligne côté shell).
- `reader.collection.params.collectionId` référence une collection existante
  et **lisible par l'utilisateur courant** (même vérification que
  `dataset_validation.py` pour `collectionId`) ; `writer.collection`
  vérifie en plus l'**écriture** (RLS/`can()` collection, pas dupliquée : la
  vérification définitive a lieu à l'exécution du job, celle-ci n'est qu'un
  filet à la sauvegarde, cf. §8).

## 5. Catalogue d'opérations — Phase 1 (données pures uniquement)

Six `op`, chacune un modèle Pydantic de paramètres dans
`core/app/pipelines/ops/schemas.py` — c'est le manifeste typé annoncé par
l'étude (§3.1), publié en JSON Schema (§7.3) pour que Phase 2 réutilise
**telle quelle** la génération de panneau `WcWidgetManifest`/
`generatedPropsPanel` (`shell/src/builder/wc/manifest.ts`,
`generatedPropsPanel.tsx`) sans redesign :

| `op` | Rôle | Params (esquisse) |
|---|---|---|
| `reader.collection` | Source = une collection existante | `collectionId: str` |
| `transform.filter` | Filtre attributaire | `expr: str` (SQL DuckDB borné, cf. correction §5.1) |
| `transform.select` | Projection/renommage de colonnes | `columns: dict[str, str \| None]` |
| `transform.derive` | Colonne calculée | `column: str, expr: str` (SQL DuckDB borné, cf. correction §5.1) |
| `transform.aggregate` | Group-by + agrégats | `groupBy: list[str], metrics: dict[str, str]` |
| `transform.join` | Jointure sur clé | `withCollectionId: str, on: str, how: Literal["inner","left"]` |
| `writer.collection` | Écrit le résultat dans une collection (existante ou nouvelle) | `collectionId: str \| None, createIfMissing: bool` |
| `writer.export` | Écrit un extrait GeoJSON/CSV sur S3 | `format: Literal["geojson","csv"], key: str` |

(8 ops listées, dans la fourchette 6-8 de l'étude §5 Phase 1.) Le catalogue
complet — spatial étage 1, `qgis:*` étage 2, `reader.connector` — arrive en
Phase 3, additivement (nouveau littéral d'union sur `op`, pas de refonte).

### 5.1 Correction : `filter.expr`/`derive.expr` sont du SQL DuckDB, pas du CEL

L'étude de faisabilité (§2.3) affirmait que CEL était « ✅ déjà » disponible
côté serveur pour ces deux ops. **C'est inexact** : `cel-js` n'existe que
côté shell (`shell/src/builder/expr.ts`), jamais importé dans `core/` — il
n'y a **aucun** moteur CEL Python dans le cœur aujourd'hui, malgré le
commentaire de `app/mcp/form_app.py` qui évoque « cel-js/cel-python » comme
alternatives jamais tranchées (A8 couvre l'usage shell, pas le cœur).

Décision (tranchée par Tanguy en session, pas re-débattue) : `filter.expr` et
`derive.expr` sont des **expressions scalaires SQL DuckDB bornées** (ex.
`"pop > 1000"`, `"pop * 2"`), validées par le **même mécanisme AST** que
`app/analytics/sql_sandbox.py` (`json_serialize_sql` → un seul nœud
expression, pas un `SELECT` complet, aucune sous-requête/DDL/fonction de
lecture de fichier). Zéro nouvelle dépendance, cohérent avec un runtime qui
compile déjà tout vers des vues DuckDB — introduire un évaluateur CEL séparé
aurait cassé ce modèle (aller-retour DuckDB→Python par ligne pour un
sous-ensemble d'ops seulement). Portée strictement plus étroite que le futur
`transform.sql` de Phase 4 (une expression, jamais une requête). L'alignement
CEL de l'étude de faisabilité (et, plus largement, la question d'un moteur
CEL serveur pour d'autres besoins que celui-ci) reste **ouvert**, hors
périmètre de ce sous-plan.

## 6. Compilation & exécution

### 6.1 Compilation

1. **Validation** — déjà faite à la sauvegarde (§4.2) ; revalidée à
   l'exécution par défense en profondeur (le graphe en base a pu être créé
   avant un changement de schéma de collection).
2. **Tri topologique** → liste ordonnée de nœuds.
3. **Pas de fusion** (non-but §1) : chaque nœud produit une **vue DuckDB
   matérialisée** (`CREATE TEMP VIEW node_<id> AS <SQL>`), le nœud suivant
   lit la vue de son prédécesseur. Chaque op de transformation compile vers
   un fragment SQL généré (pas de SQL utilisateur libre en Phase 1 —
   `transform.sql` arrive en Phase 4, sandboxé).

### 6.2 Exécution — réutilise le runtime SP-11b tel quel

- **Connexion** : `app.analytics.duckdb_conn.open_connection`, **même
  fonction**, même patron in-process/éphémère par run (pas de pool, cf.
  grounding §2). Pas de nouvelle configuration DuckDB à inventer.
- **Lecture** (`reader.collection`) : **même requête de dédoublonnage
  GeoParquet CDC** que `app.analytics.aggregate._dedup_cte`
  (`read_parquet(..., hive_partitioning=true)` + `QUALIFY row_number() ...`),
  appelée directement — pas de duplication de logique.
- **Écriture** (`writer.collection`) : passe par le **chemin d'écriture OGC
  API Features existant** (transactions Part 4, déjà auditées) — un pipeline
  n'écrit jamais directement en base ou en GeoParquet, il ré-émet des
  features via la même primitive que n'importe quel client OGC. Aucune
  frontière d'autorisation nouvelle.
- **Écriture export** (`writer.export`) : upload S3 direct (patron présigné
  déjà utilisé pour les exports SP-16/thumbnails).

### 6.3 Run = job procrastinate

Nouveau module `core/app/pipelines/` (frontière import-linter à ajouter dans
`core/pyproject.toml`, `[tool.importlinter]` — position dans la liste
`layers` à déterminer par sa direction de dépendance réelle : `pipelines`
dépend de `collections`/`configs`/`analytics`, donc listé **avant** eux dans
la couche, comme `harvest`/`ingestion` le sont déjà) :

- `core/app/pipelines/models.py` — table `pipeline_runs` (id, tenant_id,
  pipeline_item_id FK, status `queued|running|succeeded|failed`, started_at,
  finished_at, error, node_stats jsonb) ; migration Alembic
  **`0018_pipeline_runs.py`** (`down_revision = "0017"`, cf. grounding §9).
- `core/app/pipelines/jobs.py` — `run_pipeline_task(run_id, tenant_id)`,
  `@app.task(queue="etl")` (nouvelle queue dédiée, cf. étude §3.2 point 5) ;
  **même patron try/except-toujours-marquer-erreur** que
  `run_ingestion_task` (jamais de run "zombie" en `running`) ; ajouté à
  `import_paths` de `core/app/jobs.py` et à la commande worker du
  `docker-compose.yml` (`-q ingestion,search,cdc,etl`).
- `core/app/pipelines/routes.py` — `POST /pipelines/{id}/run` (défère la
  tâche **après** `session.commit()`, même raison documentée que
  `ingestion/routes.py` ligne 122) ; `GET /pipelines/{id}/runs` (historique) ;
  `POST /pipelines/{id}/preview?upTo=<nodeId>` (exécution **synchrone**,
  bornée `LIMIT 50`, pas de job — même esprit que le `ROW_CAP`/
  `STATEMENT_TIMEOUT_S` de `sql_sandbox.py`, réutilisés tels quels) ;
  `GET /pipelines/ops` (catalogue + JSON Schema des manifestes, cf. §5).
- Toutes ces routes sont montées **seulement si** `is_etl_enabled()` est
  vrai au démarrage du process (§3.2) — sinon non enregistrées sur le
  routeur FastAPI (pas un simple garde par requête : la route n'existe pas,
  d'où le `404` plutôt que `403`, cohérent avec l'absence de la fonctionnalité
  plutôt qu'un refus d'accès).
- Statut poll-able : même patron shell que `ImportFileButton.tsx` (`poll()`
  toutes les 1500 ms) — réutilisable tel quel par un futur bouton Run en
  Phase 2, posé ici uniquement côté MCP/API (`run_pipeline` retourne
  `runId`, un second appel `explain_pipeline` ou un futur `get_pipeline_run`
  MCP renvoie le statut).

## 7. Permissions & sécurité

- Le `Pipeline` est un item : `can(user, action, item)`, `audit_log`
  (`pipeline.create`/`pipeline.run`), `tenant_id` — identique à tout autre
  item, aucune nouvelle porte d'autorisation (règle d'architecture #2, un
  seul `can()`).
- **Double vérification à l'exécution**, même principe que SP-14a §5 pour
  les datasets : lire/éditer le *document* Pipeline est une chose ; à
  l'exécution du job, `reader.collection`/`writer.collection` re-vérifient
  indépendamment les droits sur les collections référencées (RLS déjà en
  place) — un pipeline partagé plus largement que ses collections sources ou
  cible ne donne donc jamais un accès élargi aux données, seulement à la
  définition du graphe.
- `writer.collection` avec `createIfMissing: true` crée une collection via
  la primitive existante (même autorisation que la création manuelle d'une
  collection — pas de contournement).
- Aucun échappatoire SQL libre en Phase 1 (`transform.sql` différé à Phase 4,
  cf. non-buts) : rien à sandboxer au-delà du SQL généré par le compilateur,
  qui n'expose jamais de paramètre utilisateur non typé dans une chaîne SQL
  brute (les valeurs passent en paramètres liés DuckDB, jamais en
  concaténation).

## 8. MCP

`core/app/mcp/tools.py` gagne trois outils, **enregistrés uniquement si
`is_etl_enabled()`** (le serveur MCP lit le flag une fois à son démarrage,
§3.2) — même structure que `create_dataset`/`run_analytics_query`/
`explain_dataset` (SP-14l, mêmes fonctions repository + `can()`,
`actor_kind="agent"`) :

- `create_pipeline(name, nodes, edges)` — crée l'item + le config
  `kind="pipeline"`, audité.
- `run_pipeline(pipelineId)` — défère le job, retourne `runId` (poll côté
  agent via un futur `GET /pipelines/{id}/runs` déjà exposé en REST — pas
  besoin d'un outil MCP de poll dédié en Phase 1, l'agent peut relire la
  ressource).
- `explain_pipeline(pipelineId)` — décrit le graphe en langage naturel
  (nœuds, ops, connexions) à partir du document, sans l'exécuter — même
  esprit que `explain_dataset`.

## 9. Compatibilité & tests

- Aucune migration de schéma existant : `"pipeline"` est un nouveau
  littéral additif sur `BuilderConfig.kind` (comme `"bookmark"` en SP-14m),
  `pipeline_runs` une **nouvelle** table. Les 18 specs E2E existantes
  restent vertes sans modification (pas de nouvelle UI shell dans ce
  sous-plan).
- Nouveaux tests cœur (pytest) :
  - `is_etl_enabled()` : lecture env var, défaut `false`.
  - `GET /instance` retourne `etlEnabled` cohérent avec l'env var
    (monkeypatch, comme les tests existants de `readOnly`).
  - Routes `/pipelines/*` et `POST /configs` `kind="pipeline"` → `403`/`404`
    quand `CORE_ETL_ENABLED=false` ; comportement normal quand `true`.
  - Validation du graphe (`pipeline_validation.py`) : cycle rejeté, `op`
    inconnu rejeté, params invalides rejetés champ par champ,
    `collectionId` inexistant/non lisible rejeté.
  - Round-trip Pydantic↔TS du schéma `Pipeline` (mémo explicite : éviter la
    régression de round-trip déjà rencontrée sur `visibleWhen`, SP-5b —
    l'étude de faisabilité le mentionne aussi, §3.1).
  - Exécution bout-en-bout : pipeline « lire collection A → filter → écrire
    collection B », job procrastinate exécuté en test (comme les tests
    d'ingestion), résultat vérifié dans B.
  - `POST /pipelines/{id}/preview` : borné (LIMIT 50), ne mute rien.
  - MCP : `create_pipeline`/`run_pipeline`/`explain_pipeline` absents du
    tool listing quand `CORE_ETL_ENABLED=false`.
- Pas de test Playwright/Vitest nouveau : aucune surface shell dans ce
  sous-plan (cohérent avec le non-but §1 « pas de canvas »).

## 10. Risques

| Risque | Garde-fou |
|---|---|
| Le flag `CORE_ETL_ENABLED` devient un deuxième système de permissions parallèle à `can()` | Il ne gère jamais le *qui* (ça reste `can()`/RLS), seulement le *si la fonctionnalité existe sur cette instance* — même rôle que `CORE_READ_ONLY_MODE`, pas un rôle utilisateur |
| Exécution nœud-par-nœud (sans fusion) trop lente sur des graphes profonds | Accepté pour ce MVP (mitigation D4 de l'étude) ; l'optimisation de fusion est un chantier de perf isolé, postérieur, qui ne change pas le contrat du document `Pipeline` |
| `x`/`y`/`when` acceptés sans effet créent une confusion (« pourquoi ce champ ne fait rien ? ») | Documenté explicitement dans le schéma (docstring Pydantic) et ici (§4.1) — même stratégie que `LayoutItem.x/y` avant l'éditeur visuel |
| Oubli de propager `CORE_ETL_ENABLED` dans `.env.example`/docs d'installation | Ajouté dans ce sous-plan en même temps que le code (Task dédiée à l'exécution), pas différé |
| Deux moteurs de transformation si SP-14 réintroduit un pipeline inline par erreur | Rappel §2 : `DatasetPayload.source` reste `Literal["collection"]` tant que SP-15b n'ajoute pas `"pipeline"` explicitement — non-but explicite ici |

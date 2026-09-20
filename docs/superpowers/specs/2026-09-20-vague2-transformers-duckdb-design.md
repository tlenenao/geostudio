# Vague 2 des transformers/lecteurs `planned_duckdb` — 20 nouvelles op

**Date** : 2026-09-20
**Demande** : « lance une spec pour réaliser tous les transformers duckdb restant », puis « rajoute tous les
readers et writers » (précisé ensuite : lecteurs SQL par dialecte + lecteurs objet/fichiers tabulaires
DuckDB — pas le bloc SaaS bespoke, pas un nouveau `writer.connector.*`, ces deux derniers restant hors
périmètre, cf. §6).
**Référence** : `docs/superpowers/specs/2026-09-17-vague1-transformers-duckdb-design.md` (Vague 1, 15 op livrées,
catalogue à 34 op) — son §3.2 cartographiait le reste des 90 lignes `planned_duckdb` en familles et concluait
que « construire les 90 transformers » est un programme, pas un chantier. Ce document exécute la **prochaine**
tranche, choisie par Tanguy parmi les familles cartographiées : la famille « schéma dynamique » (~8 lignes,
§1-§4), la famille « cardinalité/ordre changé » (~4 lignes, §1-§4), et deux sous-familles de lecteurs
identifiées par Vague 1 §3.2 comme les candidats les plus sûrs du reste de la matrice (§6) — 12 transformers
FME de transformation + 9 lignes FME de lecture (« Google BigQuery », « Microsoft SQL Server Spatial »,
« Oracle Spatial Relational », « Apache Parquet », « CSV », « JSON », « S3Connector », «
AzureBlobStorageConnector », « GoogleCloudStorageConnector »).

Une 3e demande, dans la même conversation — retirer le sidecar QGIS (GPL-2.0-or-later) — a été décomposée à
part (impact : 19 lignes `qgis_frozen`, dont 6 raster sans équivalent DuckDB et 2 cas de triangulation
incertains, cf. classification en tête de tâche). Tanguy n'a retenu, pour **ce document**, que le sous-ensemble
qui est en réalité un chantier de même nature que le reste de cette spec — de nouvelles op `transform.*` pures
DuckDB — sans toucher au sidecar lui-même : **§8** couvre cette migration vecteur. Le retrait mécanique du
sidecar (docker-compose, `CORE_ETL_ENABLED`, migration des pipelines prod existants), le chemin GDAL direct
pour les 6 op raster, et les 2 cas de triangulation restent explicitement hors de ce document (§9) — le
sidecar QGIS continue de tourner et de servir les lignes non couvertes par §8.

## 0. Constat de départ — le texte de Vague 1 se trompe sur l'ampleur du problème (vérifié, pas supposé)

Vague 1 §1 affirmait que ces deux familles exigeaient un nouveau mécanisme d'exécution : soit étendre
`compile_transform_sql` pour recevoir une connexion DuckDB, soit traiter ces op comme `transform.qgis`
(exécution inline dans `runtime.py`, `compile=None`). En testant contre un DuckDB réel (piège CLAUDE.md n°3 —
jamais contre la documentation seule), cette prémisse s'avère en grande partie fausse :

- **`SELECT COLUMNS(c -> c LIKE 'foo_%') FROM t`** — sélection dynamique par motif, déjà utilisée par
  `_compile_create_geometry`/`_compile_concat_coordinates` (`compiler.py` existant).
- **`SELECT * EXCLUDE(foo_a, foo_b), COLUMNS('foo_(.*)') AS '\1_renamed' FROM t`** → colonnes `a_renamed`,
  `b_renamed` — **renommage en masse par regex avec rétro-référence**, testé et confirmé, jamais utilisé dans
  ce dépôt jusqu'ici.
- **`SELECT * FROM (DESCRIBE t)`** — `DESCRIBE` s'utilise comme une sous-requête ordinaire, donc comme
  n'importe quelle vue (`CREATE TEMP VIEW v AS SELECT column_name, column_type FROM (DESCRIBE t)` testé et
  confirmé).
- **`SELECT id, payload.* FROM t`** (`payload` une colonne STRUCT) — expansion dynamique des champs d'une
  colonne imbriquée, sans connaître leurs noms à l'avance.
- **`SELECT unnest(ST_Dump(geometry)).geom AS geometry FROM t`** — **change le nombre de lignes en sortie**
  (`MULTIPOINT (0 0, 1 1, 2 2)` → 3 lignes, testé et confirmé). Vague 1 affirmait qu'aucun op ne pouvait changer
  la cardinalité (« transform.select/transform.derive produisent toujours exactement une ligne de sortie par
  ligne d'entrée ») — c'est vrai de ces deux op précis, pas d'une limite de `compile_transform_sql`/
  `runtime.py` : `CREATE TEMP VIEW … AS {sql}` (ligne 732 de `runtime.py`) accepte n'importe quelle requête,
  y compris une qui change le nombre de lignes. Rien dans le runtime ne suppose 1:1.
- **`ORDER BY`** dans une vue survit empiriquement à travers une chaîne de vues (testé : 20 000 lignes,
  8 threads, tri → vue intermédiaire de projection → vue avec fonction fenêtrée — ordre préservé dans les
  trois cas). Ce n'est **pas une garantie documentée** de DuckDB — juste un comportement observé à cette
  échelle (voir §3.3, décision assumée sur ce point précis).

**Conséquence** : sur les 12 transformers FME des deux familles, **seuls 3** (ChangeDetector, FeatureMerger,
SchemaMapper) ont un besoin réel d'introspection dynamique qu'aucune primitive SQL statique ne couvre —
comparer les colonnes communes de **deux** relations dont l'ensemble n'est connu qu'à l'exécution.
`struct_pack(COLUMNS(...))` a été testé pour tenter de couvrir aussi FeatureMerger sans introspection : il
produit une liste de structs à un seul champ **par colonne matchée** (`COLUMNS()` duplique l'expression
englobante par colonne, ce n'est pas une agrégation en un seul struct) — pas la sémantique voulue (un struct
unique combinant toutes les colonnes restantes). D'où le besoin réel, mais limité à ces 3 op, d'un mécanisme
d'introspection.

## 1. Ce que ce chantier construit, en une phrase

**20 nouvelles entrées `OperationContract`** : 11 op `transform.*` couvrant les 12 transformers FME des
familles « schéma dynamique » et « cardinalité/ordre changé » (8 en `compile` pur, 3 utilisant une extension
minimale et chirurgicale du contrat — `needs_columns` — pour recevoir la liste des colonnes réelles de
leur(s) entrée(s), jamais une connexion DuckDB dans `compiler.py`, qui reste un module pur) ; 4 nouvelles op
`reader.connector.*` (`bigquery`/`mssql`/`oracle`/`blob`, §6) suivant exactement le patron déjà en production
de `reader.connector.postgres`/`snowflake` ; et 5 nouvelles op `transform.*` remplaçant 7 des 19 lignes
`qgis_frozen` de la matrice par un équivalent DuckDB pur, sans toucher au sidecar QGIS (§8) — catalogue à
34 + 11 + 4 + 5 = **54 op**.

## 2. Périmètre

### 2.1 Dans ce chantier — 11 op couvrant 12 lignes FME

| Op GeoStudio | FME couvert(s) | Mécanisme | Entrée secondaire |
|---|---|---|---|
| `transform.bulkRemoveAttributes` | BulkAttributeRemover | `COLUMNS(c -> …)` | non |
| `transform.bulkRenameAttributes` | BulkAttributeRenamer | `COLUMNS('regex') AS 'repl'` | non |
| `transform.scanSchema` | SchemaScanner | `DESCRIBE` en sous-requête | non |
| `transform.explodeList` | ListExploder | `UNNEST(list_col)` | non |
| `transform.explodeGeometry` | Deaggregator | `UNNEST(ST_Dump(geometry))` | non |
| `transform.exposeAttributes` | AttributeExposer | `struct_col.*` | non |
| `transform.validateAttributes` | AttributeValidator | fonctions fenêtre sur colonnes **explicites** (param typé, pas de mode « toutes colonnes automatique ») | non |
| `transform.sort` | Sorter + SpatialSorter | `ORDER BY`, `ST_Hilbert(geometry)` en clé optionnelle | non |
| `transform.detectChanges` | ChangeDetector | FULL OUTER JOIN + comparaison dynamique des colonnes communes | **oui** (`withCollectionId`) |
| `transform.mergeChildren` | FeatureMerger | `GROUP BY` + `list(struct_pack(col1:=col1, …))` construit dynamiquement | **oui** (`withCollectionId`) |
| `transform.mapSchema` | SchemaMapper | liste de colonnes cible **statique** (param), colonnes source résolues dynamiquement | non |

Consolidation assumée (même principe qu'en Vague 1) : Sorter et SpatialSorter deviennent un seul
`transform.sort` — le tri spatial n'est, du point de vue DuckDB, qu'un `ORDER BY` avec `ST_Hilbert(geometry)`
comme expression de tri parmi d'autres, l'idiome documenté par DuckDB lui-même pour ce besoin (noté dans la
matrice, ligne SpatialSorter).

Réductions de périmètre assumées par rapport au comportement FME complet (même esprit que Vague 1 §4.2 —
documentées, pas silencieuses) :

- `transform.validateAttributes` : l'utilisateur liste explicitement les colonnes à tester (non-null,
  unicité) — pas de mode « toutes les colonnes automatiquement », qui échapperait à un `compile` pur sans
  `needs_columns` pour un gain no-code marginal.
- `transform.mapSchema` : correspondance par **nom de colonne identique** entre la liste cible statique et le
  schéma source réel — pas le matching automatique par nom/type flou de SchemaMapper. Pas de résolution
  contre le schéma d'une collection destination (pas de couplage à `writer.collection` ici) : `targetColumns`
  est une liste de noms fournie en param, comme n'importe quel autre param typé de ce catalogue.
- `transform.detectChanges`/`transform.mergeChildren` : entrée secondaire par `withCollectionId` uniquement
  (même patron que `transform.join`/`transform.intersection`/`transform.merge`), pas par une seconde arête
  DAG dédiée — topologie déjà supportée, aucune extension de `PipelineCanvas` nécessaire.

### 2.2 Hors périmètre, inchangé depuis Vague 1

Les ~8 op « déjà atteignables par composition » (AttributeManager, DatabaseJoiner, TestFilter,
GeometryFilter, AttributeRangeFilter, Sampler, AggregateFilter, FeatureTypeFilter), les ~5 « appel externe par
ligne » (HTTPCaller, PythonCaller, SQLExecutor, MCPCaller, Geocoder), les nouveaux lecteurs SQL/fichiers, les
connecteurs de flux et le bloc Integrations restent **hors de ce chantier**, sans changement par rapport à la
carte de Vague 1 §3.2.

## 3. Design — les 11 nouveaux contrats

### 3.1 Fichiers touchés (mêmes 4 fichiers qu'en Vague 1 + `runtime.py`, aucun nouveau fichier)

- `core/app/pipelines/ops/schemas.py` : 11 nouvelles classes `TransformXxxParams(BaseModel)`, patron
  identique aux 34 existantes (champs typés, pas de champ `expr` texte libre sauf pour ce qui est déjà une
  expression SQL bornée dans le catalogue actuel).
- `core/app/pipelines/compiler.py` : 11 nouvelles fonctions `_compile_xxx`. **8 gardent la signature exacte
  des 34 existantes** (`params, *, input_view, join_view=None, input_srid=None`). **3 gagnent deux kwargs
  additionnels** : `_compile_detect_changes`/`_compile_merge_children`/`_compile_map_schema(params, *,
  input_view, join_view=None, input_srid=None, input_columns=None, join_columns=None)`.
- `core/app/pipelines/ops/contracts.py` :
  - nouveau champ `needs_columns: bool = False` sur le dataclass `OperationContract` (défaut `False` —
    aucune des 34 entrées existantes n'est touchée).
  - 11 nouvelles entrées dans `OPERATIONS`, `engine="duckdb"`, `engine_license="MIT (DuckDB)"`.
  - `transform.detectChanges` et `transform.mergeChildren` : `accepts_secondary_input=True`, même patron que
    `transform.join`/`transform.intersection`/`transform.merge` (déjà dans `BINARY_OPS`, dérivé
    automatiquement).
- `core/app/pipelines/compiler.py::compile_transform_sql` : construit le dict de kwargs à passer à
  `contract.compile` — `input_columns`/`join_columns` **seulement si** `contract.needs_columns` est vrai. Les
  34 fonctions existantes ne reçoivent jamais ces deux kwargs, zéro churn dessus.
- `core/app/pipelines/runtime.py::_execute_transform_chain` : avant l'appel à `compile_transform_sql`, si
  l'op du nœud a `needs_columns=True`, résout `input_columns` via `DESCRIBE {input_view}` (patron déjà
  utilisé lignes 365/397 pour d'autres besoins) et `join_columns` via `DESCRIBE {join_view}` si une entrée
  secondaire est branchée — une seule requête `DESCRIBE` bon marché par entrée, uniquement pour les 3 op
  concernées, aucune requête additionnelle pour les 31 autres types de nœud transform.

**Aucun changement à la signature publique de `OperationContract.compile`** au sens Python (`Callable[...,
str]` reste inchangé) — seul le **contenu** des kwargs passés varie selon `needs_columns`, décision prise dans
`compile_transform_sql`, pas dans le type.

### 3.2 Forme des 11 nouvelles classes de params

- `TransformBulkRemoveAttributesParams` : `pattern: str` (regex DuckDB).
- `TransformBulkRenameAttributesParams` : `pattern: str`, `replacement: str` (motif regex + gabarit de
  remplacement avec rétro-référence `\1`, forme directe de `COLUMNS('pattern') AS 'replacement'`).
- `TransformScanSchemaParams` : aucun champ — sortie à colonnes fixes (`columnName`, `columnType`), une ligne
  par colonne de l'entrée.
- `TransformExplodeListParams` : `column: str` (colonne LIST source, explosée en place — une ligne par
  élément, mêmes autres colonnes dupliquées).
- `TransformExplodeGeometryParams` : aucun champ — opère sur la colonne `geometry` conventionnelle, même
  patron que `transform.swapCoordinates`/`transform.setSrid`.
- `TransformExposeAttributesParams` : `column: str` (colonne STRUCT ou LIST-de-STRUCT source, dont les champs
  deviennent des colonnes top-level).
- `TransformValidateAttributesParams` : `nonNullColumns: list[str] = []`, `nonNullResultColumn: str | None`,
  `uniqueColumns: list[str] = []`, `uniqueResultColumn: str | None` — `model_validator` exigeant qu'au moins
  un des deux couples (colonnes + colonne résultat) soit renseigné.
- `TransformSortParams` : `by: list[SortKey] = []` où `SortKey = {column: str, direction: Literal["asc",
  "desc"] = "asc"}`, `bySpatialHilbert: bool = False` (préfixe `ST_Hilbert(geometry)` comme clé de tri
  prioritaire) — `model_validator` exigeant `by` non vide ou `bySpatialHilbert=True`.
- `TransformDetectChangesParams` : `withCollectionId: str | None`, `keyColumns: list[str]`,
  `statusColumn: str` (valeurs `"inserted"|"deleted"|"updated"|"unchanged"`).
- `TransformMergeChildrenParams` : `withCollectionId: str | None`, `on: str` (clé de jointure),
  `childrenColumn: str` (colonne de sortie contenant la liste de structs enfants).
- `TransformMapSchemaParams` : `targetColumns: list[str]` (liste statique des colonnes de sortie voulues,
  dans l'ordre) — toute colonne absente de la source devient `NULL`, toute colonne source hors de cette liste
  est éliminée.

Chaque classe porte une docstring française courte (devient le tooltip du nœud dans `PipelinePalette.tsx`,
même mécanisme que les 34 op existantes — aucun changement front nécessaire, vérifié en Vague 1 §4.4 et
toujours valable : le canevas lit `GET /pipelines/ops` dynamiquement).

### 3.3 `transform.sort` — décision assumée sur la garantie d'ordre

Décision explicite (validée par Tanguy, pas déduite) : **aucune restriction structurelle** sur ce qui peut
suivre un nœud `transform.sort` dans le DAG. L'ordre de sortie est **documenté comme best-effort** au-delà du
nœud writer immédiatement suivant — dans la description du param et dans la doc utilisateur du builder, pas
seulement dans ce design. Le test de falsification (§4) doit néanmoins couvrir le cas simple (sort → writer
direct) à une échelle qui déclenche un vrai parallélisme (assez de lignes pour que DuckDB partitionne le
travail entre threads), pour que « best-effort » repose sur une mesure réelle et pas une intuition — piège
CLAUDE.md n°7 (une assertion de durée/petite échelle ne prouve rien sur une propriété de concurrence).

## 4. Tests (falsifiés avant clôture, piège CLAUDE.md n°10)

- **Un test par `_compile_xxx`** dans `test_pipeline_compiler.py` : SQL généré exécuté contre une vraie
  connexion DuckDB (extension `spatial` chargée), assertion sur le résultat — jamais seulement sur la forme
  de la chaîne SQL. Pour les 3 op `needs_columns`, le test appelle `_compile_xxx` directement avec une liste
  `input_columns`/`join_columns` construite à la main (le compilateur reste testable en pur, sans passer par
  `runtime.py`).
- **Test dédié de résolution des colonnes** dans `test_pipeline_runtime.py` : un pipeline à 2 nœuds utilisant
  `transform.detectChanges` (ou `mergeChildren`/`mapSchema`) exécuté de bout en bout, vérifiant que
  `input_columns`/`join_columns` résolus par `DESCRIBE` correspondent bien au schéma réel de la vue —
  falsification explicite : injecter une colonne renommée entre l'écriture de la config et l'exécution,
  confirmer que le SQL généré s'adapte plutôt que de référencer une colonne disparue.
- **Test de non-régression sur le compte d'op** : `len(OPERATIONS) == 49` (34 + 11 transform + 4 reader — état
  intermédiaire avant les 5 op supplémentaires de §8, qui portent le total final à 54, cf. §8.3).
- **`test_pipeline_routes.py`** : `GET /pipelines/ops` contient les 15 nouvelles clés avec leur
  `kind`/`paramsSchema`.
- **Falsification de l'ordre pour `transform.sort`** (`test_pipeline_runtime.py`) : pipeline reader → sort →
  writer, volume de données suffisant pour forcer un plan multi-thread (vérifier via `EXPLAIN` ou un volume
  empiriquement assez grand — pas une supposition), assertion sur l'ordre exact des lignes en sortie du
  writer. Documenter le résultat (garanti à cette échelle / casse à partir de N lignes) dans le design ou le
  rapport de tâche, pas seulement « le test passe ».
- **`transform.mapSchema`** : test avec une colonne cible absente de la source (doit produire `NULL`, pas une
  erreur) et une colonne source hors de la liste cible (doit être éliminée) — les deux branches de la
  réduction de périmètre assumée en §2.1.
- **`transform.detectChanges`** : test des 4 valeurs de `statusColumn` (`inserted`/`deleted`/`updated`/
  `unchanged`) avec un jeu de données couvrant les 4 cas simultanément (FULL OUTER JOIN mal construit produit
  souvent un faux `unchanged` sur une ligne réellement `updated` — cas à couvrir explicitement).
- **Les 4 op `reader.connector.*`** (§6) : tests dédiés dans `test_pipeline_connector_runtime.py` (patron
  déjà suivi par `materialize_postgres_connector`/`materialize_snowflake_connector` — un secret du mauvais
  `kind` doit être rejeté explicitement, une requête non SELECT-only doit être rejetée par
  `validate_select_only` avant tout appel réseau) — falsification par injection d'un `kind` erroné et d'une
  requête `INSERT`/`DELETE`, confirmer le rejet avant de le corriger.

## 5. Portes de qualité et surfaces à régénérer avant clôture

Mêmes portes qu'en Vague 1 (`docs/superpowers/specs/2026-09-17-vague1-transformers-duckdb-design.md` §4.4),
appliquées à ce chantier :

- `ruff check`/`ruff format --check`/`mypy --strict` (si `app.pipelines` est dans le périmètre strict —
  vérifier `core/pyproject.toml`) ; `lint-imports` ; suite complète `core`.
- Régénérer `openapi.json` + `core-schema.d.ts` (piège CLAUDE.md n°1) — diff non vide attendu (15 nouveaux
  schémas de params).
- `docs/revue/matrice-couverture-fme.jsonl` : les 12 lignes FME de transformation **et** les 9 lignes FME de
  lecture (§6) couvertes passent `planned_duckdb` → `implemented`, `geostudio_equivalent` renseigné, puis
  `python3 core/scripts/fme_coverage_cli.py --write` puis `--check`.
- `docs/revue/inventaire-fonctionnalites.jsonl` : `GET /pipelines/ops` existe déjà, aucune nouvelle route —
  à vérifier plutôt que supposer, comme en Vague 1.
- Aucun fichier `shell/` à modifier — `PipelinePalette.tsx`/`PipelineNodeInspector.tsx` restent
  générique-depuis-catalogue, vérifié en Vague 1 et non changé depuis. Le formulaire de création de secret
  (`SecretsAdminPage` ou équivalent) doit en revanche gagner les nouveaux `kind` — **à vérifier contre le
  code réel du composant avant de supposer un changement front nul**, contrairement au reste de ce chantier
  (piège CLAUDE.md n°12 : ne pas présumer par analogie avec Vague 1 que « aucun fichier shell » s'applique
  encore une fois sans l'avoir revérifié pour ce cas précis).
- `CLAUDE.md` à la clôture : une ligne dans `### Livré` (« Vague 2 des transformers/lecteurs DuckDB — 15
  nouvelles op (11 transform + 4 reader.connector.*), catalogue à 49 op, mécanisme `needs_columns` pour
  l'introspection de schéma à l'exécution »).

## 6. Lecteurs : dialectes SQL + objet/stockage (§3.2 de Vague 1, candidats déjà identifiés comme les plus sûrs)

### 6.1 Dialectes SQL — `reader.connector.bigquery`/`mssql`/`oracle`

Vérifié dans le code : `materialize_postgres_connector`/`materialize_snowflake_connector`
(`core/app/pipelines/connector_runtime.py`, lignes 282-358) ne font que `sa.create_engine(payload.dsn)` puis
`exec_driver_sql(params.query)` — le dialecte SQLAlchemy est résolu par le **schéma du DSN**
(`postgresql://…`, `snowflake://…`) via les entry points du paquet driver installé, jamais importé
explicitement dans ce module. `materialize_bigquery_connector`/`materialize_mssql_connector`/
`materialize_oracle_connector` sont des copies quasi identiques de `materialize_snowflake_connector` —
seuls changent le `payload.kind` attendu et le paquet driver ajouté aux dépendances (`sqlalchemy-bigquery`,
`pymssql` ou `pyodbc`, `python-oracledb` en mode thin — ce dernier déjà noté dans la matrice comme évitant
la dépendance Instant Client propriétaire).

- `ReaderConnectorBigQueryParams`/`ReaderConnectorMssqlParams`/`ReaderConnectorOracleParams` : même forme
  exacte que `ReaderConnectorSnowflakeParams` (`secretName: str`, `query: str`), même validation
  SELECT-only par `validate_select_only` réutilisée telle quelle.
- 3 nouveaux kinds de secret (`app/secrets/schemas.py`, union discriminée « additive par construction »,
  vérifié en tête de fichier) : `BigQueryDsnPayload`/`MssqlDsnPayload`/`OracleDsnPayload`, même forme que
  `PostgresDsnPayload`/`SnowflakeDsnPayload` (`dsn: str` opaque, jamais parsé côté cœur). **Non vérifié dans
  ce document** : la forme exacte du DSN attendu par `sqlalchemy-bigquery` pour l'authentification (un
  chemin de fichier de credentials ne survivrait pas au trajet secret chiffré → chaîne opaque → DSN — à
  vérifier contre le README réel de `sqlalchemy-bigquery` avant d'écrire le premier test, piège CLAUDE.md
  n°3 ; une alternative serait un JSON de service account inline dans le DSN, à confirmer supporté).

### 6.2 Objet/stockage — `reader.connector.blob` (S3, Azure Blob, GCS)

Répond explicitement à la question laissée ouverte par Vague 1 §3.2 (« d'où vient le fichier lu par un
pipeline serveur ») pour ce sous-ensemble précis : **jamais d'upload, jamais une URL arbitraire** — toujours
un objet dans un bucket pour lequel le tenant a configuré un secret de connexion au préalable, exactement le
même modèle de confiance que `reader.connector.postgres`/`snowflake` (jamais de connexion anonyme,
`secretName` toujours requis).

- Un seul op `reader.connector.blob` pour les 3 fournisseurs (S3/Azure Blob/GCS) plutôt que 3 op distinctes —
  cohérent avec la source `filesystem` générique de dlt via `fsspec`, qui résout le fournisseur depuis le
  préfixe de l'URI (`s3://`, `az://`, `gs://`) exactement comme `sa.create_engine` résout le dialecte SQL
  depuis le préfixe du DSN en §7.1 — même idiome, appliqué à un mécanisme différent.
- `ReaderConnectorBlobParams` : `secretName: str`, `path: str` (URI complet avec préfixe de schéma,
  potentiellement un glob), `format: Literal["csv", "json", "parquet"]`.
- Réutilise `_run_dlt_and_attach` tel quel (`core/app/pipelines/connector_runtime.py` ligne 195) — la
  fonction est déjà générique sur n'importe quel `dlt.resource`, aucune modification nécessaire.
- 3 nouveaux kinds de secret (`s3_credentials`/`azure_blob_credentials`/`gcs_credentials`) : contrairement
  aux DSN SQL opaques, les credentials objet/stockage sont typiquement structurés (clé d'accès/clé secrète/
  région pour S3, compte/clé pour Azure Blob, JSON de compte de service pour GCS) — **forme exacte des
  champs non vérifiée dans ce document**, à confirmer contre la doc réelle de `s3fs`/`adlfs`/`gcsfs` (les
  3 implémentations fsspec que dlt utilise sous le capot pour ces 3 préfixes) avant d'écrire le premier test.
- **Excel (.xlsx) volontairement exclu de cette op** : la source `filesystem` de dlt auto-détecte et parse
  CSV/JSON/Parquet nativement, mais pas un classeur Excel binaire (nécessiterait l'extension communautaire
  DuckDB `excel`, déjà notée dans la matrice, ligne Microsoft Excel) — hors périmètre de ce chantier, pas un
  oubli : follow-up possible une fois `reader.connector.blob` en place, pas construit ici.

### 6.3 Fichiers touchés (§6)

- `core/app/pipelines/ops/schemas.py` : 4 nouvelles classes `ReaderConnectorXxxParams`.
- `core/app/pipelines/connector_runtime.py` : 4 nouvelles fonctions `materialize_xxx_connector`.
- `core/app/pipelines/ops/contracts.py` : 4 nouvelles entrées `OPERATIONS`, `kind="reader"`, engine/licence à
  documenter par connecteur (dlt Apache-2.0 + driver SQL propre à chaque dialecte pour §7.1 ; dlt + fsspec/
  s3fs/adlfs/gcsfs pour §7.2 — licences déjà relevées comme permissives dans la matrice, à reconfirmer contre
  le `pyproject.toml` réel une fois les dépendances ajoutées).
- `app/secrets/schemas.py` : 6 nouveaux kinds (§7.1 + §7.2), union discriminée étendue.
- Dépendances `core/pyproject.toml` : `sqlalchemy-bigquery`, `pymssql` (ou `pyodbc`), `python-oracledb`,
  et les extras `filesystem`/`s3`/`az`/`gs` de `dlt` — à vérifier lesquels sont déjà présents (le patron
  Snowflake/Postgres existant a peut-être déjà tiré une partie de ces extras transitivement).

## 8. Migration vecteur des algorithmes QGIS gelés (7 lignes `qgis_frozen` → DuckDB pur)

Classification de départ (vérifiée, pas supposée) : des 50 algorithmes de l'allowlist QGIS
(`core/app/pipelines/ops/qgis_algorithms.json`), **12 seulement sont réellement consommés** par les 19 lignes
`qgis_frozen` de la matrice — les 38 autres sont de la capacité inutilisée, aucune migration requise pour
elles. Sur ces 12 : 6 sont des opérations raster (hors périmètre ici, §9), 2 relèvent d'une triangulation sans
équivalent DuckDB trouvé (hors périmètre ici, §9), et **2 sont déjà atteignables aujourd'hui par composition
d'op existantes** (vérifié empiriquement, aucun nouveau code) :

- **Clipper** (`native:clip`) — `transform.intersection` avec `outputGeometry="intersection"`
  (`TransformIntersectionParams`, `core/app/pipelines/ops/schemas.py` ligne 79) produit déjà exactement
  `ST_Intersection(t.geometry, o.geometry)` (`compiler.py::_compile_intersection`) — testé contre un DuckDB
  réel, confirmé. Même caveat déjà documenté pour `SpatialFilter` dans la matrice : une entrée qui intersecte
  plusieurs features de l'overlay en ressort dupliquée une fois par correspondance, contrairement à
  `native:clip`.
- **Dissolver** (`native:dissolve`) — `transform.aggregate` avec `metrics: {"geometry":
  "ST_Union_Agg(geometry)"}` (`groupBy` optionnel) produit déjà le dissolve standard — testé contre un DuckDB
  réel (3 polygones, 2 adjacents fusionnés en un seul, le 3e resté séparé, résultat exact attendu).

Ces deux lignes passent `qgis_frozen` → `implemented` (`geostudio_equivalent` = la combinaison d'op, cf. la
même limite déjà notée en Vague 1 §3.2 dernier point : le vérificateur mécanique
`fme_coverage_cli.py --check` exige une clé unique de `ops_catalog()`, pas une composition — à traiter comme
une extension de taxonomie ou laissée en note, même decision que pour les ~8 lignes « déjà atteignables par
composition » de Vague 1).

### 8.1 5 nouvelles op `transform.*`

| Op GeoStudio | FME couvert | Mécanisme | Entrée secondaire |
|---|---|---|---|
| `transform.centroid` | CenterPointReplacer | `ST_Centroid(geometry)` | non |
| `transform.simplify` | Generalizer | `ST_Simplify`/`ST_SimplifyPreserveTopology(geometry, tolerance)` | non |
| `transform.convexHull` | HullReplacer | `ST_ConvexHull(geometry)` | non |
| `transform.boundingGeometry` | BoundingBoxReplacer | `ST_Envelope`/`ST_MinimumRotatedRectangle(geometry)` | non |
| `transform.snapToLayer` | Snapper | `ST_Snap(t.geometry, o.geometry, tolerance)` | **oui** (`withCollectionId`) |

Toutes les 5 en `compile` pur, patron identique aux 34 op existantes — aucune n'a besoin de `needs_columns`.
Fonctions vérifiées comme existantes par introspection de `duckdb_functions()` (`ST_Centroid`, `ST_Simplify`,
`ST_SimplifyPreserveTopology`, `ST_ConvexHull`, `ST_Envelope`, `ST_MinimumRotatedRectangle`, `ST_Snap`) —
**signatures exactes et comportement sémantique non vérifiés** (piège CLAUDE.md n°3, comme pour les
identifiants DuckDB spatial de Vague 1 §3) : à confirmer contre `duckdb.org/docs/current/core_extensions/
spatial` ou un DuckDB réel avant d'écrire le premier test du plan, en particulier :

- `transform.simplify` : `preserveTopology: bool = True` sélectionne entre les deux fonctions — reste à
  vérifier si `ST_SimplifyPreserveTopology` accepte les mêmes types de géométrie que `ST_Simplify` (GEOS a
  parfois des restrictions différentes selon la fonction).
- `transform.boundingGeometry` : `mode: Literal["envelope", "orientedRectangle"]` — couvre les 2 modes 2D de
  BoundingBoxReplacer déjà notés dans la matrice (« seuls les modes 2D sont couverts, pas le mode cube 3D »).
  Ne couvre pas MinimumSpanningCircleReplacer (aucune fonction `ST_MinimumBoundingCircle`-like trouvée dans
  `duckdb_functions()` — `ST_MaximumInscribedCircle` est un calcul différent, le plus grand cercle **inscrit**
  dans la géométrie, pas le plus petit cercle qui la **contient** — reste sur QGIS, §9).
- `transform.snapToLayer` : `ST_Snap` prend une géométrie de référence unique — comportement à définir/tester
  si l'entrée secondaire (`withCollectionId`) contient plusieurs features (snap contre la plus proche ? contre
  toutes en cascade ? actuellement indéterminé, à trancher dans le plan plutôt que deviné ici).

### 8.2 Fichiers touchés (§8)

Mêmes 3 fichiers que le reste de ce document (`schemas.py`, `compiler.py`, `contracts.py`) — aucun nouveau
fichier, aucun changement à `runtime.py` (aucune des 5 n'a besoin de `needs_columns`). `engine_license="MIT
(DuckDB)"` pour les 5 — aucune ne dépend de QGIS, ce qui est tout l'intérêt de cette migration.

### 8.3 Tests et portes de qualité (§8)

Même discipline que §4/§5 : un test par `_compile_xxx` contre un DuckDB réel avec géométrie connue
(assertion sur le résultat, pas la forme du SQL) ; `len(OPERATIONS) == 54` (34 + 11 + 4 + 5 — les 2
reclassifications Clipper/Dissolver n'ajoutent aucune entrée, elles réutilisent des op déjà comptées) ;
`docs/revue/matrice-couverture-fme.jsonl` : les 7 lignes
(5 nouvelles op + Clipper + Dissolver) passent `qgis_frozen` → `implemented` ; `CLAUDE.md ### Livré` mentionne
« 7 des 19 lignes `qgis_frozen` migrées vers DuckDB pur (5 nouvelles op + 2 par composition), sidecar QGIS
toujours en place pour les 12 restantes ».

## 9. Ce que ce document ne fait pas

Ne construit aucun nouveau moteur d'exécution (les 4 lecteurs §6 réutilisent `_run_dlt_and_attach` sans le
modifier ; les 5 op §8 sont du `compile` pur). Ne tranche pas les familles « appel externe par ligne »,
« connecteurs de flux » ou le bloc « Integrations » (~20 connecteurs SaaS bespoke — Box, Dropbox, CKAN,
ArcGIS Online, Autodesk, Slack, Trello, RabbitMQ, MongoDB, Google Sheets…) — explicitement écarté par Tanguy
de ce chantier (choix du 2e tour de cadrage), toujours hors périmètre, carte inchangée depuis Vague 1 §3.2 sur
ce point. Ne construit aucun `writer.connector.*` (DatabaseUpdater/DatabaseDeleter) — écrire vers un système
externe est une capacité qui n'existe nulle part aujourd'hui (seuls `writer.collection`/`export`/`dataset`
écrivent, tous vers le cœur GeoStudio lui-même) et mériterait son propre design (garde d'egress en écriture,
sémantique de mode) plutôt qu'un ajout mécanique ici — explicitement écarté par Tanguy du 2e tour de cadrage.

**Ne retire pas le sidecar QGIS** — 12 des 19 lignes `qgis_frozen` continuent d'en dépendre après ce
document (6 op raster : ContourGenerator/RasterResampler/RasterToPolygonCoercer/RasterAspectCalculator/
RasterHillshader/RasterSlopeCalculator ; 2 cas de triangulation sans équivalent DuckDB trouvé :
TINGenerator/SurfaceModeller/DEMGenerator ; AreaOnAreaOverlayer, dont le mode auto-overlay sur une seule
couche ne se réduit pas à une composition simple ; MinimumSpanningCircleReplacer, cercle englobant minimal
sans fonction DuckDB équivalente ; Densifier, aucune fonction `ST_Densify`/`ST_Segmentize` trouvée dans
`duckdb_functions()`). Le retrait mécanique du sidecar (docker-compose, `CORE_ETL_ENABLED`, migration des
pipelines prod existants qui utilisent `transform.qgis` aujourd'hui, `LICENSE-QGIS.md`), le chemin GDAL direct
pour les 6 op raster (candidat identifié : `gdaldem`/`gdal_contour`/`gdalwarp`/`gdal_polygonize.py`, MIT/X,
précédent déjà dans la stack via `titiler`/rasterio — non conçu ici), et les 2 cas de triangulation (piste non
vérifiée : Shapely/GEOS `shapely.ops.triangulate`, BSD, en process dans le worker) restent des chantiers
séparés, non entamés par ce document.

Ne restreint pas structurellement l'usage de `transform.sort` (décision assumée en §3.3, à revisiter
explicitement si un incident de données mal ordonnées survient en production). Ne construit pas le matching
automatique par type de SchemaMapper ni le mode « toutes colonnes » de AttributeValidator — réductions de
périmètre documentées en §2.1, pas des oublis.

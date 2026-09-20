# Vague 2 des transformers `planned_duckdb` — 11 nouvelles op, familles « schéma/forme » + « ordre/cardinalité »

**Date** : 2026-09-20
**Demande** : « lance une spec pour réaliser tous les transformers duckdb restant ».
**Référence** : `docs/superpowers/specs/2026-09-17-vague1-transformers-duckdb-design.md` (Vague 1, 15 op livrées,
catalogue à 34 op) — son §3.2 cartographiait le reste des 90 lignes `planned_duckdb` en familles et concluait
que « construire les 90 transformers » est un programme, pas un chantier. Ce document exécute la **prochaine**
tranche, choisie par Tanguy parmi les familles cartographiées : la famille « schéma dynamique » (~8 lignes) et
la famille « cardinalité/ordre changé » (~4 lignes) — 12 transformers FME au total.

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
  échelle (voir §5, décision assumée sur ce point précis).

**Conséquence** : sur les 12 transformers FME des deux familles, **seuls 3** (ChangeDetector, FeatureMerger,
SchemaMapper) ont un besoin réel d'introspection dynamique qu'aucune primitive SQL statique ne couvre —
comparer les colonnes communes de **deux** relations dont l'ensemble n'est connu qu'à l'exécution.
`struct_pack(COLUMNS(...))` a été testé pour tenter de couvrir aussi FeatureMerger sans introspection : il
produit une liste de structs à un seul champ **par colonne matchée** (`COLUMNS()` duplique l'expression
englobante par colonne, ce n'est pas une agrégation en un seul struct) — pas la sémantique voulue (un struct
unique combinant toutes les colonnes restantes). D'où le besoin réel, mais limité à ces 3 op, d'un mécanisme
d'introspection.

## 1. Ce que ce chantier construit, en une phrase

**11 nouvelles entrées `OperationContract`** couvrant les 12 transformers FME des familles « schéma
dynamique » et « cardinalité/ordre changé » : 8 en `compile` pur (patron déjà prouvé par les 34 op
existantes, y compris 2 qui changent la cardinalité), et 3 utilisant une extension minimale et chirurgicale du
contrat (`needs_columns`) pour recevoir la liste des colonnes réelles de leur(s) entrée(s) — jamais une
connexion DuckDB dans `compiler.py`, qui reste un module pur.

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
- **Test de non-régression sur le compte d'op** : `len(OPERATIONS) == 45` (34 + 11).
- **`test_pipeline_routes.py`** : `GET /pipelines/ops` contient les 11 nouvelles clés avec leur
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

## 5. Portes de qualité et surfaces à régénérer avant clôture

Mêmes portes qu'en Vague 1 (`docs/superpowers/specs/2026-09-17-vague1-transformers-duckdb-design.md` §4.4),
appliquées à ce chantier :

- `ruff check`/`ruff format --check`/`mypy --strict` (si `app.pipelines` est dans le périmètre strict —
  vérifier `core/pyproject.toml`) ; `lint-imports` ; suite complète `core`.
- Régénérer `openapi.json` + `core-schema.d.ts` (piège CLAUDE.md n°1) — diff non vide attendu (11 nouveaux
  schémas de params).
- `docs/revue/matrice-couverture-fme.jsonl` : les 12 lignes FME couvertes passent `planned_duckdb` →
  `implemented`, `geostudio_equivalent` renseigné, puis
  `python3 core/scripts/fme_coverage_cli.py --write` puis `--check`.
- `docs/revue/inventaire-fonctionnalites.jsonl` : `GET /pipelines/ops` existe déjà, aucune nouvelle route —
  à vérifier plutôt que supposer, comme en Vague 1.
- Aucun fichier `shell/` à modifier — `PipelinePalette.tsx`/`PipelineNodeInspector.tsx` restent
  générique-depuis-catalogue, vérifié en Vague 1 et non changé depuis.
- `CLAUDE.md` à la clôture : une ligne dans `### Livré` (« Vague 2 des transformers DuckDB — 11 nouvelles op,
  catalogue à 45 op, mécanisme `needs_columns` pour l'introspection de schéma à l'exécution »).

## 6. Ce que ce document ne fait pas

Ne construit aucun nouveau moteur, aucun nouveau connecteur. Ne tranche pas les familles « appel externe par
ligne », « nouveaux lecteurs », « connecteurs de flux » ou « Integrations » — toujours hors périmètre, carte
inchangée depuis Vague 1 §3.2. Ne restreint pas structurellement l'usage de `transform.sort` (décision
assumée en §3.3, à revisiter explicitement si un incident de données mal ordonnées survient en production).
Ne construit pas le matching automatique par type de SchemaMapper ni le mode « toutes colonnes » de
AttributeValidator — réductions de périmètre documentées en §2.1, pas des oublis.

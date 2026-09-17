# Vague 1 des transformers `planned_duckdb` — 15 nouvelles op DuckDB pures

**Date** : 2026-09-17
**Demande** : « go spec pour la construction des 90 transformers duckdb planifiés ».
**Référence** : matrice de couverture FME→GeoStudio (`docs/revue/matrice-couverture-fme.jsonl`,
289 lignes) — 90 lignes `coverage_status: planned_duckdb` ; `OperationContract`
(`docs/superpowers/specs/2026-09-16-operation-contract-design.md`), livré la veille, qui a
explicitement posé et refusé de construire ces 90 lignes (« Aucune nouvelle op ni transformer des
90 lignes `planned_duckdb` de la matrice — ce chantier prépare le terrain, ne le construit pas.
Chantier séparé, ultérieur. »). Ce document est ce chantier séparé.

## 1. Constat de départ (vérifié dans le code, pas supposé)

Les 90 lignes `planned_duckdb` partagent `engine: "duckdb"` (vérifié : `Counter` sur le JSONL, 90/90),
mais ce champ ne veut dire que « l'exécution finale se fait dans le runtime DuckDB déjà existant » —
il ne dit rien de l'effort réel. En les classant par la capacité qu'elles exigent réellement du moteur
(pas par la catégorie FME de la matrice, qui mélange les deux), elles se répartissent en familles très
inégales :

- **~19** sont des expressions scalaires ou des constructeurs géométriques exprimables en une seule
  requête SQL DuckDB sur la vue en entrée, sans schéma dynamique ni effet de bord — exactement le
  patron des 11 op `transform.*` déjà livrées (`compile_transform_sql`, une fonction pure
  `dict → str`, jamais de connexion DuckDB touchée, vérifié dans `core/app/pipelines/compiler.py`).
- **~8** (`AttributeManager`, `DatabaseJoiner`, `TestFilter`, `GeometryFilter`,
  `AttributeRangeFilter`, `Sampler`, `AggregateFilter`, `FeatureTypeFilter`) sont, de l'aveu même de
  leur `notes` dans la matrice, **déjà atteignables aujourd'hui** par composition de 2 op existantes
  (`transform.select`→`transform.filter`, `reader.connector.postgres`→`transform.join`, N nœuds
  `transform.filter` en éventail…) — la matrice les a classées `planned_duckdb` pour signaler un
  manque de **confort no-code** (fan-out multi-port natif sur le canevas), pas un manque de moteur.
- **~8** (`BulkAttributeRemover`, `BulkAttributeRenamer`, `ChangeDetector`, `SchemaMapper`,
  `SchemaScanner`, `AttributeValidator`, `AttributeExposer`, `FeatureMerger`) exigent d'introspecter
  le schéma **réel** de la vue en entrée **au moment de l'exécution** (colonnes inconnues à
  l'enregistrement de la config) — `compile_transform_sql` ne reçoit aujourd'hui aucune connexion
  DuckDB (vérifié : signature `_compile_*(params, *, input_view, join_view, input_srid) -> str`,
  jamais de `conn`), donc structurellement incapable de le faire sans un nouveau mécanisme.
- **~4** (`Sorter`, `SpatialSorter`, `ListExploder`, `Deaggregator`) changent respectivement l'ordre
  ou le nombre de lignes en sortie — architecturalement compatibles avec une simple `compile`
  (une requête `ORDER BY`/`UNNEST` reste une requête), mais reposent sur une hypothèse jamais vérifiée
  dans ce dépôt : `runtime.py` matérialise chaque nœud transform en `CREATE TEMP VIEW` (vérifié
  ligne 630, par opposition aux readers qui font `CREATE TEMP TABLE`, lignes 196/486) — rien ne
  garantit qu'un `ORDER BY` posé dans une vue survit à travers la chaîne de vues jusqu'au writer final
  sans un test qui le prouve.
- **~5** (`HTTPCaller`, `PythonCaller`, `SQLExecutor`, `MCPCaller`, `Geocoder`) exigent un appel
  externe **par ligne** — un modèle d'exécution qui n'existe nulle part dans `core/app/pipelines/`
  aujourd'hui (les 3 connecteurs `reader.connector.*` existants ne font qu'une lecture unique en tête
  de DAG, jamais un appel par ligne au milieu du graphe). `PythonCaller` va plus loin : exécution de
  code utilisateur arbitraire, alors qu'aucune des 19 op actuelles n'exécute autre chose qu'une
  expression SQL bornée (`app/pipelines/expr_validation.py`) — rupture d'invariant produit, pas
  seulement un nouveau connecteur.
- **~9** (`Readers/Writers` : BigQuery, MSSQL, Oracle, MongoDB, Excel, CSV, JSON, Parquet, Google
  Sheets) exigent une nouvelle famille de lecteurs — 3 d'entre elles (BigQuery/MSSQL/Oracle) sont le
  même patron que `reader.connector.postgres`/`snowflake` déjà livré (dialecte SQLAlchemy résolu par
  entry point, via dlt) ; les autres (fichiers arbitraires, Mongo, Sheets) demandent chacune sa propre
  source dlt et posent une question non tranchée : d'où vient le fichier lu par un pipeline serveur
  (upload ? clé S3 ? URL ?) — absent des lecteurs actuels, qui ne lisent que des collections ou des
  connecteurs réseau.
- **~4** (`RabbitMQConnector`, `AzureServiceBusConnector`, `AzureQueueStorageConnector`,
  `KinesisReceiver`/`Sender`) sont des connecteurs de flux — bloqués par la question produit déjà
  ouverte **Q10 temps réel** (`CLAUDE.md`, `REV-108`), pas une question moteur.
- **~27 + reste** (`Integrations`, plus `SQLCreator`/`InlineQuerier`/`DatabaseQuerier`/
  `DatabaseUpdater`/`DatabaseDeleter`) sont des connecteurs SaaS/Cloud/DB bespoke, chacun avec son
  propre SDK, son propre modèle d'auth et sa propre licence à vérifier — un chantier par connecteur ou
  par petite famille, pas un bloc homogène.

**Conclusion du constat** : « construire les 90 transformers » n'est pas un chantier, c'est un
programme de plusieurs chantiers de nature différente. Ce document en définit la carte complète (§3)
et **exécute seulement la première tranche sans risque architectural** (§4) — même discipline que
`OperationContract` la veille, appliquée cette fois à une construction réelle plutôt qu'à un refus.

## 2. Ce que ce chantier construit, en une phrase

**15 nouvelles entrées `OperationContract`** (`engine="duckdb"`, `execution_model="in_process"`,
`compile` pur, exactement le patron des 11 `transform.*` existantes), couvrant **19 des 90 lignes**
de la matrice (`Coordinate System` presque en entier + les 4 constructeurs/transformateurs
géométriques simples de `Geometry`) — zéro nouvelle capacité de runtime, zéro fichier `shell/` touché,
zéro nouveau champ sur `OperationContract`.

## 3. Périmètre

### 3.1 Dans ce chantier — Vague 1 (19 lignes FME → 15 op GeoStudio)

Consolidation assumée : plusieurs transformers FME qui ne diffèrent que par le moteur géodésique ou
la direction d'une même opération deviennent **une seule** op GeoStudio paramétrée — éviter de
construire 19 op quasi identiques pour un gain no-code nul.

| Op GeoStudio (proposée) | Transformer(s) FME couverts | Besoin fonctionnel |
|---|---|---|
| `transform.swapCoordinates` | CoordinateSwapper | Permuter X/Y de la géométrie |
| `transform.reprojectAttribute` | AttributeReprojector, GtransAttributeReprojector, PROJAttributeReprojector | Reprojeter une paire de coordonnées portée par des attributs (pas la géométrie de la feature) |
| `transform.setSrid` | CoordinateSystemSetter, CoordinateSystemRemover | Assigner ou retirer le SRID sans reprojeter (métadonnée seule) |
| `transform.extractSrid` | CoordinateSystemExtractor | SRID de la géométrie → colonne attribut |
| `transform.formatCoordinates` | DecimalDegreesCalculator, DMSCalculator | Formater une coordonnée en degrés décimaux ou DMS |
| `transform.extractElevation` | ElevationExtractor | Composante Z → colonne attribut |
| `transform.extractDimension` | DimensionExtractor | Dimension de la géométrie (2D/3D) → colonne attribut |
| `transform.countVertices` | VertexCounter | Nombre de sommets → colonne attribut |
| `transform.extractCoordinates` | CoordinateExtractor | X/Y (/Z) → colonnes attributs séparées |
| `transform.concatCoordinates` | CoordinateConcatenator | Colonnes X/Y (/Z) → géométrie point |
| `transform.roundCoordinates` | CoordinateRounder | Réduire la précision des coordonnées |
| `transform.translateGeometry` | Offsetter | Translation (dx, dy[, dz]) |
| `transform.scaleGeometry` | Scaler | Mise à l'échelle (xs, ys[, zs]) |
| `transform.rotateGeometry` | Rotator | Rotation autour de l'axe Z |
| `transform.createGeometry` | Creator | Génération d'une géométrie littérale (WKT/coordonnées) |

Ces 15 op sont choisies pour une seule raison, vérifiable : **aucune ne sort du patron déjà prouvé**
par les 11 op `transform.*` existantes — schéma de params statique connu à l'enregistrement de la
config, une seule requête `SELECT … FROM {input_view}` par `compile`, jamais de connexion DuckDB,
jamais d'appel externe, jamais de changement du nombre de lignes.

**Identifiants de fonctions DuckDB spatial (`ST_Translate`, `ST_Scale`, `ST_Rotate`, `ST_FlipCoordinates`
ou équivalent, `ST_SetSRID`, `ST_Z`, `ST_NPoints`, etc.) NON vérifiés dans ce document contre la
documentation réelle de l'extension `spatial`** — piège CLAUDE.md n°3 (le texte d'un design se trompe
régulièrement sur les identifiants d'une interface tierce). Le plan qui suivra vérifie chaque
signature contre `duckdb.org/docs/current/core_extensions/spatial` (ou un `duckdb -c "SELECT * FROM
duckdb_functions() WHERE …"` réel) avant d'écrire le premier test, pas contre ce document ni contre la
mémoire du modèle.

### 3.2 Hors périmètre, explicitement (Vagues futures — carte, pas engagement)

Chaque famille ci-dessous a sa propre question architecturale non résolue ; aucune n'est tranchée par
ce document — un futur chantier reprendra le brainstorming pour chacune séparément, comme
`OperationContract` l'a fait pour celui-ci.

- **Ops déjà atteignables par composition** (`AttributeManager`, `DatabaseJoiner`, `TestFilter`,
  `GeometryFilter`, `AttributeRangeFilter`, `Sampler`, `AggregateFilter`, `FeatureTypeFilter`) : ne
  construit **aucune** nouvelle op ici. Le vrai manque est un fan-out multi-port natif sur
  `PipelineCanvas` (React Flow) — une capacité de canevas, pas une op de moteur — hors périmètre
  cœur de ce document. `PlanarityFilter`/`NeighborFinder`/`SpatialRelator` restent également hors
  périmètre : le premier n'a aucune fonction DuckDB spatial équivalente identifiée à ce jour ; les
  deux autres (jointure spatiale par plus-proche-voisin/enrichissement) prolongent naturellement la
  famille `transform.intersection`/`countWithin` mais demandent une vraie requête de jointure
  spatiale à concevoir, pas un simple `compile` d'une ligne.
- **Ops à schéma dynamique** (`BulkAttributeRemover`, `BulkAttributeRenamer`, `ChangeDetector`,
  `SchemaMapper`, `SchemaScanner`, `AttributeValidator`, `AttributeExposer`, `FeatureMerger`) :
  exigent un mécanisme que `compile_transform_sql` n'a pas — introspecter `input_view` (`DESCRIBE`/
  `PRAGMA table_info`) avant de générer du SQL. Deux voies possibles à trancher dans ce futur
  chantier : étendre la signature de `compile` pour recevoir une connexion (impacte les 15 op de la
  Vague 1 aussi, si le contrat doit rester uniforme), ou traiter ces op comme `transform.qgis`
  (`compile=None`, exécution inline dans `runtime.py`). Ne pas préjuger laquelle ici.
- **Ops à cardinalité/ordre changé** (`Sorter`, `SpatialSorter`, `ListExploder`, `Deaggregator`) :
  bloquées par une hypothèse non vérifiée sur la persistance de l'ordre à travers une chaîne de
  `CREATE TEMP VIEW` (§1) — un futur chantier doit d'abord écrire un test qui la falsifie
  (pipeline à 3 nœuds, tri au milieu, assertion sur l'ordre des lignes en sortie du writer) avant de
  promettre `Sorter` au catalogue.
- **Ops à appel externe par ligne** (`HTTPCaller`, `SQLExecutor`, `MCPCaller`, `Geocoder`) : nouveau
  modèle d'exécution (traitement ligne à ligne, débit/latence, ré-utilisation de la garde d'egress
  SSRF déjà existante — `app/pipelines/egress.py` — mais appliquée par ligne, pas une fois en tête de
  DAG). `PythonCaller` va plus loin qu'un nouveau connecteur : exécution de code utilisateur
  arbitraire dans le moteur de pipeline, une rupture du seul invariant produit qui tient aujourd'hui
  (« rien n'exécute jamais que du SQL borné ou du CEL »). **Recommandation, pas décision** : traiter
  `PythonCaller` comme une question produit à trancher explicitement avant tout chantier qui le
  toucherait — à ajouter aux questions ouvertes de `CLAUDE.md` aux côtés de Q10/Q11 plutôt qu'à
  arbitrer silencieusement dans un futur design technique.
- **Nouveaux lecteurs SQL par dialecte** (BigQuery, MSSQL, Oracle) : risque le plus bas de tout le
  reste de la matrice — même patron exact que `reader.connector.postgres`/`snowflake`
  (`ReaderConnectorPostgresParams`/`SnowflakeParams`, dialecte SQLAlchemy, `SecretResolver`
  fraîchement extrait en Protocol la veille par le chantier `desktop-etl-secret-resolver-seam`,
  `docs/superpowers/plans/2026-09-17-desktop-etl-secret-resolver-seam.md`). Bon candidat pour la
  Vague 2 immédiate après celle-ci, mais hors périmètre ici pour garder ce chantier mono-thème
  (op DuckDB pures, aucun nouveau secret/dlt source).
- **Lecteurs de fichiers génériques** (Excel/CSV/JSON/Parquet non-géo, Google Sheets, MongoDB) :
  question non tranchée — d'où vient le fichier lu par un pipeline serveur (aucun des lecteurs actuels
  ne lit un fichier arbitraire, seulement des collections ou des connecteurs réseau).
- **Connecteurs de flux** (`RabbitMQConnector`, `AzureServiceBusConnector`,
  `AzureQueueStorageConnector`, `KinesisReceiver`/`Sender`) : bloqués par Q10 (temps réel, `REV-108`),
  déjà une question ouverte documentée — rien de neuf à trancher ici.
- **Bloc `Integrations` (27 lignes) + `SQLCreator`/`InlineQuerier`/`DatabaseQuerier`/
  `DatabaseUpdater`/`DatabaseDeleter`** : connecteurs SaaS/Cloud/DB bespoke, chacun son SDK, son
  modèle d'auth, sa licence à vérifier contre la source réelle (piège CLAUDE.md n°3) — programme de
  petits chantiers dédiés, pas un bloc à trancher ici. `S3Connector`/`AzureBlobStorageConnector`/
  `GoogleCloudStorageConnector` sont déjà notés comme le patron le plus simple (source `filesystem`
  générique de dlt, licence déjà vérifiée dans la matrice) — bon candidat de tête pour ce programme,
  mais non construit ici.
- **Aucun changement d'API publique.** `GET /pipelines/ops` gagne 15 nouvelles clés dans sa réponse —
  c'est un changement de **contenu**, pas de **forme** (même schéma de réponse). Diff
  `openapi.json`/`core-schema.d.ts` attendu **non vide** cette fois (contrairement à
  `OperationContract`) : 15 nouveaux schémas de params apparaissent dans les modèles générés — à
  vérifier, pas à supposer.
- **Aucune correction de statut sur les ~8 lignes « déjà atteignables par composition »** de la
  matrice. Le vérificateur mécanique (`core/scripts/fme_coverage_cli.py`) exige, pour
  `coverage_status: implemented` + `engine: duckdb`, que `geostudio_equivalent` soit **une clé réelle
  unique** de `ops_catalog()` — une composition de 2 op n'a pas de clé unique à donner, et la
  taxonomie `coverage_status` (`docs/superpowers/specs/2026-09-15-matrice-couverture-fme-design.md`
  §« Taxonomie ») n'a aujourd'hui aucune valeur pour « déjà couvert par composition d'op existantes ».
  Ajouter cette valeur d'enum est un changement de la matrice elle-même, pas de ce chantier — laissé
  en l'état, dette documentaire déjà visible dans les `notes` de ces 8 lignes.

## 4. Design — les 15 nouveaux contrats

### 4.1 Fichiers touchés (mêmes 2 fichiers que les 11 op existantes, aucun nouveau fichier)

- `core/app/pipelines/ops/schemas.py` : 15 nouvelles classes `TransformXxxParams(BaseModel)` — champs
  typés (pas de champ `expr` texte libre : c'est tout l'intérêt no-code face à `transform.derive`,
  cf. §1 sur le bucket "Coordinate System"), docstring française courte sur chaque classe (devient la
  description affichée en tooltip du nœud, vérifié : `PipelinePalette.tsx` lit
  `catalog[op].paramsSchema.description`, JSON Schema généré depuis le docstring Pydantic).
- `core/app/pipelines/compiler.py` : 15 nouvelles fonctions privées `_compile_xxx(params, *,
  input_view, join_view=None, input_srid=None) -> str` — même signature exacte que les 11 existantes,
  toutes `join_view`/`input_srid` ignorés puisqu'aucune de ces 15 op n'est binaire ni ne change le
  SRID (sauf vérification contraire au moment d'écrire `transform.reprojectAttribute`, qui reprojette
  un attribut, pas la géométrie — `output_srid` de la feature reste un passthrough, à confirmer
  explicitement dans le test plutôt que supposé).
- `core/app/pipelines/ops/contracts.py` : 15 nouvelles entrées dans `OPERATIONS`, `engine="duckdb"`,
  `engine_license="MIT (DuckDB)"` (même licence que les 11 existantes, aucune extension tierce
  nouvelle requise — à confirmer par op : si une fonction utilise l'extension communautaire `spatial`
  déjà chargée, pas de nouvelle dépendance de licence ; si une op venait à exiger une extension
  DuckDB non encore chargée par le runtime, `engine_license` devrait le refléter — vérifier au moment
  d'écrire chaque `compile`, pas ici).

**Aucun changement à `OperationContract` lui-même** (le dataclass, §3 du design `OperationContract`) :
ces 15 entrées n'utilisent que des champs déjà existants (`op`, `kind="transform"`, `params_schema`,
`engine`, `engine_license`, `compile`), `execution_model` reste au défaut `"in_process"`,
`is_copyleft` reste au défaut `False`, `exchange` reste `None`.

### 4.2 Convention de nommage et de forme des params

- Nom d'op : `transform.<verbeCamelCase>` — cohérent avec les 11 existantes (`transform.buffer`,
  `transform.reproject`…), jamais le nom FME littéral (`Offsetter` devient `translateGeometry`,
  descriptif de ce qu'il fait plutôt que de son origine FME — cohérent avec le fait que
  `geostudio_equivalent` dans la matrice est déjà un nom **proposé**, pas un nom FME calqué).
- Toute op qui produit une colonne dérivée (`extractSrid`, `extractElevation`, `extractDimension`,
  `countVertices`, `formatCoordinates`) prend un paramètre `column: str` explicite pour le nom de la
  colonne créée — même patron que `TransformDeriveParams.column` déjà existant, pas de nom de colonne
  implicite/deviné.
- Toute op qui modifie la géométrie en place (`swapCoordinates`, `setSrid`, `roundCoordinates`,
  `translateGeometry`, `scaleGeometry`, `rotateGeometry`) n'a pas de paramètre `column` — elle opère
  sur la colonne `geometry` conventionnelle, comme `transform.buffer`/`transform.reproject` déjà
  existantes (vérifier ce nom conventionnel dans `TransformBufferParams`/le SQL généré avant
  d'écrire le premier test — pas supposé ici).
- `transform.reprojectAttribute` et `transform.concatCoordinates`/`extractCoordinates` prennent des
  noms de colonnes source/cible en paramètres explicites (`xColumn`/`yColumn`/`targetCrs`…) — jamais
  de détection automatique d'un nom de colonne candidat.

### 4.3 Tests (falsifiés avant clôture, piège CLAUDE.md n°10)

- **Un test par `_compile_xxx`** dans `test_pipeline_compiler.py` (boîte noire déjà existante) : SQL
  généré exécuté contre une vraie connexion DuckDB avec l'extension `spatial` chargée et une géométrie
  de test connue, assertion sur le résultat numérique/géométrique attendu — pas seulement sur la
  forme de la chaîne SQL (une assertion de forme ne prouve pas que `ST_Xxx` existe avec cette
  signature, piège CLAUDE.md n°3).
- **Un test de non-régression sur le compte d'op** : `len(OPERATIONS) == 34` (19 actuelles + 15) —
  garde-fou pour qu'aucune des 15 ne soit oubliée silencieusement, même patron que le test à 19 clés
  posé par `OperationContract`.
- **`test_pipeline_routes.py`** : la réponse de `GET /pipelines/ops` contient bien les 15 nouvelles
  clés avec leur `kind`/`paramsSchema` — filet API existant, étendu.
- **Falsification explicite** : pour au moins une op par sous-famille (attribut vs géométrie vs
  métadonnée SRID), injecter délibérément un bug dans `_compile_xxx` (ex. mauvais nom de colonne),
  confirmer que le test échoue, puis corriger — pas se contenter de « le test passe ».

### 4.4 Portes de qualité et surfaces à régénérer avant clôture

- `ruff check`/`ruff format --check`/`mypy --strict` (si `app.pipelines` est dans le périmètre strict
  — vérifier `core/pyproject.toml`, pas supposer) ; `lint-imports` ; suite complète `core`.
- **Régénérer `openapi.json` + `core-schema.d.ts`** (piège CLAUDE.md n°1) — diff **non vide** attendu
  cette fois (15 nouveaux schémas de params) : c'est le signal que la régénération a bien tourné, pas
  une anomalie à corriger.
- **`docs/revue/inventaire-fonctionnalites.jsonl`** : aucune nouvelle route REST/MCP/shell n'apparaît
  (`GET /pipelines/ops` existe déjà) — la porte CI (`core/tests/test_feature_inventory.py`) ne devrait
  rien exiger de neuf, à vérifier plutôt que supposer. Mettre à jour la `description` de la ligne
  existante `automatisation-construire-un-pipeline-etl-no-code-graphe-reader-transform-writer`
  (mention du nombre d'op au catalogue) reste optionnel, laissé à l'appréciation de la tâche de
  clôture.
- **`docs/revue/matrice-couverture-fme.jsonl`** : pour chacune des 19 lignes FME couvertes,
  `coverage_status: planned_duckdb` → `implemented`, `geostudio_equivalent` renseigné avec le nom
  d'op réel — puis `python3 core/scripts/fme_coverage_cli.py --write` (régénère
  `docs/revue/matrice-couverture-fme.md`) et `--check` doit passer (vérifie mécaniquement que chaque
  `geostudio_equivalent` déclaré `implemented` existe bien dans `ops_catalog()`).
- **Aucun fichier `shell/`** à modifier : `PipelinePalette.tsx` liste les op dynamiquement depuis
  `GET /pipelines/ops` (vérifié — boucle sur `Object.entries(catalog)`, libellé = nom d'op littéral,
  aucune table de traduction par op) ; `PipelineNodeInspector.tsx` rend ses champs génériquement
  depuis `paramsSchema.properties` (vérifié en amont de ce document, mécanisme déjà utilisé par les
  19 op existantes) — les 15 nouvelles op apparaissent dans le builder sans aucun changement front.
- **Mise à jour de `CLAUDE.md`** à la clôture : une ligne dans `### Livré` (« 15 nouvelles op
  transform.* — Vague 1 des 90 planned_duckdb, catalogue à 34 op »).

## 5. Ce que ce document ne fait pas

Ne construit aucun nouveau moteur, aucun nouveau connecteur, aucune nouvelle sémantique d'exécution
(ordre, cardinalité, appel externe, code utilisateur, schéma dynamique). Ne tranche pas s'il faut
un jour construire `PythonCaller`. Ne corrige pas la taxonomie `coverage_status` de la matrice. Pose
une carte vérifiée du reste des 90 lignes (§3.2) pour que le prochain chantier — quelle que soit la
famille qu'il choisit d'attaquer — reparte d'un état des lieux à jour plutôt que de redécouvrir les
mêmes questions.

# IPC d'échange DuckDB↔futurs moteurs natifs — Arrow zéro-copie + GeoParquet natif (core-only)

**Date** : 2026-09-16
**Demande** : brainstorm sur « un IPC performant » pour remplacer GPKG (item 4 de la feuille de route
ETL, `CLAUDE.md`), immédiatement recadré par l'utilisateur en cours de session : « on garde tout en
Parquet/Arrow natif DuckDB pour un moteur qui n'a pas cette contrainte (in-process, ou son propre
binding). Oublie QGIS, pense aux autres. » — QGIS (`transform.qgis`) est explicitement **hors
périmètre** de ce chantier : fallback GPL amené à se réduire (cf. `OperationContract`,
2026-09-16-operation-contract-design.md), pas la surface à optimiser.
**Référence** : suite directe d'OperationContract (`docs/superpowers/specs/
2026-09-16-operation-contract-design.md`) — item 3 (moteur natif) et item 4 (IPC) de la feuille de
route ETL notée dans `CLAUDE.md` § Suivis non bloquants. Matrice de couverture FME→GeoStudio
(`docs/revue/matrice-couverture-fme.jsonl`) : 55 `planned_gdal` + 16 `planned_pdal` + 3 `planned_otb` +
2 `planned_rust` = 76 transformers qui attendent un futur moteur natif.

## 1. Constat de départ (vérifié empiriquement, pas supposé)

**Le sidecar QGIS ne peut pas bénéficier d'un IPC plus rapide, et ce n'est pas le sujet de ce
chantier.** Vérifié contre l'image réelle `qgis/qgis:release-3_34` (celle utilisée en production,
`deploy/qgis-worker/Dockerfile`) :
- `ogrinfo --formats` : GDAL embarqué = **3.4.1**, drivers GPKG et FlatGeobuf présents, **aucun driver
  Parquet ni Arrow**. `qgis_process` ne pourra donc jamais lire un GeoParquet en `INPUT`, quoi qu'on
  fasse côté DuckDB — un changement de format pour QGIS supposerait de faire évoluer l'image de base
  QGIS elle-même, hors périmètre.
- Benchmark réel (DuckDB 1.5.5, extension spatiale, 200 000 features avec géométrie point) :

  | Format | write | read | taille |
  |---|---|---|---|
  | GPKG (`FORMAT GDAL DRIVER GPKG`) | 0,340 s | 0,055 s | 28,4 Mo |
  | FlatGeobuf (`FORMAT GDAL DRIVER FlatGeobuf`) | 0,408 s | 0,334 s | 32,5 Mo |
  | Parquet natif DuckDB (`FORMAT PARQUET`, sans pont GDAL) | 0,043 s | 0,031 s | 2,9 Mo |

  FlatGeobuf est **plus lent et plus gros** que GPKG dans ce test — l'intuition « binaire streamé donc
  plus rapide » ne tient pas ici. Le seul gain mesuré (8-10x en vitesse, 10x en taille) vient du writer
  Parquet **natif** de DuckDB, qui ne passe jamais par le pont GDAL/OGR — chemin qui reste fermé à QGIS
  (pas de driver Parquet dans son GDAL). Conclusion actée avec l'utilisateur : ne pas toucher au format
  d'échange de `transform.qgis` (GPKG reste le meilleur choix mesuré pour ce pont précis), concentrer
  l'effort sur l'échange pour les *futurs* moteurs.

**DuckDB expose déjà un chemin zéro-copie complet, vérifié empiriquement** :
- `DuckDBPyRelation.arrow()` retourne un `pyarrow.RecordBatchReader` — un flux, pas une matérialisation
  complète en mémoire.
- La colonne géométrie y est encodée `geoarrow.wkb` (extension Arrow standard, metadata
  `ARROW:extension:name`), pas un blob WKB nu sans étiquette.
- Le CRS **complet en PROJJSON** voyage dans les métadonnées de l'extension dès que la colonne porte un
  `ST_SetCRS` — vérifié avec EPSG:2154 (Lambert-93), le CRS survit intact, y compris son `bbox`
  d'usage et sa définition d'ellipsoïde. Sans `ST_SetCRS`, ce même mécanisme resterait vide (`{}`) — la
  fonction d'échange ci-dessous doit donc explicitement forcer le CRS sur la relation source avant
  export, jamais compter sur un défaut.

**`app.pipelines` est déjà autorisé à importer `app.cdc`** (contrat de couches `pyproject.toml`,
`app.pipelines` listé au-dessus d'`app.cdc`) — `app.cdc.parquet_writer.write_geoparquet` (GeoParquet 1.0,
écrit et testé depuis SP-11a) est réutilisable tel quel depuis `app.pipelines`, sans exemption
`lint-imports` nouvelle.

**Aucun moteur natif n'a de binding installé dans cet environnement** (`import osgeo`/`import pdal`
échouent tous deux) — cohérent avec le périmètre d'OperationContract (« aucun nouveau moteur câblé »).
Ce chantier ne peut donc pas vérifier un round-trip contre un vrai GDAL/PDAL/OTB/Rust ; il pose le
contrat et les deux fonctions d'échange génériques côté DuckDB, que le futur chantier « premier moteur
natif » consommera et validera contre un binding réel.

## 2. Périmètre

**Dans ce chantier :**
- Un nouveau module `app/pipelines/exchange.py`, deux fonctions publiques :
  - `to_arrow_stream(relation: duckdb.DuckDBPyRelation, *, srid: int) -> pyarrow.RecordBatchReader` —
    force `ST_SetCRS` sur la colonne géométrie identifiée par introspection de type (même garantie que
    `_materialize_reader`/`_materialize_qgis_output` : détection par type DuckDB `GEOMETRY`, jamais par
    nom de colonne), puis `.arrow()`. Lève `PipelineRuntimeError` si la relation ne porte aucune colonne
    géométrie (même contrat d'erreur que `_materialize_qgis_output`).
  - `from_arrow_stream(conn: duckdb.DuckDBPyConnection, reader: pyarrow.RecordBatchReader, *,
    view_name: str) -> None` — enregistre le flux comme TEMP TABLE DuckDB (`conn.register` +
    `CREATE TEMP TABLE ... AS SELECT * FROM`), symétrique de `_materialize_qgis_output` mais sans jamais
    passer par un fichier.
  - Round-trip **jamais** invoqué depuis `runtime.py` par ce chantier (aucun consommateur réel, cf. hors
    périmètre) — validé uniquement par ses propres tests unitaires.
- Un helper de repli fichier, `to_geoparquet_file(relation, *, srid: int, path: str) -> None` dans le
  même module, **qui délègue à `app.cdc.parquet_writer.write_geoparquet`** plutôt que d'en écrire un
  second (adaptation de signature seulement : `write_geoparquet` prend aujourd'hui une liste de
  `ChangeRow` CDC, ce chantier lui ajoute un point d'entrée alternatif prenant une relation DuckDB
  directement — à trancher en plan si l'adaptation de signature s'avère plus intrusive que prévu, cf.
  risque §5).
- Extension additive d'`OperationContract` (`app/pipelines/ops/contracts.py`) : nouveau champ
  `exchange: Literal["arrow_stream", "geoparquet_file"] | None = None`. Défaut `None` pour les 19 op
  existantes (aucune ne l'utilise — les 12 op DuckDB pur SQL n'ont besoin d'aucun échange, et
  `transform.qgis` garde son échange fichier propre, non unifié avec ce nouveau champ, cf. hors
  périmètre). Aucune entrée du registre `OPERATIONS` ne fixe cette valeur dans ce chantier — le champ
  existe pour que le futur chantier « premier moteur natif » l'utilise sans redevoir étendre le
  dataclass.
- Tests : round-trip identité (schéma + CRS + valeurs de géométrie préservés, cas EPSG:2154), erreur
  propre sur relation sans géométrie, non-duplication du writer GeoParquet (le test importe
  directement `write_geoparquet`, pas une réimplémentation), suite existante des 19 op inchangée (même
  garantie qu'OperationContract : diff de comportement nul).

**Hors périmètre, explicitement (à ne pas réinterpréter en cours d'exécution) :**
- **Aucun moteur natif réellement câblé** (GDAL/PDAL/OTB/Rust) — ce chantier ne fait que poser le seam
  d'échange ; le câbler à un vrai binding (vérifier la version GDAL du futur conteneur, la maturité
  Arrow de PDAL/OTB — non tenue pour acquise ici) est un chantier séparé, ultérieur.
- **Aucun changement à `transform.qgis`/`runtime.py`/`_execute_qgis_transform`** — GPKG, l'allowlist et
  le sidecar HTTP restent identiques. Décision explicite de la session : ne pas optimiser une surface
  destinée à se réduire.
- **Aucune nouvelle op ni transformer** de la matrice FME.
- **`exchange` n'est jamais consommé par aucun code d'exécution réel** dans ce chantier — champ de
  contrat seul, pas de branche `if contract.exchange == ...` dans `runtime.py` (rien à brancher, aucun
  moteur ne le lit encore). Un futur chantier qui câble un moteur natif est celui qui écrira cette
  branche.
- **Aucun changement d'API publique** (`GET /pipelines/ops`) — `exchange` n'entre jamais dans
  `ops_catalog()`, même traitement que les champs `engine`/`engine_license`/`execution_model` déjà
  invisibles côté shell. Diff `openapi.json`/`core-schema.d.ts` vide attendu, à vérifier plutôt que
  supposer.

## 3. Architecture

Deux chemins d'échange, choisis par le futur moteur selon sa nature — ni l'un ni l'autre n'est
imposé, ce chantier construit les deux :

**Chemin 1 — zéro-copie Arrow (`arrow_stream`), pour un moteur lié en Python/Rust dans le même
process que `runtime.py`** : pas de fichier, pas de volume scratch, pas de sérialisation. Le futur
appelant fait `reader = to_arrow_stream(relation, srid=srid)`, passe `reader` directement à son binding
(GDAL≥3.6 via l'API Arrow OGR, un module Rust via `arrow-rs`/PyO3), récupère un `RecordBatchReader` en
retour, le réinjecte via `from_arrow_stream`. Pertinent pour un moteur dont le binding accepte
nativement l'interface Arrow C Data — à vérifier par moteur avant de l'y engager, jamais supposé.

**Chemin 2 — GeoParquet natif en repli (`geoparquet_file`), pour un moteur qui doit rester un
process séparé mais comprend Parquet** : écriture via le writer natif DuckDB (measuré 8-10x plus
rapide/compact que tout pont GDAL), en réutilisant `write_geoparquet` — jamais un fichier GPKG/FlatGeobuf
pour ce cas, le gain de performance mesuré vient justement de l'absence de pont GDAL.

**QGIS n'emprunte ni l'un ni l'autre** : son échange fichier (GPKG, `_execute_qgis_transform`/
`_materialize_qgis_output`) reste géré tel quel, hors de ce module, documenté comme l'exception figée.

## 4. Erreurs et cas limites

- Relation sans colonne géométrie détectée → `PipelineRuntimeError` explicite (jamais un
  `IndexError`/`KeyError` silencieux sur une liste vide de colonnes géométrie), même patron que
  `_materialize_qgis_output`.
- CRS non fourni à `to_arrow_stream` (paramètre `srid` obligatoire, pas optionnel) — élimine par
  construction le cas mesuré où `.arrow()` renvoie des métadonnées vides faute de `ST_SetCRS` explicite.
- `from_arrow_stream` sur un flux déjà épuisé (un `RecordBatchReader` ne peut être consommé qu'une
  fois) : documenté dans le docstring, pas de garde runtime — cohérent avec le fait qu'aucun code
  d'exécution réel n'appelle encore cette fonction dans ce chantier.

## 5. Risques et points à vérifier en plan (pas supposés ici)

- **Signature de `write_geoparquet`** : conçue pour une liste de `ChangeRow` CDC, pas pour une relation
  DuckDB arbitraire — l'implémentation devra soit factoriser un chemin commun (relation → lignes), soit
  constater que l'adaptation est trop intrusive et écrire un writer parallèle minimal qui appelle les
  mêmes primitives GeoParquet internes (pas un writer réinventé de zéro). Trancher à l'implémentation,
  pas ici.
- **Maturité Arrow de GDAL/PDAL/OTB** : affirmations publiques (GDAL≥3.6 a une API Arrow OGR, PDAL a des
  étapes `readers.arrow`/`writers.arrow`) non vérifiées empiriquement dans cette session faute de
  binding installé — à revérifier contre le binding réel avant qu'un futur chantier ne s'appuie dessus
  pour de vrai.
- **`exchange` sans consommateur** : ce champ de contrat restera mort tant qu'aucun moteur natif n'est
  câblé — risque documenté d'« abstraction prématurée » (CLAUDE.md, YAGNI) atténué par le fait qu'il est
  optionnel (défaut `None`, zéro impact sur les 19 op existantes) et que la matrice FME chiffre déjà 76
  transformers qui en dépendront réellement (§ Référence) — pas un seam spéculatif sans demande connue.

## 6. Suite

Une fois ce chantier posé, le prochain (hors périmètre ici, à brainstormer séparément) : câbler un
premier moteur natif réel (candidat le plus documenté par la matrice : GDAL pour les 55
`planned_gdal`), choisir `arrow_stream` ou `geoparquet_file` selon ce que son binding accepte
réellement, et vérifier le round-trip contre ce moteur pour de vrai — ce que cette session ne peut pas
faire faute de binding installé.

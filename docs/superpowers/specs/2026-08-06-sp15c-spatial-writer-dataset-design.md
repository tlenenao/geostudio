# SP-15c — Pipeline : opérations spatiales étage 1 + `writer.dataset` (design)

> **Date : 2026-08-06 · Statut : validé (brainstorm tenu en session)**
> Troisième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39**), correspondant à la partie *étage 1*
> de la Phase 3 de l'étude de faisabilité
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> (§5 « Spatial & largeur FME »). SP-15a a livré le socle headless (document
> `Pipeline`, 8 op data-only, runtime DuckDB, job procrastinate,
> `CORE_ETL_ENABLED`) ; SP-15b a livré le canvas no-code shell
> (`PipelineBuilderPage`, palette/inspecteur/aperçu/run schema-driven). Ce
> sous-plan ajoute des op au catalogue existant sans toucher au moteur de
> compilation/exécution lui-même.
>
> **Découpage de la Phase 3 de l'étude en trois sous-parties** (décidé en
> brainstorm, la Phase 3 telle que décrite dans l'étude regroupait quatre
> sujets hétérogènes) :
> - **SP-15c (ce document)** : opérations spatiales étage 1 (DuckDB, sans
>   nouvelle infra) + `writer.dataset` (termine la subsomption A39).
> - **SP-15d (à venir)** : sidecar `qgis_process` (étage 2, GPL, profil
>   compose `etl`, spike d'ouverture D2 de l'étude).
> - **SP-15e (à venir)** : `reader.connector` dlt (REST + Postgres).
>
> Références : feuille de route (§SP-15, A39) · `CLAUDE.md` (règles
> d'architecture #1-4) ·
> [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (document `Pipeline`, catalogue d'op, `ops/schemas.py`, `compiler.py`,
> `runtime.py`, `config_validation.py` — tous réutilisés et étendus ici) ·
> [`2026-08-06-sp15b-canvas-nocode-design.md`](2026-08-06-sp15b-canvas-nocode-design.md)
> (canvas schema-driven, `PipelineCanvas.tsx`) · SP-11b (`duckdb_conn.py`,
> extension `spatial` déjà chargée, CTE de dédoublonnage CDC GeoParquet) ·
> SP-14a (`DatasetPayload`, source de vérité de ce que `writer.dataset`
> catalogue).

## 1. Objectif & non-buts

**Objectif.** Étendre le catalogue de 8 op de SP-15a avec **5 op de
transformation spatiale étage 1** (`transform.buffer`, `transform.reproject`,
`transform.intersection`, `transform.countWithin`, `transform.h3Aggregate`) et
**1 nouveau writer** (`writer.dataset`), qui achève l'amendement A39 : le
« pipeline de transformations déclaratif » d'un dataset (SP-14/A28) **est**
désormais un `Pipeline` réel se terminant par ce writer, plus une prose
séparée non implémentée.

Toutes les op nouvelles sont couvertes par le runtime existant : DuckDB
in-process, aucune dépendance externe hors l'extension communautaire `h3`
(installée au build d'image, pas au runtime). Aucun changement au mécanisme
de validation de graphe, à la matérialisation nœud-par-nœud, au job
procrastinate, ni à `CORE_ETL_ENABLED` — uniquement des entrées
supplémentaires dans les points d'extension déjà identifiés par SP-15a :
`ops/schemas.py` (catalogue), `compiler.py` (compilation SQL),
`runtime.py` (validation d'expressions + dispatch writer),
`config_validation.py` (perms).

**Non-buts explicites** (reportés) :
- **Sidecar `qgis_process`**, op `qgis:*`, profil compose `etl` — SP-15d.
- **`reader.connector` dlt** (REST/Postgres) — SP-15e.
- **`transform.sql`** échappatoire DuckDB brut réservé à l'analyste — Phase 4
  (inutile tant qu'aucun canvas n'a de raison de l'exposer prudemment, cf.
  étude §3.3).
- **Polyfill H3** (couverture d'un polygone par plusieurs cellules) — MVP :
  une cellule par ligne, dérivée du centroïde. Suffisant pour l'agrégation
  spatiale demandée par les cas d'usage de l'étude (densité par zone), pas
  pour de la cartographie de précision cellule-exacte.
- **Réconciliation automatique de CRS** entre deux entrées d'une même op
  spatiale — l'auteur du pipeline doit intercaler un `transform.reproject`
  explicite si les CRS diffèrent ; l'op refuse de compiler sinon (§2, §3.3).
- **Refonte de `DatasetPayload`** : `writer.dataset` réutilise le modèle
  `source="collection"` existant tel quel, il n'introduit pas de nouveau
  mode de stockage dataset (cf. §4, arbitrage décidé en brainstorm après
  avoir constaté qu'aucune couche de matérialisation dataset n'existe
  aujourd'hui).

## 2. Mécanisme transverse : suivi du CRS par vue

Aucune des 8 op de SP-15a n'a besoin de connaître le SRID d'une géométrie
(elles ne la manipulent jamais géométriquement — `transform.join` fait un
`JOIN`/`ON` arbitraire, jamais un prédicat spatial). `transform.reproject` et
le mode `unit="meters"` de `transform.buffer` en ont besoin ; `transform.
intersection`/`transform.countWithin` en ont besoin pour leur garde de
cohérence (§3.3).

Le compilateur (`compiler.py`) gagne un état parallèle à `view_by_node` :

```python
srid_by_node: dict[str, int]   # node.id -> SRID courant de sa vue de sortie
```

- Initialisé pendant `_prepare` (pass 1) : chaque `reader.collection`
  matérialisé reçoit `info.srid or 4326` (même repli que
  `core/app/features/repository.py`).
- Propagé identique à travers toutes les op qui ne touchent pas à la
  géométrie (`filter`, `select`, `derive`, `aggregate`, `countWithin`,
  `intersection` avec `outputGeometry="left"`, `buffer` — le buffer revient
  au SRID d'entrée après son aller-retour interne en 3857).
- Mis à jour uniquement par `transform.reproject`, vers son `targetCrs`
  parsé en entier SRID.

Cet état ne vit que pendant la compilation d'un run (comme `view_by_node`) —
aucune persistance, aucun changement de `PipelineNode`/`PipelineEdge`.

## 3. Catalogue des 5 op spatiales

### 3.1 `transform.buffer`

```python
class TransformBufferParams(BaseModel):
    distance: float
    unit: Literal["meters", "native"] = "meters"
```

- `unit="native"` : `ST_Buffer(geometry, :distance)` directement, dans les
  unités du CRS courant (degrés si 4326).
- `unit="meters"` (défaut, cas no-code attendu par un auteur non-SIG) :
  `ST_Transform` vers `EPSG:3857`, `ST_Buffer`, `ST_Transform` retour vers le
  SRID d'entrée — trois appels chaînés dans la même vue. Approximation
  planaire assumée (`ST_Buffer` ne corrige pas la courbure terrestre),
  documentée comme limite connue, cohérente avec le classement "🟡 faible
  gravité" de l'étude pour ce type de compromis.
- `srid_by_node` inchangé après cette op (retour au SRID d'entrée en mode
  `meters`).

### 3.2 `transform.reproject`

```python
class TransformReprojectParams(BaseModel):
    targetCrs: str = Field(pattern=r"^[A-Za-z]+:\d+$")   # ex. "EPSG:3857"
```

- SQL : `SELECT * EXCLUDE (geometry), ST_Transform(geometry,
  'EPSG:' || :srid_courant, :targetCrs) AS geometry FROM <input>`.
- Met à jour `srid_by_node[node.id]` vers l'entier extrait de `targetCrs`.
- Le pattern Pydantic borne la forme acceptée (pas de free-form SQL injecté
  dans un identifiant de CRS) — cohérent avec la posture "pas d'échappatoire
  non bornée" déjà tenue pour `filter.expr`/`derive.expr`.

### 3.3 `transform.intersection`

Variante spatiale de `transform.join` (même mécanisme de matérialisation
implicite de `withCollectionId` en pass 1) :

```python
class TransformIntersectionParams(BaseModel):
    withCollectionId: str = Field(json_schema_extra={"format": "collection-id"})
    how: Literal["inner", "left"] = "inner"
    outputGeometry: Literal["left", "intersection"] = "left"
```

- SQL : `SELECT ... FROM <input> t {INNER|LEFT} JOIN <other> o ON
  ST_Intersects(t.geometry, o.geometry)`, géométrie finale = `t.geometry`
  (défaut) ou `ST_Intersection(t.geometry, o.geometry)` selon
  `outputGeometry`.
- **Garde CRS** : si `srid_by_node[input] != srid_by_node[other]`, erreur de
  compilation explicite (« reprojeter d'abord avec transform.reproject »)
  plutôt qu'un résultat silencieusement faux. Pas de réconciliation
  implicite (non-but §1).

### 3.4 `transform.countWithin`

```python
class TransformCountWithinParams(BaseModel):
    withCollectionId: str = Field(json_schema_extra={"format": "collection-id"})
    countColumn: str = "count"
    predicate: Literal["intersects", "contains"] = "intersects"
```

- SQL : `SELECT t.* EXCLUDE (geometry), t.geometry, COUNT(o.geometry) AS
  :countColumn FROM <input> t LEFT JOIN <other> o ON ST_{Intersects|Contains}
  (t.geometry, o.geometry) GROUP BY ALL` — `GROUP BY ALL` (natif DuckDB)
  évite d'énumérer les colonnes de `t`, dont le schéma varie selon le
  pipeline amont (le même problème qu'aurait un `GROUP BY` explicite sur un
  schéma dynamique).
- Même garde CRS que `transform.intersection`.
- Cas d'usage #3 de l'étude (« incidents à moins de 500 m d'une école, par
  commune ») se compose en chaînant `transform.buffer` (500 m sur les
  écoles) → `transform.countWithin` (compter les incidents dans chaque
  buffer) → `transform.aggregate` (déjà existant, group by commune).

### 3.5 `transform.h3Aggregate`

```python
class TransformH3AggregateParams(BaseModel):
    resolution: int = Field(ge=0, le=15)
    metrics: dict[str, str]   # même forme que TransformAggregateParams.metrics
```

- SQL : `SELECT h3_latlng_to_cell(ST_Y(ST_Centroid(geometry)),
  ST_X(ST_Centroid(geometry)), :resolution) AS h3Cell,
  ST_GeomFromText(h3_cell_to_boundary_wkt(h3Cell)) AS geometry,
  <metrics...> FROM <input> GROUP BY h3Cell` (la fonction exacte de
  conversion WKT→GEOMETRY — `ST_GeomFromText` vs un cast dédié — sera
  confirmée au premier test de compilation contre un DuckDB réel, pas figée
  ici).
- Centroïde uniquement (polyfill hors périmètre, §1).
- Coordonnées H3 toujours WGS84 par construction (`h3_latlng_to_cell` prend
  lat/lng) : si `srid_by_node[input] != 4326`, compilation refusée avec le
  même message de garde que §3.3/3.4, pas de reprojection implicite.
- `srid_by_node[node.id]` = `4326` après cette op.
- Nécessite `INSTALL h3 FROM community;` **au build de l'image** (`Dockerfile`,
  à côté de l'`INSTALL spatial;` déjà présent), et `LOAD h3;` ajouté dans
  `core/app/analytics/duckdb_conn.py:22` à côté de `LOAD spatial;`. Pas
  d'installation réseau au runtime — cohérent avec `enable_external_access=
  false` posé par `_lock_down` (`LOAD` lit l'extension déjà présente sur
  disque, ne nécessite aucun accès réseau).

## 4. `writer.dataset`

**Constat d'exploration** : il n'existe aujourd'hui **aucune couche de
matérialisation dataset**. `DatasetPayload` (SP-14a,
`core/app/configs/schemas.py:114-134`) est une pure référence displayée
(`source: Literal["collection","arcgis"]` + métadonnées d'affichage), jamais
une cible d'écriture — il n'y a pas de `core/app/datasets/` avec une
ingestion propre. `writer.dataset` **ne crée pas** une nouvelle couche de
stockage : il réutilise la collection comme support physique et catalogue le
résultat comme un item `dataset`.

```python
class WriterDatasetParams(BaseModel):
    collectionId: str = Field(json_schema_extra={"format": "collection-id"})
    datasetId: str | None = None   # pk d'un item BuilderConfig(kind="dataset") existant
    title: str | None = None       # requis si datasetId est None
```

Validation additionnelle (miroir de celle de `PipelinePayload` — au moins un
writer) : `title` obligatoire quand `datasetId` est absent.

**Exécution** (`runtime.py`, nouvel `elif node.op == "writer.dataset"` à côté
de `_write_collection`/`_write_export`) :

1. Écrit les lignes dans `collectionId` **via `_write_collection` tel
   quel** — même fonction, même chemin d'écriture OGC Features
   (`validate_feature` → `insert_feature`), même `rls_scope`. Aucune
   nouvelle primitive d'écriture.
2. Upsert un item `BuilderConfig(kind="dataset")` :
   - `datasetId` fourni → charge l'item, `can(actor, "update", item)`,
     remplace son `DatasetPayload` par `source="collection", collectionId=
     <collectionId>` ; métadonnées d'affichage existantes (`columns`,
     `timeField`, `reactsToExtent`, `crossFilterLinks`) **préservées telles
     quelles**, jamais régénérées par le run.
   - `datasetId` absent → crée un nouvel item, `title` requis,
     `DatasetPayload(source="collection", collectionId=...)`, propriétaire =
     l'acteur du run (utilisateur ou agent MCP), `tenant_id`/`audit_log`
     standard (idem toute création d'item).

**Permissions** (`config_validation.py`) :
- `_WRITE_OPS` étendu avec `"writer.dataset"` pour la vérification d'écriture
  sur `collectionId` (identique à `writer.collection`, à la sauvegarde du
  pipeline).
- **Check additionnel au moment du run** (pas à la sauvegarde, puisque
  `datasetId` peut référencer un dataset créé par un run précédent, donc
  inconnu au moment où le pipeline est enregistré) : si `datasetId` est
  fourni, `can(actor, "update", dataset_item)` doit passer, sinon le run
  échoue proprement (statut `failed`, message explicite) — aucun
  contournement de `can()` par le biais du pipeline.

## 5. Shell

Zéro changement dans `PipelinePalette.tsx`, `PipelineNodeInspector.tsx`,
`CollectionParamSelect.tsx`, `validation.ts` (confirmé schema-driven en
exploration — dispatch uniquement sur `entry.kind`/`prop.format`/`prop.type`,
jamais sur un nom d'`op` littéral). Les 6 nouvelles op (5 transform + 1
writer) sont immédiatement glissables-déposables depuis la palette et leurs
params s'auto-génèrent dans l'inspecteur sans aucun code shell nouveau.

**Seul point à toucher** : `PipelineCanvas.tsx:14-20`
(`INSERTABLE_TRANSFORMS`) — liste **actuellement codée en dur** des 5 op
`transform.*` proposées par le menu "+" d'insertion sur arête. Les 5 nouvelles
op transform y sont ajoutées (pas `writer.dataset`, qui n'est de toute façon
pas une op `transform`, donc jamais candidate à cette liste). Sans cet ajout,
les op spatiales resteraient accessibles uniquement par glisser-déposer
depuis la palette — une incohérence UX mineure mais évitable en 5 lignes.

## 6. Compatibilité & tests

- **Aucune migration DB** (pas de nouvelle table — `writer.dataset` réutilise
  `BuilderConfig`/`Collection` existants).
- **Aucun changement de comportement** pour les 8 op existantes ni pour
  `PipelineBuilderPage`/canvas/palette côté shell.
- Par op nouvelle : un test de compilation SQL (fixture DuckDB in-memory,
  géométries synthétiques — pas de PostGIS, cohérent avec le style des tests
  `compiler.py`/`runtime.py` existants), un test de validation des params
  (bornes `resolution` 0-15, pattern `targetCrs`, enums `predicate`/`how`/
  `outputGeometry`), un test de garde CRS pour `intersection`/`countWithin`/
  `h3Aggregate` (mismatch → erreur explicite, pas de résultat silencieux).
- `writer.dataset` : test de création (nouveau dataset), test de mise à jour
  (`datasetId` existant, métadonnées d'affichage préservées), test de refus
  si `can(actor, "update", dataset)` échoue au run, un scénario bout-en-bout
  couvrant le cas d'usage #3 de l'étude (buffer → countWithin → aggregate →
  writer.dataset).
- Suites existantes (`core` pytest, `shell` vitest/e2e, 87 specs Playwright)
  restent vertes — aucune régression attendue, extension additive pure.

## 7. Risques

| Risque | Mitigation |
|---|---|
| `ST_Buffer` planaire imprécis pour de grandes distances/hautes latitudes | Documenté comme limite connue (non-but), acceptable pour un MVP « équivalent FME progressif » (étude §6.1) |
| Fonction exacte de conversion WKT→GEOMETRY pour `h3_cell_to_boundary_wkt` non vérifiée sur le papier | Confirmée au premier test de compilation réel contre DuckDB (§3.5), pas bloquant pour le design |
| `GROUP BY ALL` sur un schéma dynamique (colonnes dupliquées entre `t` et une métrique nommée pareil) | Cas limite documenté, pas mitigé activement en MVP — un auteur qui nomme une métrique comme une colonne existante obtient une erreur DuckDB claire, pas un résultat silencieusement faux |
| `writer.dataset` masque la relation 1-N réelle (un dataset ne peut pointer que sur une seule collection, pas sur un pipeline multi-writer) | Cohérent avec `DatasetPayload.source="collection"` existant, pas une régression introduite ici |

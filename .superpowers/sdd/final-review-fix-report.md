# Rapport — corrections review finale SP-15a (géométrie preview/export)

Un seul commit : les deux findings partagent la même cause racine dans
`core/app/pipelines/runtime.py`.

## Cause racine

`_materialize_reader` renomme la colonne géométrie source en `"geometry"`
mais la garde en type `GEOMETRY` DuckDB brut. Le client Python DuckDB
renvoie ce type comme `bytes` WKB. `_write_collection` convertissait déjà
ça en GeoJSON au point d'écriture (`SELECT *, ST_AsGeoJSON(geometry) AS
geometry` conditionné par `has_geometry`), mais `preview_pipeline` et
`_write_export` lisaient encore la vue avec un `SELECT *` brut, donc
récupéraient du WKB.

## Finding 1 (Important) — `preview_pipeline` / `POST /pipelines/{id}/preview` → 500

**Changement — `preview_pipeline`** (`core/app/pipelines/runtime.py`,
autour de la ligne 244) : avant le `SELECT * FROM <view> LIMIT <n>` final,
détection `has_geometry` via `conn.execute(f"SELECT * FROM {view} LIMIT
0").description` (même technique que `_write_collection`), puis
`SELECT * EXCLUDE (geometry), ST_AsGeoJSON(geometry) AS geometry` à la
place du `SELECT *` bare si la vue a une colonne géométrie. Chaque ligne du
résultat a ensuite sa valeur `"geometry"` (chaîne GeoJSON) décodée via
`json.loads(...)` pour redevenir un objet réel (`{"type": "Point",
"coordinates": [...]}`) plutôt qu'une chaîne-dans-une-chaîne — c'est la
forme qu'un consommateur REST attend d'une ligne de preview. Comportement
inchangé si la vue n'a pas de colonne géométrie.

## Finding 2 (Important) — `writer.export` casse (geojson) ou écrit du bruit (csv)

**Changement — `_write_export`** (`core/app/pipelines/runtime.py`, autour
de la ligne 300) : même détection `has_geometry` + substitution
`ST_AsGeoJSON` que ci-dessus, avant le `fetchall()`.

- Branche `csv` : la colonne géométrie contient désormais une chaîne
  GeoJSON exploitable au lieu du repr Python des bytes WKB — aucun autre
  changement nécessaire, `csv.writer` l'écrit telle quelle.
- Branche `geojson` : deux bugs indépendants corrigés — (a) au lieu du
  `"geometry": None` codé en dur, la géométrie réelle de la ligne est
  extraite de `properties` (`properties.pop("geometry", None)`) puis
  décodée via `json.loads(...)` (ou `None` si la ligne n'a pas de
  géométrie) pour construire le `"geometry"` du Feature ; (b) `pop` retire
  aussi la colonne du dict `properties`, donc elle n'est plus dupliquée
  dans `"properties"` — même contrat que `_write_collection` qui fait un
  `row.pop("geometry")` équivalent avant de construire son feature.

`_materialize_reader` et `app/pipelines/compiler.py` n'ont pas été
touchés : conforme à la consigne (Phase 1 n'a aucune op spatiale, la
géométrie n'a besoin d'être encodée qu'aux deux frontières de sortie, pas
portée en GeoJSON à travers les vues de transform intermédiaires).

## Tests ajoutés — `core/tests/test_pipeline_runtime.py`

- `test_preview_pipeline_serializes_geometry` : pipeline reader→writer.export
  (up_to="r1", un reader avec colonne géométrie) ; vérifie que chaque ligne
  renvoyée a `"geometry"` sous forme d'objet GeoJSON réel
  (`{"type": "Point", "coordinates": [...]}`), et que `json.dumps(rows)`
  réussit (preuve que la vraie route HTTP via `jsonable_encoder` ne
  planterait pas, contrairement à avant le fix où c'était des `bytes`).
- `test_write_export_geojson_serializes_geometry` : `run_pipeline` avec un
  nœud `writer.export` `format="geojson"` et un `_FakeS3` capturant
  `put_object` ; vérifie que `json.loads(body)` réussit, que la géométrie de
  la feature correspond au point réel de la ligne (pas `None`), et qu'elle
  n'est pas dupliquée dans `"properties"`.
- `test_write_export_csv_geometry_as_geojson_string` : même patron,
  `format="csv"` ; vérifie via `csv.reader` que la cellule "geometry" est
  une chaîne JSON valide décodable en objet GeoJSON, pas un repr Python de
  bytes (`b'\x...'`).
- Nouvelle classe `_FakeS3` (stand-in `put_object`) ajoutée à côté de
  `_FakeCollections`, même esprit (pas de vrai bucket nécessaire).
- Imports ajoutés en tête de fichier : `csv`, `io`, `json`.

Les deux tests existants (`test_preview_filter_and_derive`,
`test_preview_rejects_writer_node_as_up_to`) et le test postgis
(`test_run_pipeline_writes_into_target_collection`) n'ont pas été modifiés.

## Commandes de test exécutées et résultats

```
cd core && uv run pytest tests/test_pipeline_runtime.py -v -k "not postgis"
→ 5 passed, 1 deselected (les 2 tests préexistants + les 3 nouveaux)

cd core && uv run pytest -k "not postgis" -q
→ 960 passed, 120 deselected (baseline pré-fix 957 + 3 nouveaux tests, aucune régression)

cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test \
  uv run pytest tests/test_pipeline_runtime.py tests/test_pipeline_jobs.py -v -m postgis
→ 4 passed, 5 deselected (test_run_pipeline_writes_into_target_collection +
  les 3 tests de test_pipeline_jobs.py), confirmant que _write_collection
  (le patron mirroré, non modifié) fonctionne toujours à l'identique.
```

Vérification post-run sur le conteneur `postgis-test` partagé : la table
`villes_propres` créée par le test a bien été droppée par le teardown du
test lui-même (`DROP TABLE villes_propres; TRUNCATE items, configs,
config_revisions, collections, audit_log, users, tenants CASCADE`) —
`items` et `pipeline_runs` sont vides après coup. Les tables `ingest_*`
visibles dans `\dt` sont des reliquats d'un travail antérieur non lié à
cette tâche, non créées par ce run, laissées en l'état (hors périmètre).

## Commit

- `d10a30a` — `fix(core): serialize geometry to GeoJSON in pipeline preview and export`
  (`core/app/pipelines/runtime.py`, `core/tests/test_pipeline_runtime.py`)

## Remarques

- Aucun signal contraire aux hypothèses du prompt : le patron
  `has_geometry` / `ST_AsGeoJSON(...) EXCLUDE` de `_write_collection` s'est
  appliqué tel quel aux deux autres fonctions, sans avoir besoin de
  toucher `_materialize_reader` ni `compiler.py`.
- Fichiers `.superpowers/sdd/*.md` (task-1..6, progress.md) déjà modifiés
  dans l'arbre de travail avant cette tâche, non liés à ces deux findings —
  volontairement laissés hors du commit, comme demandé.

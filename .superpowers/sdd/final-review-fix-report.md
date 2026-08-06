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

## Fix: PipelineRunPanel onRun error handling

Finding (Important) de la review finale SP-15b : dans
`shell/src/builder/pipeline/PipelineRunPanel.tsx`, si `client.runPipeline(pipelineId)`
ou le premier `client.getPipelineRuns` appelé depuis `poll()` rejette (erreur
serveur, panne réseau), `setRunning(false)` n'était jamais atteint — le
bouton restait bloqué sur « Exécution… » définitivement désactivé, avec une
promesse rejetée non gérée. Distinct du cas où un run se termine avec le
statut `"failed"` (ce chemin fonctionnait déjà : `poll()` voit le statut
terminal, efface `running`, et le `role="alert"` par run affiche
`run.error`) — seul l'échec de la requête elle-même bloquait l'UI.

### Changement

- Ajout d'un état séparé `runError` (distinct du champ `error` par run) :
  `const [runError, setRunError] = useState<string | null>(null);`
- `onRun` réécrit avec `try/catch/finally` : `setRunError(null)` avant
  l'appel, capture de l'exception dans le `catch` (`e.message` si
  `instanceof Error`, sinon message générique « Échec du lancement du
  pipeline. »), et `setRunning(false)` déplacé dans un `finally` (le `poll()`
  continue par ailleurs d'appeler `setRunning(false)` lui-même sur statut
  terminal normal — le `finally` y est redondant mais inoffensif, choix
  délibéré pour rester minimal).
- Rendu du nouvel état juste sous le bouton « Exécuter », au-dessus du
  `<ul>` des runs : `{runError && <p role="alert" className="text-red-600
  text-xs">{runError}</p>}` — mêmes classes Tailwind que le `role="alert"`
  par run déjà présent dans le fichier (`text-red-600`), avec `text-xs`
  ajouté pour cohérence avec les autres textes de la liste.

### Test ajouté — `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`

`"if runPipeline itself fails, the button re-enables and shows an error
instead of staying stuck"` : `runPipeline` mocké pour rejeter avec
`new Error("réseau indisponible")`, clic sur « Exécuter », attend que le
bouton redevienne actif (`toBeEnabled()`), vérifie que `role="alert"`
contient le message. Suit exactement le patron `renderPanel(overrides)`
déjà utilisé par les 3 autres tests du fichier.

### Commandes de test exécutées et résultats

```
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx
→ Test Files 1 passed (1), Tests 4 passed (4)

cd shell && npx tsc --noEmit
→ aucune sortie (clean)
```

### Commit

- `39fa6bd` — `fix(shell): recover pipeline run panel from a failed run/poll request`
  (`shell/src/builder/pipeline/PipelineRunPanel.tsx`,
  `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`)

### Remarques

- `poll()` lui-même n'a pas été modifié, comme demandé — la redondance du
  `finally` avec son `setRunning(false)` interne sur le chemin nominal est
  volontaire (fix minimal, facile à auditer).
- Seuls les deux fichiers shell listés ont été stagés/commités ; les
  fichiers `.superpowers/sdd/*.md` déjà modifiés dans l'arbre avant cette
  tâche restent hors du commit.

## Fix: SP-15d — sidecar qgis-worker (4 findings, revue finale de branche)

Un seul commit pour les 4 findings : tous concernent le même dispatch
`transform.qgis` (`_execute_qgis_transform`) ou son sidecar HTTP.

### Finding 1 (Important) — colonne géométrie du GPKG sidecar non renommée

**Cause** : `_execute_qgis_transform` matérialisait `ST_Read(out_path)` tel
quel (`SELECT * FROM ST_Read(...)`), en supposant que la colonne géométrie
s'appelle déjà `"geometry"`. Faux en général : vérifié empiriquement que
même DuckDB's propre `COPY ... TO ... WITH (FORMAT GDAL, DRIVER 'GPKG', ...)`
nomme sa colonne géométrie `"geom"`, pas `"geometry"` — GDAL/QGIS font de
même. Toute la chaîne en aval (`preview_pipeline`'s `has_geometry =
"geometry" in input_cols`, `_write_export`, `_write_collection`) dépend de
ce nom littéral ; silencieusement, la géométrie disparaissait.

**Changement — `core/app/pipelines/runtime.py`** : extraction d'une
nouvelle fonction `_materialize_qgis_output(conn, *, out_path, view_name,
algorithm_id)` (juste avant `_execute_qgis_transform`, ~ligne 238) qui :
1. sonde les colonnes de `ST_Read(out_path)` via `.description` ;
2. détecte la colonne géométrie par **type** DuckDB (`d[1].id ==
   "geometry"`, robuste au SRID annoté dans le type, ex.
   `GEOMETRY('EPSG:4326')`), jamais par nom ;
3. si aucune colonne géométrie n'est trouvée (sortie non-vecteur d'un
   algorithme dégénéré), lève `PipelineRuntimeError` explicite — jamais un
   `KeyError`/résultat vide silencieux (contrainte du finding respectée) ;
4. sinon, construit un `SELECT` explicite qui aliase cette colonne en
   `"geometry"` (même garantie que `_materialize_reader` donne déjà aux
   readers, cf. en-tête du module) avant le `CREATE TEMP TABLE` final.

`_execute_qgis_transform` appelle désormais ce helper au lieu d'inliner le
`ST_Read` naïf. Aucune autre des 14 opérations pré-existantes n'a été
touchée.

### Finding 2 (Minor) — nettoyage du scratch seulement sur succès

**Cause** : `shutil.rmtree(scratch_dir, ...)` n'était exécuté qu'après la
dernière ligne de la fonction — toute exception antérieure (timeout, erreur
HTTP, statut non-200, échec du `ST_Read`) laissait `in.gpkg`/`out.gpkg`
dans le volume partagé `etl-scratch` sans nettoyage.

**Changement** : tout le corps de `_execute_qgis_transform` à partir du
`COPY` (inclus) est désormais dans un `try/finally` ; le `finally` appelle
`shutil.rmtree(scratch_dir, ignore_errors=True)` — `ignore_errors=True`
conservé pour qu'un échec du nettoyage ne masque jamais l'exception réelle
en cours de propagation. `import shutil` déplacé en tête de module (n'était
importé qu'inline auparavant).

**Testabilité** : `scratch_dir` était construit avec `/scratch` en dur —
inaccessible en écriture dans cet environnement (répertoire appartenant à
root, `mkdir`/`touch` → `Permission denied`, confirmé). Extraction d'une
constante module `_QGIS_SCRATCH_ROOT = "/scratch"` (juste avant le nouveau
helper) que les tests redirigent vers un `tmp_path` via `monkeypatch` — la
valeur par défaut en production reste `/scratch`, comportement inchangé.

### Finding 3 (Minor) — sidecar sans garde sur requête malformée

**Cause** — `deploy/qgis-worker/server.py`, `Handler.do_POST` : un corps non
JSON, ou JSON valide sans `algorithmId`/`inputs`, levait une exception non
attrapée (`json.JSONDecodeError`/`KeyError`/`TypeError`) — confirmé
empiriquement (RED ci-dessous) : le client recevait `httpx.
RemoteProtocolError: Server disconnected without sending a response`
plutôt qu'une réponse HTTP propre.

**Changement** : le parsing (`json.loads` + accès `body["algorithmId"]`/
`body["inputs"]`) est enveloppé dans `try/except (json.JSONDecodeError,
KeyError, TypeError)`, qui répond `400 {"error": "requête invalide : ..."}`
via le helper `_respond` existant. Le reste du contrat (403/502/504/200)
inchangé.

### Finding 4 (Minor) — `.json()` du client peut lui-même planter

**Cause** — `core/app/pipelines/runtime.py`, branche non-200 : `response.
json().get("error", response.text)` suppose que le corps d'erreur est du
JSON valide. Désormais fermé côté sidecar par le Finding 3, mais pas côté
client — un intermédiaire (proxy/gateway) pourrait renvoyer un corps non-
JSON.

**Changement** : `try: detail = response.json().get(...) except ValueError:
detail = response.text` (json.JSONDecodeError est une sous-classe de
ValueError) — défense en profondeur, `PipelineRuntimeError` toujours levée
avec le meilleur texte disponible, jamais de crash sur `.json()` lui-même.

### Tests ajoutés

**`core/tests/test_pipeline_runtime.py`** (insérés juste avant les tests
`@pytest.mark.qgis` existants qui nécessitent un vrai sidecar) :

- `test_materialize_qgis_output_renames_non_geometry_named_column` —
  écrit un vrai GPKG via `COPY ... FORMAT GDAL DRIVER GPKG` (DuckDB lui-même,
  aucun sidecar requis), vérifie d'abord que ce fichier a bien une colonne
  `"geom"` et pas `"geometry"` (preuve de la prémisse du finding), puis que
  `_materialize_qgis_output` expose `"geometry"` avec la bonne valeur
  (`ST_AsText` == `"POINT (3 4)"`).
- `test_materialize_qgis_output_raises_clean_error_without_geometry_column`
  — un CSV lu via `ST_Read` (aucune colonne géométrie du tout, cas
  dégénéré) doit lever `PipelineRuntimeError` (match "aucune colonne
  géométrie"), jamais un `KeyError` silencieux.
- `test_execute_qgis_transform_cleans_scratch_dir_on_sidecar_error` —
  `httpx.post` mocké (502 + corps JSON `{"error": ...}`), `_QGIS_SCRATCH_
  ROOT` redirigé vers `tmp_path` ; vérifie que `PipelineRuntimeError` est
  levée ET que `scratch_dir` n'existe plus après coup.
- `test_execute_qgis_transform_raises_clean_error_on_non_json_error_body` —
  même patron, `httpx.post` mocké renvoie un corps texte non-JSON
  (`"<html>Bad Gateway</html>"`) ; vérifie `PipelineRuntimeError` avec ce
  texte dans le message, pas de `json.JSONDecodeError` non attrapée.
- Nouvelle classe `_FakeQgisWorkerResponse` (stand-in `httpx.Response` :
  `status_code`/`.json()`/`.text`) et helper `_make_qgis_input_connection()`
  ajoutés à côté de `_FakeS3`, même esprit.

**`core/tests/test_qgis_worker_server_handler.py`** (nouveau fichier — pas
d'infra de test existante dans `deploy/qgis-worker/`, colocation choisie
dans `core/tests/` pour être exécuté par `uv run pytest` du cœur ;
`server.py` chargé par chemin de fichier via `importlib.util`, lecture de
`/app/allowlist.txt` neutralisée par `unittest.mock.patch("pathlib.Path.
read_text", ...)` puisque ce chemin n'existe que dans le conteneur) :

- `test_do_post_non_json_body_returns_clean_400`
- `test_do_post_missing_algorithm_id_returns_clean_400`
- `test_do_post_missing_inputs_returns_clean_400`
- `test_do_post_valid_request_still_reaches_allowlist_check` (non-régression :
  le nouveau guard ne doit pas avaler les requêtes bien formées — vérifie
  que le chemin 403 pré-existant est toujours atteint).

Chaque test démarre un vrai `ThreadingHTTPServer` sur un port éphémère
(`("127.0.0.1", 0)`) dans un thread daemon, y poste une vraie requête HTTP
via `httpx`, l'arrête en fin de fixture — aucun `qgis_process` ni conteneur
requis (tous les cas rejetés avant l'appel `subprocess.run`).

### RED → GREEN (evidence)

**Finding 1** (`git stash` du fix, repro directe hors pytest) :
```
$ uv run python -c "... conn.execute(f\"CREATE TEMP TABLE node_t1 AS SELECT * FROM ST_Read('{out_path}')\") ..."
columns: {'id', 'geom', 'fid'}
has_geometry (original bug reproduction): False
```
confirmant exactement le bug décrit (colonne `geom`, jamais `geometry`).

**Findings 1+2** (`git stash push -- core/app/pipelines/runtime.py`, puis
les 4 nouveaux tests qui en dépendent) :
```
FAILED test_materialize_qgis_output_renames_non_geometry_named_column
FAILED test_materialize_qgis_output_raises_clean_error_without_geometry_column
FAILED test_execute_qgis_transform_cleans_scratch_dir_on_sidecar_error
FAILED test_execute_qgis_transform_raises_clean_error_on_non_json_error_body
4 failed, 18 deselected
```
(`AttributeError: module 'app.pipelines.runtime' has no attribute
'_materialize_qgis_output'` / `'_QGIS_SCRATCH_ROOT'`) → `git stash pop`,
mêmes 4 tests :
```
5 passed, 17 deselected
```
(le 5e est le test préexistant `test_execute_qgis_transform_raises_clean_error_without_worker_url`).

**Finding 3** (`git stash push -- deploy/qgis-worker/server.py`) :
```
FAILED test_do_post_non_json_body_returns_clean_400
FAILED test_do_post_missing_algorithm_id_returns_clean_400
FAILED test_do_post_missing_inputs_returns_clean_400
3 failed, 1 passed
```
avec en stderr `KeyError: 'inputs'` dans le thread de traitement de la
requête et côté client `httpx.RemoteProtocolError: Server disconnected
without sending a response` — exactement le symptôme décrit par le
finding. `git stash pop` → :
```
4 passed
```

### Commandes de test exécutées et résultats

```
# avant fix (baseline)
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test uv run pytest -q
→ 1147 passed, 5 skipped in 81.07s

# après fix, suite complète
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test uv run pytest -q
→ 1155 passed, 5 skipped in 84.05s   (+8 nouveaux tests, 0 régression, mêmes 5 skips qgis)

cd core && uv run lint-imports
→ Analyzed 138 files, 399 dependencies. layered architecture KEPT. Contracts: 1 kept, 0 broken.
```

### Fichiers modifiés

- `core/app/pipelines/runtime.py` — `_execute_qgis_transform` (Findings
  1/2/4) + nouvelle fonction `_materialize_qgis_output` et constante
  `_QGIS_SCRATCH_ROOT` (Finding 1/2, testabilité) ; `import shutil` déplacé
  en tête de fichier.
- `deploy/qgis-worker/server.py` — `Handler.do_POST` (Finding 3).
- `core/tests/test_pipeline_runtime.py` — 4 tests + 1 stand-in + 1 helper
  (Findings 1/2/4).
- `core/tests/test_qgis_worker_server_handler.py` — nouveau, 4 tests
  (Finding 3).

### Auto-revue

- Les 14 autres opérations du pipeline (`reader.collection`, `transform.
  filter/select/derive/aggregate/join/intersection/countWithin/
  h3Aggregate`, `writer.collection/dataset/export`) n'apparaissent dans
  aucun diff — seule `_execute_qgis_transform` et son nouveau helper ont
  changé, vérifié via `git diff` ciblé sur les lignes retirées (aucune ligne
  hors de cette fonction).
- Un répertoire `deploy/qgis-worker/__pycache__/` est apparu comme
  sous-produit du chargement dynamique de `server.py` par
  `importlib.util` (ce répertoire n'a pas de `.gitignore` `__pycache__/`
  propre, contrairement à `core/`) — neutralisé dans le test lui-même via
  `sys.dont_write_bytecode = True` (sauvegardé/restauré), et le répertoire
  déjà créé supprimé manuellement. Rien à committer sur ce point.
- Le choix de garder `geom_cols[0]` (première colonne géométrie trouvée) en
  cas de pluralité inattendue n'est pas testé explicitement (aucun
  algorithme de l'allowlist SP-15d n'en produit plusieurs, vérifié en
  lisant `app/pipelines/ops/qgis_algorithms.py` en début de tâche) — documenté
  en commentaire dans le code plutôt que testé, pour ne pas fabriquer un
  cas qui n'existe nulle part dans l'allowlist réelle.
- Les 5 tests `@pytest.mark.qgis` restent skippés cette session (pas de
  sidecar réel disponible, `sudo` interactif indisponible) — conforme aux
  consignes ("gap déjà reconnu, hors périmètre").

### Remarques / points d'attention

- Aucun test contre un vrai conteneur `qgis-worker` n'a été exécuté cette
  session (contrainte explicite de la tâche). Les 4 nouveaux tests de
  `test_pipeline_runtime.py` et les 4 de `test_qgis_worker_server_handler.py`
  couvrent les 4 findings sans dépendance à `/scratch` réel ni à
  `qgis_process` installé.
- `_QGIS_SCRATCH_ROOT` et l'extraction de `_materialize_qgis_output` sont
  des refactors minimaux motivés uniquement par la testabilité des
  Findings 1/2 (sans eux, `/scratch` appartenant à root rendait tout test
  direct de `_execute_qgis_transform` impossible dans cet environnement) —
  le comportement par défaut en production est strictement identique
  (`/scratch`, même séquence d'opérations).

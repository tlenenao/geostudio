# Task 3 (SP-6a) — rapport d'implémentation

Worker `procrastinate` + pipeline d'import (table PostGIS + collection + item carte).

## Statut

**DONE** — implémentation conforme au brief, tous les tests locaux passent (297 passed,
36 skipped, aucune régression), `lint-imports` PASS.

## Ce qui a été implémenté

1. **`core/app/ingestion/storage.py`** (nouveau) — wrapper S3/MinIO fin :
   `make_s3_client`, `ensure_uploads_bucket` (create_bucket idempotent +
   put_bucket_cors), `generate_presigned_put_url` (PUT présigné, 900s par
   défaut), `download_object`.
2. **`core/app/ingestion/importer.py`** (nouveau) — `run_import(session, ...)` :
   parse (GeoJSON ou CSV lat/lon via `app.ingestion.parsers`) → déduit les
   colonnes/types → `CREATE TABLE public.ingest_<uuid>` + `INSERT` en bulk →
   `introspect_table` + `apply_collection_ddl` (RLS, GRANTs) →
   `collections_repo.create_collection` → calcule extent/zoom
   (`table_extent`) → `items_repo.create_item` (resource_type="map") →
   `configs_repo.create_config` (BuilderConfig kind="map", une couche
   "feature" pointant `{CORE_BASE_URL}/collections/{id}/items`). Retourne
   `ImportResult(collection_id, item_id)`. Lève `IngestionParseError` avant
   toute écriture DDL/DML si le fichier est invalide ou vide.
3. **`core/app/ingestion/tasks.py`** (nouveau) — `app` (`procrastinate.App`
   module-level, `SyncPsycopgConnector(conninfo=...)`) et
   `run_ingestion_task(job_id, tenant_id)` (`@app.task(queue="ingestion")`) :
   `mark_running` → télécharge l'objet S3 → `run_import` → `mark_done`, avec
   `except IngestionParseError` → `mark_error(str(exc))` et
   `except Exception` (catch-all, log + `mark_error`) pour ne jamais laisser
   un job "zombie" en pending/running. `job is None` → log + `return` (no-op,
   pas de crash).
4. **`core/pyproject.toml`** + **`core/Dockerfile`** — `procrastinate>=2.0`
   ajouté aux deux listes (dépendance déclarée + liste `uv pip install`
   maintenue à la main du Dockerfile).
5. **`docker-compose.yml`** — `S3_UPLOADS_BUCKET: geostudio-uploads` ajouté à
   l'environnement de `core` ; nouveau service `worker` (même image `./core`,
   `procrastinate ... schema --apply && procrastinate ... worker -q ingestion`,
   env `DATABASE_URL`/`S3_*`/`CORE_BASE_URL`, `depends_on: [pgbouncer, minio]`).
6. **`.env.example`** — `S3_UPLOADS_BUCKET=geostudio-uploads` ajouté après
   `S3_THUMBNAILS_BUCKET`.

Tout le code implémenté est exactement celui fourni dans le brief (vérifié
contre les interfaces consommées — `app.collections.repository.create_collection`,
`app.collections.ddl.{apply_collection_ddl,quote_ident}`,
`app.collections.introspection_pg.introspect_table`,
`app.collections.extent.table_extent`, `app.configs.repository.create_config`,
`app.configs.schemas.{BuilderConfig,MapConfig,MapView,BaseMap,MapLayer}`,
`app.items.repository.create_item`, `app.db.{make_engine,make_session_factory,
request_scoped_session}` — toutes les signatures lues dans le code source
correspondent à ce que le brief attend, aucun ajustement nécessaire).

## Vérification de l'API procrastinate (constraint du brief)

`uv sync` a résolu **procrastinate 3.9.0** (le brief demandait `>=2.0`, un
saut de version majeure 2→3 était donc possible). J'ai vérifié directement
dans `.venv/lib/python3.14/site-packages/procrastinate/` avant d'écrire
`tasks.py`, comme demandé :

- `procrastinate.App.__init__(self, *, connector, import_paths=None,
  worker_defaults=None, periodic_defaults=None)` — `App(connector=...)`
  du brief est correct.
- `SyncPsycopgConnector.__init__(self, *, json_dumps=None, json_loads=None,
  **kwargs)` — tous les autres kwargs (dont `conninfo`) sont passés tels
  quels à `psycopg_pool.ConnectionPool(**pool_args, ...)`, dont la
  signature accepte bien `conninfo` en premier paramètre. `conninfo=...`
  du brief fonctionne sans changement.
- `Blueprint.task(self, _func=None, *, name=None, aliases=None, retry=False,
  pass_context=False, queue='default', ...)` — `@app.task(queue="ingestion")`
  correct.
- `Task.defer(self, *_, **task_kwargs) -> int` — `task.defer(job_id=...,
  tenant_id=...)` correct.
- `App.replace_connector(self, connector) -> Generator[App]` (context
  manager) — usage du test (`with ingestion_tasks.app.replace_connector(...)
  as app:`) correct.
- `App.run_worker(self, **kwargs)` (sync, ouvre l'event loop en interne) —
  `app.run_worker(wait=False, queues=["ingestion"])` correct.
- `procrastinate.testing.InMemoryConnector` — présent, sans argument au
  constructeur, tel qu'attendu.

**Aucune divergence trouvée** entre le brief et l'API installée (3.9.0) — le
snippet du brief a été utilisé tel quel dans `tasks.py`.

## Tests et résultats

### `test_ingestion_storage.py` — PASS (3/3), aucune dépendance PostGIS/MinIO

```
tests/test_ingestion_storage.py::test_ensure_uploads_bucket_creates_and_sets_cors PASSED
tests/test_ingestion_storage.py::test_generate_presigned_put_url_targets_put_object PASSED
tests/test_ingestion_storage.py::test_download_object_reads_body PASSED
3 passed in 0.04s
```

### `test_ingestion_importer.py` et `test_ingestion_tasks.py` (postgis) — SKIP propre

`CORE_TEST_DATABASE_URL` n'est pas défini dans cet environnement (confirmé,
`echo $CORE_TEST_DATABASE_URL` vide) et le conteneur `geostudio-postgis-1`
n'expose pas son port sur l'hôte — conformément à la contrainte d'environnement,
je n'ai pas essayé de contourner cela. Les deux suites collectent et **SKIP
proprement** (3 skipped chacune), pas d'erreur :

```
tests/test_ingestion_importer.py::test_geojson_import_creates_queryable_collection_and_map_item SKIPPED
tests/test_ingestion_importer.py::test_csv_import_with_auto_detected_lat_lon SKIPPED
tests/test_ingestion_importer.py::test_corrupted_geojson_raises_without_creating_anything SKIPPED
3 skipped

tests/test_ingestion_tasks.py::test_valid_geojson_marks_job_done_with_collection_and_item SKIPPED
tests/test_ingestion_tasks.py::test_corrupted_file_marks_job_error_not_zombie SKIPPED
tests/test_ingestion_tasks.py::test_missing_job_is_a_noop_not_a_crash SKIPPED
3 skipped
```

Import direct des trois nouveaux modules, sans erreur :

```
$ uv run python -c "import app.ingestion.storage; import app.ingestion.importer; import app.ingestion.tasks; print('ok')"
ok
```

## TDD Evidence

**`storage.py`**
- RED : `ModuleNotFoundError: No module named 'app.ingestion.storage'` (collection error)
- GREEN : 3 passed

**`importer.py`**
- RED : `ModuleNotFoundError: No module named 'app.ingestion.importer'` (collection error —
  survient avant même l'évaluation du marker `postgis`/skip, donc confirme l'échec
  d'import indépendamment de `CORE_TEST_DATABASE_URL`)
- GREEN (local) : 3 skipped (propre, pas d'erreur) ; import direct du module réussit

**`tasks.py`**
- RED : `ImportError: cannot import name 'tasks' from 'app.ingestion'` (collection error)
- GREEN (local) : 3 skipped (propre, pas d'erreur) ; import direct du module réussit

## Suite complète et lint-imports

```
$ uv run pytest
297 passed, 36 skipped in 13.59s
```
Baseline avant cette tâche : 294 passed, 30 skipped. Delta : +3 passed
(`test_ingestion_storage.py`), +6 skipped (`test_ingestion_importer.py` +
`test_ingestion_tasks.py`, 3 chacun) — exactement ce qu'annonce le brief,
aucune régression.

```
$ uv run lint-imports
Analyzed 61 files, 141 dependencies.
layered architecture KEPT
Contracts: 1 kept, 0 broken.
```

`docker compose config -q` a aussi été utilisé pour valider la syntaxe YAML
du service `worker` ajouté (seuls des avertissements attendus sur des
variables d'env non définies dans ce shell, pas d'erreur de syntaxe).

## Fichiers modifiés/créés

- Créés : `core/app/ingestion/storage.py`, `core/app/ingestion/importer.py`,
  `core/app/ingestion/tasks.py`, `core/tests/test_ingestion_storage.py`,
  `core/tests/test_ingestion_importer.py`, `core/tests/test_ingestion_tasks.py`
- Modifiés : `core/pyproject.toml`, `core/Dockerfile`, `core/uv.lock` (mis à
  jour automatiquement par `uv sync`, non listé explicitement dans le brief
  mais suit le même patron que le commit Task 2 qui l'avait inclus pour
  `shapely`), `docker-compose.yml`, `.env.example`

## Self-review

- Discipline YAGNI : aucune logique ajoutée au-delà du brief (pas de retry,
  pas de monitoring, pas de gestion de colonnes en collision `id`/`geom` —
  explicitement documentée comme hors périmètre v1 dans le commentaire du
  code, comme dans le brief).
- Le code de `importer.py`/`tasks.py`/`storage.py` est copié conforme au
  brief ; toutes les interfaces consommées ont été vérifiées contre le code
  source réel avant de considérer le travail terminé.
- Tests postgis confirmés SKIP propre (pas de faux vert, pas d'erreur
  masquée) ; suite complète et lint-imports pristines.
- `core/uv.lock` ajouté au commit en toute connaissance de cause (absent de
  la liste du brief mais nécessaire pour que le lock reste synchronisé avec
  `pyproject.toml`, comme fait pour Task 2/`shapely`).

## Concerns

Aucun. Le pipeline complet (storage → importer → tasks) a été implémenté
sans divergence par rapport au brief ; l'API procrastinate 3.9.0 installée
est compatible telle quelle avec le snippet fourni. Les tests postgis restent
non exécutés localement (comme anticipé et accepté par la contrainte
d'environnement) — leur exécution réelle contre PostGIS reste à faire lors
d'une prochaine session avec `CORE_TEST_DATABASE_URL` défini, ou en CI.

## Fix Report — job zombie si `get_job`/`mark_running` échoue

**Finding corrigé** (revue de code) : dans `run_ingestion_task`, le premier
bloc (`ingestion_repo.get_job`, le `if job is None: return`, `mark_running`,
et l'extraction des attributs du job) était placé dans un
`with request_scoped_session(...)` **avant** le `try/except
(IngestionParseError, Exception)` qui protège le reste de la fonction. Toute
exception levée dans ce premier bloc (erreur DB transitoire sur `get_job`/
`mark_running`, ou échec du commit implicite de `request_scoped_session` à
la sortie du `with`) se propageait donc hors de `run_ingestion_task` sans
jamais appeler `mark_error` — le job restait bloqué en `pending`, exactement
le "zombie" que le contrat de cette tâche interdit.

**Correctif** : le `try:` englobe maintenant toute la fonction dès sa
première instruction utile — le bloc `get_job`/`if job is None: return`/
`mark_running`/déballage des attributs est désormais **à l'intérieur** du
même `try` que le téléchargement S3 et `run_import`. Le `except
IngestionParseError` et le `except Exception` catch-all (avec
`logger.exception` + `mark_error`) couvrent donc maintenant aussi ce premier
bloc. Le cas `job is None` continue de faire un simple `return` (pas une
exception, comportement de no-op inchangé). L'interface publique
(`run_ingestion_task(job_id, tenant_id) -> None`, décorateur
`@app.task(queue="ingestion")`) et le chemin nominal (happy path) sont
inchangés.

**Limite résiduelle acceptée** (notée Minor par la revue, non corrigée à
dessein) : si `get_job` échoue à cause d'une panne totale de connexion DB,
l'appel à `mark_error` dans le `except` peut lui-même échouer (sa propre
session ouvre une nouvelle connexion) et cette seconde exception peut encore
s'échapper. Ce cas de défaillance en cascade (DB indisponible pour toute
opération, y compris l'écriture du statut d'erreur) est hors du périmètre de
ce correctif, qui ferme uniquement la première fuite (échec de
`get_job`/`mark_running` alors que la DB répond normalement pour l'écriture
d'erreur).

**Vérification**
- Relecture manuelle du nouveau flux de contrôle : toute ligne exécutée dans
  le corps de `run_ingestion_task`, du premier `get_job` jusqu'au
  `mark_done`, est maintenant sous le même `try`, donc toute exception qui en
  sort atteint un des deux `except` et tente `mark_error`.
- `uv run python -c "import app.ingestion.tasks"` → OK, import propre.
- `uv run pytest tests/test_ingestion_tasks.py -v` → 3 tests collectés,
  **3 SKIPPED** (marqueur `postgis`, pas d'erreur de collecte).
- `uv run pytest` (suite complète) → **297 passed, 36 skipped** — identique
  à la baseline avant ce correctif, aucune régression.
- `uv run lint-imports` → **PASS** (`Analyzed 61 files, 141 dependencies.
  layered architecture KEPT. Contracts: 1 kept, 0 broken.`).

**Commit** : `fix(core): run_ingestion_task — ne laisse plus un job zombie
si get_job/mark_running échoue (SP-6a)`.

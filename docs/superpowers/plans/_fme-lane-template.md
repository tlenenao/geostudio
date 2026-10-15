# Gabarit de voie FME — ajouter une op via un module de voie

> Plan parent : `2026-10-15-fme-fermeture-108-planned.md` (§2 = définition de « fait », à
> recopier dans chaque brief). Couture posée en vague 0 (2026-10-15).

## Principe : un fichier par voie, aucun fichier partagé à éditer

| Voie | Module | Test de voie à créer |
|---|---|---|
| A | `core/app/pipelines/ops/attrs.py` | `core/tests/test_pipeline_ops_attrs.py` |
| B | `core/app/pipelines/ops/dbio.py` | `core/tests/test_pipeline_ops_dbio.py` |
| C | `core/app/pipelines/ops/geom2.py` | `core/tests/test_pipeline_ops_geom2.py` |
| D | `core/app/pipelines/ops/cloudfiles.py` | `core/tests/test_pipeline_ops_cloudfiles.py` |
| E | `core/app/pipelines/ops/messaging.py` | `core/tests/test_pipeline_ops_messaging.py` |
| F1 | `core/app/pipelines/ops/raster2.py` | `core/tests/test_pipeline_ops_raster2.py` |
| F2 | `core/app/pipelines/ops/readers2.py` | `core/tests/test_pipeline_ops_readers2.py` |

Chaque module exporte trois noms (déjà présents, vides) :

- `CONTRACTS: list[OperationContract]` — agrégé dans `OPERATIONS` par
  `core/app/pipelines/ops/contracts.py` (`LANE_MODULES` + `_aggregate`). Une op déclarée
  deux fois (socle ou autre voie) lève `ValueError` à l'import.
- `READERS: dict[str, Callable]` / `WRITERS: dict[str, Callable]` — agrégés dans
  `core/app/pipelines/registries.py` (même garde anti-doublon).

**Ne jamais éditer** `ops/contracts.py`, `ops/schemas.py`, `registries.py`, ni les listes
figées des tests existants. Les modèles `*Params` vivent dans le module de voie.

**Cycle d'import** : un module de voie n'importe *jamais* `ops.contracts`, `runtime` ni
`registries` au niveau module (contracts.py l'importe ; runtime importe contracts).
`OperationContract` vient de `app.pipelines.ops.operation_contract`. Importer
`app.pipelines.compiler`, `app.pipelines.errors`, `app.sql_ident`, `app.pipelines.egress`
est sûr (patron de `ops/geocode.py`, `ops/filtering.py`). Un import de `runtime` reste
possible en local, dans le corps d'une fonction.

## Checklist par op

1. **Params** : `class TransformXxxParams(BaseModel)` dans le module de voie, schéma strict.
   Le **premier paragraphe du docstring** est le texte utilisateur (français) affiché par la
   palette (`ops_catalog()` → `_user_facing_description`) ; le reste = doc développeur.
   Indices de formulaire : `Field(..., json_schema_extra={"format": "collection-id"})` ou
   `{"format": "secret-name"}` (rendus par `shell/src/builder/pipeline/PipelineNodeInspector.tsx`).
2. **Contrat** : `CONTRACTS.append(OperationContract(op=..., kind=..., params_schema=...,
   engine=..., engine_license=..., ...))` (ou liste littérale). Champs utiles
   (`ops/operation_contract.py`) :
   - transform : exactement **un** de `compile=(params, *, input_view, join_view,
     input_srid[, input_columns, join_columns]) -> str` (SQL DuckDB) ou
     `execute=(conn, *, input_view, view_name, params) -> None` (matérialise `view_name`).
     Le dispatch est automatique (`compiler.compile_transform_sql`, runtime) — aucune
     branche à ajouter.
   - `needs_columns=True` : le runtime passe `input_columns`/`join_columns` à `compile`.
   - `needs_runtime_context=True` (avec `execute`) : reçoit en plus `secret_resolver=`,
     `preview=`, `input_srid=` (patron `transform.httpCall`, `ops/routing.py`).
   - `output_srid=(params, *, op, input_srid, join_srid=None) -> int` si le SRID change.
   - `accepts_secondary_input=True` : op binaire ⇒ `BINARY_OPS` ; le Params **doit** avoir
     `withCollectionId: str | None` (lu par `runtime._JOIN_PARAM_MODELS` ; ajouté
     automatiquement à `config_validation._COLLECTION_PARAM_FIELD`, contrôle `can()` inclus).
   - `enabled_when=is_xxx_enabled` : op absente du catalogue si le flag est éteint (la vraie
     garde reste au point d'exécution).
   - `is_copyleft=True` ⇒ `execution_model="sidecar"` obligatoire (vérifié à la construction).
   - `engine="shapely"` ⇒ `engine_license="BSD-3-Clause (Shapely)"` (testé globalement).
3. **Reader** : `READERS["reader.xxx"] = fn` avec la signature
   `fn(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int`
   (retourne le SRID). Modèles : `ops/wfs.py::read_wfs`, `ops/raster.py::read_raster`.
   Un reader sans entrée `READERS` fait échouer
   `test_every_reader_and_writer_op_has_a_runtime_registry_entry`.
4. **Writer** : `WRITERS["writer.xxx"] = fn`, signature générique de `run_pipeline`
   (`core/app/pipelines/runtime.py`) : `fn(session, conn, *, node, view_by_node, tenant_id,
   user, **extra) -> stat` (`extra` = `on_progress`/`should_cancel`/`run_id`). Seuls
   `writer.export`/`writer.file` ont une signature propre — ne pas en ajouter une 3ᵉ sans
   le contrôleur. Writer vers une collection : `writer.collection` reste la référence
   (garde de privilège, quarantaine, masquage) ; `config_validation._WRITE_OPS` est partagé.
5. **Expressions utilisateur** (SQL/CEL dans les params) : `runtime._validate_node_exprs`
   est une chaîne `elif` **partagée** — préférer valider dans l'op elle-même ; sinon,
   signaler au contrôleur (ajout d'une branche à la fusion, pas dans la voie).
6. **Masquage GAP-22, egress, aperçu** : cf. §2 du plan parent. Colonnes masquées :
   `runtime._masked_fields`/`hide_sensitive_columns` ; réseau : `app/pipelines/egress.py`.
7. **Shell** : rien à faire pour la palette ni l'inspecteur (pilotés par `GET /v1/pipelines/ops`
   : libellé = id d'op, description = docstring). Pas de clé i18n par op. Seul le widget
   Analyse (`shell/src/builder/widgets/analysis.tsx`, liste codée en dur de ~10 outils)
   demande une édition — uniquement si l'op doit y figurer.
8. **Matrice** : éditer **seulement les lignes de la voie** dans
   `docs/revue/matrice-couverture-fme.jsonl` (`coverage_status`, `geostudio_equivalent`
   = id d'op exact, `engine`, `engine_license`, `notes`). Ne **pas** régénérer
   `matrice-couverture-fme.md` dans la voie (le contrôleur le fait à la fusion :
   `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --write --check`).
   `--check` exige qu'une ligne `implemented` + `engine: "duckdb"` pointe une op de
   `ops_catalog()` et refuse `implemented` avec `engine` ∈ `gdal`/`pdal`/`otb`
   (`_NOT_YET_INTEGRATED_ENGINES`) — utiliser `python`/`duckdb`/`shapely` selon le moteur réel.

## Tests de comptage : comment le compteur évolue sans conflit

- `_BASE_OPERATIONS` (socle) est figé à **71** ; `OPERATIONS` = socle + somme des
  `CONTRACTS` des 7 modules (`test_operations_registry_has_71_base_entries_plus_lane_contracts`).
  Catalogue exposé en CI (flags fichier/raster éteints) : **67** + ops de voie sans `enabled_when`.
- Les listes figées (`test_operations_registry_has_exactly_the_known_ops`,
  `test_all_known_ops_are_registered`, `test_binary_ops_set_matches_catalog_flag`,
  `test_get_pipelines_ops_returns_all_exposed_ops`) comparent `set(...) - LANE_OPS` au socle :
  **ne pas y ajouter les ops de voie**.
- Chaque voie verrouille ses propres ops dans son fichier de test, p. ex. :
  `assert {c.op for c in attrs.CONTRACTS} == {"transform.xxx", ...}` + un test de catalogue
  (`"transform.xxx" in ops_catalog()`) + le test d'entrée dégénérée du §2.
- Conflits restants, résolus par le contrôleur à la fusion : `CHANGELOG.md`, les lignes
  contiguës du JSONL de matrice, et toute branche ajoutée à `runtime._validate_node_exprs`.

## Commandes de la voie (foreground, ciblées)

```bash
cd core
CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gs_test_<voie> \
  uv run pytest tests/test_pipeline_ops_<voie>.py tests/test_pipeline_ops_contracts.py \
  tests/test_pipeline_ops_schemas.py tests/test_pipeline_routes.py -q --basetemp=<scratchpad>/pyt
uv run ruff check . && uv run ruff format --check . && uv run lint-imports
```

La base `gs_test_<voie>` doit porter l'extension `postgis` (`CREATE EXTENSION postgis`),
sinon erreurs `type "geometry" does not exist` sans rapport avec la voie. `lint-imports` :
aucune entrée à ajouter tant que la voie reste dans `app.pipelines` ; tout import d'un autre
package `app.*` doit respecter le contrat de couches de `core/pyproject.toml`.

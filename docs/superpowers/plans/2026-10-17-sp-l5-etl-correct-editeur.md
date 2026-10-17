# SP-L5 « ETL correct et éditeur » — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** rendre justes les opérations ETL qui produisent aujourd'hui des chiffres faux ou tronqués en silence, ajouter les ops de qualité manquantes (validation de géométrie, mesures géodésiques, jointure spatiale à attributs), fiabiliser planification/déclencheurs, et rendre l'éditeur de pipeline utilisable (aperçu, drop, nœud fautif, collection cible, lineage visible).

**Architecture :** corrections au point unique de chaque défaut — le compilateur `core/app/pipelines/compiler.py` (SQL par nœud), les ops `execute` (`ops/execute.py`), le runtime (`runtime.py` : matérialisation, erreurs), les readers externes, `collection_writer.py`, le balayage `jobs.py`/`repository.py`. Les nouvelles ops vivent dans un nouveau module de voie `ops/quality.py` agrégé par `LANE_MODULES` (patron FME, aucun câblage shell par op). Deux migrations additives (colonnes nullable) sur `pipeline_runs`. Côté shell : corrections locales de `PipelineBuilderPage`/`PipelineCanvas`/`PipelineNodeInspector`/`PipelinePreviewPanel`, un panneau `LineagePanel` branché sur les routes lineage existantes.

**Tech Stack :** Python 3.12 / FastAPI / SQLAlchemy / Alembic / DuckDB 1.5.5 + spatial / shapely 2 / croniter / zoneinfo ; React 18 / @xyflow/react / React Query / Vitest / Playwright.

**AUD couverts :** AUD-008, AUD-009, AUD-021, AUD-022, AUD-077, AUD-078, AUD-079, AUD-080, AUD-082, AUD-084, AUD-086 (partiel), AUD-087, AUD-088, AUD-130 (partiel) ; addendum : AUD-162 (aperçu sidecar), AUD-173 (exemple `external-widget`).

**Reportés (raison) :**
- AUD-021 *overlayer n-aire* (AreaOnAreaOverlayer) — dépasse le lot (nouvel algorithme topologique) ; la jointure spatiale à attributs, besoin bloquant (parcelle × zonage), est livrée.
- AUD-080 *géométrie dans la quarantaine `__rejected`* — conflit de sécurité GAP-27 (les rejets ne passent pas par la RLS de limites géographiques, la géométrie y est volontairement omise, cf. commentaire de `write_rows`) : décision produit.
- AUD-086 *lineage au niveau colonne* — dépasse le lot (nécessite une analyse de flux par op) ; la surface item est livrée.
- AUD-130 *groupBy/par entité, alertes spatiales, nouveaux canaux, plancher 5 min* — décisions produit (D-décisions non tranchées) ; seul le défaut « alerte partagée à un groupe non notifiée au groupe » est corrigé.
- AUD-079 *déduplication* — déjà couverte par `transform.matcher` (écart consigné ci-dessous), aucune op nouvelle.
- AUD-022 *données d'exemple livrées avec les gabarits* — décision produit (quelles données, quelle licence) ; le liage gabarit → collection réelle est livré.

**Dépendances :** SP-L0 livré (AUD-005/006/007 : `_compile_detect_changes` sentinelle + schéma « après », tampons aeqd) — ce plan part de ce code. SP-L1a livré (`0082_pipeline_run_heartbeat`, `mark_failed_if_queued`).

**Migrations réservées :** plage **0087-0090**. Utilisées : `0087_pipeline_run_idempotency_key` (Task 5), `0088_pipeline_run_failed_node` (Task 6). `down_revision` = tête réelle au moment de l'exécution (`cd core && uv run alembic heads`) — 0082 à la rédaction, d'autres lots (0083-0086) peuvent l'avoir avancée : chaîner 0088 sur 0087.

**Fichiers / zones touchés (détection de collisions) :**
- cœur : `core/app/pipelines/{compiler,runtime,routes,service,repository,jobs,models,collection_writer,errors}.py`, `core/app/pipelines/ops/{schemas,contracts,execute,filtering,cloudfiles,wfs,quality(nouveau)}.py`, `core/app/pipelines/sidecar/{app,tracker}.py`, `core/app/configs/{schemas,pipeline_validation,builder_templates}.py`, `core/app/webhooks/triggers.py`, `core/app/alerts/jobs.py`, `core/app/sharing/repository.py`, `core/app/mcp/tools/configs.py`, `core/alembic/versions/0087_*`, `0088_*`, `core/openapi.json`.
- shell : `shell/src/pages/PipelineBuilderPage.tsx`, `shell/src/pages/ItemDetailPage.tsx`, `shell/src/builder/pipeline/{PipelineCanvas,PipelineNodeInspector,PipelinePreviewPanel,PipelineRunPanel,graphOps}.tsx|ts`, `shell/src/builder/pipeline/LineagePanel.tsx` (nouveau), `shell/src/api/{types.ts,domains/pipelines.ts,domains/pipelines.hooks.ts,domains/items.ts,domains/impact.ts}`, `shell/src/desktop/DesktopItemClient.ts`, `shell/src/lib/useUrlSyncedState.ts`, `shell/src/shell/NewItemButton.tsx`, `shell/src/i18n/domains/automation.ts`, `shell/src/api/generated/core-schema.d.ts`.
- divers : `examples/external-widget/manifest.json`, `docs/guides/2026-07-13-ecrire-un-widget-web-component.md`.

## Global Constraints

- Régénérer OpenAPI + types TS à chaque route/modèle modifié : `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types`.
- Toute surface nouvelle (route REST, outil MCP, route shell) est ajoutée à `docs/revue/inventaire-fonctionnalites.jsonl` **par le contrôleur à la clôture** (ce plan n'écrit pas dans `docs/revue/*`) : la Task 9 liste les lignes à ajouter ; `core/tests/test_feature_inventory.py` échouera tant qu'elles manquent — c'est attendu et signalé.
- Migrations Alembic testées sur base **non vide**, dans les deux sens (piège n°8), sur une base jetable dédiée créée par la fixture `throwaway_database_url` (patron `core/tests/test_migration_0082_pipeline_heartbeat.py`). DSN de test : `postgresql+psycopg://` (jamais `+psycopg2`). Plage réservée 0087-0090 ; `down_revision` = tête réelle à l'exécution.
- Conteneur `postgis-test` partagé non tracké par Alembic : après 0087/0088, `ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS idempotency_key varchar(128); ALTER TABLE pipeline_runs ADD COLUMN IF NOT EXISTS failed_node_id varchar(64);` sur la base de test partagée, sinon `UndefinedColumn` sans rapport.
- Commande pytest du lot (base jetable dédiée, sessions concurrentes) : `cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/geostudio_test_l5 uv run pytest <fichier> -v` (créer `geostudio_test_l5` une fois : `docker exec postgis-test psql -U postgres -c 'CREATE DATABASE geostudio_test_l5' && docker exec postgis-test psql -U postgres -d geostudio_test_l5 -c 'CREATE EXTENSION postgis; CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;'`). Vérifier le port réel du conteneur (`docker port postgis-test`) avant.
- Jumelles (piège n°14) listées en Task 9 avant de clore : tout correctif sur une surface est reporté sur ses jumelles nommées dans chaque tâche.
- Commits conventional en français, un sujet, trailer exact : `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Vérifier `git show --stat` après chaque commit (pas de fichier étranger).
- `docker-compose.yml` / `.env.example` / Helm : aucune modification prévue ; si nécessaire, modification localisée uniquement.
- Interdiction de toucher `CLAUDE.md`, `docs/revue/*`, `docs/superpowers/2026-08-27-historique-execution-continu.md` (clôture documentaire par le contrôleur).
- Messages utilisateur en français (i18n shell : clés dans `shell/src/i18n/domains/automation.ts`, `npm run lint` bloque le français en dur) ; identifiants en anglais.
- DuckDB : `ST_Transform(..., always_xy := true)` est la convention du dépôt (4ᵉ argument positionnel `true`).

## Faits vérifiés / écarts à l'audit

Vérifiés contre le code de `dev` (8b09c207) et un DuckDB 1.5.5 réel :

1. **AUD-008** : la clé est dans `shell/src/api/domains/pipelines.hooks.ts:69` (pas `shell/src/pipelines/`). `queryKey: ["pipeline-preview", pipelineId, nodeId, draft]` — le brouillon entier, positions `x/y` et notes comprises : chaque frame de drag relance l'aperçu.
2. **AUD-009** : la route cœur `POST /v1/pipelines/{id}/preview` honore déjà un brouillon (`routes.py:272-296`) ; le défaut est que l'éditeur ne monte le panneau que si `pk !== null` (`PipelineBuilderPage.tsx:543`) — un pipeline jamais enregistré n'a pas d'item. « Enregistrement bloqué tant que le graphe est invalide » (`disabled={!valid}`, l. 603) est un choix assumé (validation serveur stricte à l'écriture, P29) : **non modifié**, l'aperçu sans enregistrement lève le besoin.
3. **AUD-087 « Exécuter lance la version enregistrée »** : exact (`runPipeline(pk)` n'envoie pas le brouillon) — on n'exécute jamais un brouillon non enregistré (audit/rejouabilité) ; correctif = avertissement explicite quand il y a des modifications non enregistrées.
4. **AUD-087 « erreur d'aperçu jetée »** : `PipelinePreviewPanel.tsx:76-81` affiche un message générique et jette `ApiError.detail`.
5. **AUD-087 « undo désynchronise les champs »** : `StringListField` utilise `defaultValue` (jamais resynchronisé), `JsonField` initialise son état une seule fois — les autres champs sont contrôlés et suivent `node.params`.
6. **AUD-088 « titre perdu »** : `PipelineNewRoute` lit `location.state.title` ; `useUrlSyncedState` (`setSearchParams(..., {replace:true})`) remplace l'entrée d'historique **sans** `state` dès le premier changement d'onglet → titre perdu.
7. **AUD-088 « erreur SQL 500 sur derive »** : `_validate_node_exprs` (`runtime.py:895`) est appelé **hors** du `try duckdb.Error` et lève `SqlSandboxError`, non mappée par la route d'aperçu (seule `PipelineRuntimeError` → 400).
8. **AUD-077 GROUP BY ALL** : `_compile_count_within` et `_compile_merge_children` regroupent sur toutes les colonnes de `t` → deux lignes d'entrée identiques fusionnent (compte doublé, une ligne perdue). `spatialRelator` (`attrs.py:375`) utilise déjà le bon patron `__gs_rid` : on le reprend.
9. **AUD-077 join** : `SELECT * … USING (on)` duplique `geometry` (DuckDB renomme la seconde en `geometry_1`) et toute colonne homonyme (`*_1`) — le writer refuse ensuite `unknown_property` sur **chaque** ligne.
10. **AUD-077 NULL** : `_read_geometry_rows` écarte les géométries NULL (REV-196). Pour `densify` (op ligne à ligne, n→n) c'est une perte silencieuse. Pour `_rowwise` de `geom2.py`, la docstring fait de « 0 sortie = ligne écartée » le contrat : **non modifié** (écart à l'audit : seules les ops n→n sont concernées ; `triangulate`/`minimumBoundingCircle` agrègent et n'ont pas de sens sur NULL).
11. **AUD-077 reproject** : `targetCrs` accepte `^[A-Za-z]+:\d+$` (ex. `ESRI:102110`) mais `_output_srid_reproject` ne garde que le nombre → SRID faux en aval ; et un `input_srid` 0/None fait `'EPSG:0'`/assert. Correctif : `^EPSG:\d+$` + refus explicite d'un SRID d'entrée inconnu.
12. **AUD-078 « TEMP VIEW recomptée »** : chaque nœud compilé est une VIEW, `_view_row_count` la ré-évalue, puis le nœud suivant ré-évalue toute la chaîne (coût quadratique en profondeur). Correctif : en run, matérialiser en `TEMP TABLE` ; en aperçu, garder la VIEW (LIMIT 50 en bout) et ne pas compter.
13. **AUD-078 neighborFinder** : dans `ops/filtering.py` (pas `reliquats.py`) ; `maxDistance=None` = produit cartésien. Correctif : plafond d'entrée explicite.
14. **AUD-082** : `cloudfiles.read_arcgisonline` s'arrête à `min(maxFeatures, _max_rows())` même si `exceededTransferLimit` → troncature silencieuse ; `wfs.read_wfs` envoie `count` sans pagination ni contrôle. Lecteurs SQL : `_IncrementalReader` (schemas.py:34) est la base des 8 readers connecteurs ; aucune colonne géométrie n'est décodée, la sortie déclare 4326 sans géométrie.
15. **AUD-080 clé NULL** : avec la sentinelle de L0, une clé NULL des deux côtés sort `inserted` + `deleted` (jamais rapprochée) — sémantiquement faux. Doublon de clé : le FULL JOIN multiplie les lignes en silence.
16. **AUD-080 / AUD-088 F14** : `write_rows` ne met `feature_count` à jour que pour upsert/update/delete — `append`/`replace` le laissent périmé (catalogue faux).
17. **AUD-084** : cron interprété en UTC (`croniter(policy.cron, created_at)`), aucun fuseau ; aucun circuit-breaker ; un propriétaire anonymisé (`users.erased_at`) fait échouer `_acting_user` à chaque tick ; `/trigger` en 409 sans `Retry-After` ni idempotence ; `webhooks/triggers.py` appelle `run_pipeline_service` sans aucun paramètre (clé/etag perdus).
18. **AUD-084 « notification à chaque succès »** (bruit) : `jobs.py:408` notifie chaque succès d'un pipeline planifié toutes les 5 min.
19. **AUD-130** : `alerts/jobs.py:575-592` ne notifie in-app que `owner_id`.
20. **AUD-086** : routes `GET /v1/items/{id}/lineage|impact` existent (`app/lineage/routes.py`) ; aucun appel shell à `/lineage` (seul `useImpact` dans `ImpactConfirmDialog`).
21. **AUD-022** : `shell/src/builder/templates.data.json` référence des slugs (`incidents`, `communes`…) qui n'existent dans aucun tenant ; `createConfigItem({templateId})` instancie le gabarit tel quel ; MCP `create_item(template=…)` (`mcp/tools/configs.py:232-248`) appelle `build_config_from_template(template_id)` — jumelle.
22. **AUD-162** : `sidecar/app.py:135-153` ignore le corps. **AUD-173** : `examples/external-widget/manifest.json` `"moduleUrl": "widget.js"` refusé par `ModuleUrl` `^https://[^\s]+$`.
23. **DuckDB 1.5.5 vérifié** : `INSERT INTO t BY NAME SELECT …` OK ; `error('msg')` lève `InvalidInputException` à l'évaluation ; `ST_Area_Spheroid(ST_FlipCoordinates(g4326))` = 813 660,8 m² pour un carré de 0,01° à 49°N ; `ST_Length_Spheroid`/`ST_Perimeter_Spheroid` idem ; pas de `ST_IsValidReason` → `shapely.validation.explain_validity` en UDF.
24. `_node_error` : la regex `^\w+ Error:\s*` ne retire pas `Invalid Input Error:` (deux mots) → corrigée en `^[\w ]+ Error:\s*`.

---

### Task 1 : Compilateur juste — join, comptages sans fusion, reproject strict, NULL conservés (AUD-077)

**Files :**
- Modify : `core/app/pipelines/ops/schemas.py` (`TransformJoinParams` l.60, `TransformReprojectParams` l.132, `TransformCountWithinParams` l.142)
- Modify : `core/app/pipelines/compiler.py` (`_compile_join` l.157, `_compile_reproject` l.208, `_compile_count_within` l.244, `_compile_merge_children` l.739)
- Modify : `core/app/pipelines/ops/contracts.py` (`transform.join` l.157, `transform.countWithin` l.193)
- Modify : `core/app/pipelines/ops/execute.py` (`_execute_densify` l.100)
- Test : `core/tests/test_pipeline_compiler_l5.py` (nouveau), `core/tests/test_pipeline_ops_execute.py` (l.99-117)

**Interfaces :**
- Consumes : `_qi` (`app.sql_ident.quote_ident_duckdb`), `PipelineRuntimeError` (`app.pipelines.errors`), `OutputColumn` (`app.pipelines.ops.operation_contract`).
- Produces : `TransformJoinParams.rightPrefix: str = "right_"` ; `_compile_join(params, *, input_view, join_view, input_srid, input_columns, join_columns)` ; `_compile_count_within(..., input_columns, join_columns)` ; `TransformCountWithinParams.countColumn: OutputColumn` ; `_reinsert_null_geometry(conn, *, input_view: str, view_name: str) -> None` dans `ops/execute.py`.

- [ ] **Step 1 : écrire les tests qui échouent**

`core/tests/test_pipeline_compiler_l5.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 1 (AUD-077) : join sans colonnes dupliquées, comptages sans fusion de lignes
identiques, reproject strict. Exécuté contre un DuckDB réel (compilation + exécution)."""

import duckdb
import pytest

from app.pipelines import compiler
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.schemas import TransformReprojectParams


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def _cols(conn, view):
    return [d[0] for d in conn.execute(f'DESCRIBE "{view}"').fetchall()]


def _run(conn, op, params, *, input_view="a", join_view="b"):
    input_columns = _cols(conn, input_view)
    join_columns = _cols(conn, join_view) if join_view else None
    sql = compiler.compile_transform_sql(
        op,
        params,
        input_view=input_view,
        join_view=join_view,
        input_srid=4326,
        input_columns=input_columns,
        join_columns=join_columns,
    )
    return conn.execute(sql)


def test_join_keeps_one_geometry_and_prefixes_clashing_columns(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 1 AS id, 'A' AS name, ST_Point(0,0) AS geometry "
        "UNION ALL SELECT 2, 'B', ST_Point(1,1)"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 1 AS id, 'zone1' AS name, 10 AS pop, ST_Point(5,5) AS geometry"
    )
    rel = _run(conn, "transform.join", {"on": "id", "how": "left"})
    cols = [d[0] for d in rel.description]
    assert cols == ["id", "name", "geometry", "right_name", "pop"]
    rows = sorted(rel.fetchall(), key=lambda r: r[0])
    assert rows[0][3] == "zone1" and rows[0][4] == 10
    assert rows[1][3] is None


def test_join_refuses_a_missing_key(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS id, ST_Point(0,0) AS geometry")
    conn.execute("CREATE TABLE b AS SELECT 1 AS other, ST_Point(0,0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="id"):
        _run(conn, "transform.join", {"on": "id"})


def test_count_within_does_not_merge_identical_input_rows(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'x' AS name, ST_GeomFromText("
        "'POLYGON((0 0,2 0,2 2,0 2,0 0))') AS geometry FROM range(2)"
    )
    conn.execute("CREATE TABLE b AS SELECT ST_Point(1,1) AS geometry")
    rows = _run(conn, "transform.countWithin", {"countColumn": "n"}).fetchall()
    assert len(rows) == 2
    assert [r[-1] for r in rows] == [1, 1]


def test_count_within_refuses_an_existing_output_column(conn):
    conn.execute("CREATE TABLE a AS SELECT 3 AS n, ST_Point(0,0) AS geometry")
    conn.execute("CREATE TABLE b AS SELECT ST_Point(0,0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="n"):
        _run(conn, "transform.countWithin", {"countColumn": "n"})


def test_merge_children_does_not_merge_identical_parents(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS pid, ST_Point(0,0) AS geometry FROM range(2)")
    conn.execute("CREATE TABLE b AS SELECT 1 AS parent, 'c' AS label")
    rows = _run(
        conn,
        "transform.mergeChildren",
        {"parentOn": "pid", "childOn": "parent", "childrenColumn": "kids"},
    ).fetchall()
    assert len(rows) == 2


def test_reproject_accepts_only_epsg_codes():
    TransformReprojectParams.model_validate({"targetCrs": "EPSG:2154"})
    with pytest.raises(ValueError):
        TransformReprojectParams.model_validate({"targetCrs": "ESRI:102110"})


def test_reproject_refuses_an_unknown_input_srid():
    with pytest.raises(PipelineRuntimeError, match="setSrid"):
        compiler.compile_transform_sql(
            "transform.reproject",
            {"targetCrs": "EPSG:2154"},
            input_view="a",
            join_view=None,
            input_srid=0,
        )
```

Dans `core/tests/test_pipeline_ops_execute.py`, remplacer le paramétrage de `test_null_geometry_rows_are_dropped` (l.99-117) pour retirer `transform.densify` de la liste (seules `transform.minimumBoundingCircle` et `transform.triangulate` restent), puis ajouter à la fin du fichier :

```python
def test_densify_keeps_rows_with_null_geometry(conn):
    """AUD-077 : densify est n→n, une géométrie NULL ne fait pas disparaître la ligne."""
    from app.pipelines.ops.execute import _execute_densify

    conn.execute(
        "CREATE TABLE src AS SELECT 1 AS id, ST_GeomFromText('LINESTRING(0 0, 10 0)') AS geometry "
        "UNION ALL SELECT 2, NULL::GEOMETRY"
    )
    _execute_densify(conn, input_view="src", view_name="out", params={"maxSegmentLength": 5})
    rows = conn.execute("SELECT id, geometry IS NULL FROM out ORDER BY id").fetchall()
    assert rows == [(1, False), (2, True)]
```

- [ ] **Step 2 : vérifier l'échec**

Run : `cd core && uv run pytest tests/test_pipeline_compiler_l5.py tests/test_pipeline_ops_execute.py -v`
Expected : FAIL (colonnes `geometry_1`/`name_1`, 1 ligne au lieu de 2, `ESRI:` accepté, densify à 1 ligne).

- [ ] **Step 3 : paramètres**

Dans `core/app/pipelines/ops/schemas.py`, ajouter l'import en tête (`OutputColumn` vit dans `operation_contract.py`, sans dépendance vers `schemas.py`) :

```python
from app.pipelines.ops.operation_contract import OutputColumn
```

Remplacer `TransformJoinParams`, `TransformReprojectParams`, `TransformCountWithinParams` :

```python
class TransformJoinParams(BaseModel):
    """Jointure attributaire sur `on` (même nom des deux côtés). La sortie garde toutes les
    colonnes de l'entrée principale (dont sa géométrie) puis les colonnes de la seconde
    entrée hors clé et hors géométrie ; une colonne déjà présente à gauche est préfixée par
    `rightPrefix`."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"
    rightPrefix: str = Field("right_", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")


class TransformReprojectParams(BaseModel):
    targetCrs: str = Field(..., pattern=r"^EPSG:\d+$")


class TransformCountWithinParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    countColumn: OutputColumn = "count"
    predicate: Literal["intersects", "contains"] = "intersects"
```

Vérifier qu'aucun import circulaire n'apparaît : `cd core && uv run python -c "import app.pipelines.ops.contracts"` → aucune sortie.

- [ ] **Step 4 : compilateur**

Dans `core/app/pipelines/compiler.py`, ajouter l'import `from app.pipelines.errors import PipelineRuntimeError` (module feuille, aucun cycle) et la constante `_RID = '"__gs_rid"'` sous les imports. Remplacer les quatre fonctions :

```python
def _compile_join(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformJoinParams.model_validate(params)
    assert join_view is not None, "transform.join requires join_view"
    assert input_columns is not None and join_columns is not None
    for side, cols in (("principale", input_columns), ("secondaire", join_columns)):
        if p.on not in cols:
            raise PipelineRuntimeError(
                f"transform.join : clé {p.on!r} absente de l'entrée {side} (colonnes : {cols})"
            )
    right = [c for c in join_columns if c not in (p.on, "geometry")]
    out_names = [f"{p.rightPrefix}{c}" if c in input_columns else c for c in right]
    clash = [n for n in out_names if n in input_columns]
    if clash:
        raise PipelineRuntimeError(
            f"transform.join : colonne(s) de sortie déjà présente(s) : {clash} — changer rightPrefix"
        )
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    right_sel = "".join(
        f", o.{_qi(c)} AS {_qi(n)}" for c, n in zip(right, out_names, strict=True)
    )
    return (
        f"SELECT t.*{right_sel} FROM {_qi(input_view)} t {join_kw} {_qi(join_view)} o "
        f"ON t.{_qi(p.on)} = o.{_qi(p.on)}"
    )


def _compile_reproject(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformReprojectParams.model_validate(params)
    if not input_srid:
        raise PipelineRuntimeError(
            "transform.reproject : SRID d'entrée inconnu — déclarer le SRID source avec "
            "transform.setSrid avant de reprojeter"
        )
    return (
        f"SELECT * EXCLUDE (geometry), "
        f"ST_Transform(geometry, 'EPSG:{input_srid}', '{p.targetCrs}', true) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_count_within(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformCountWithinParams.model_validate(params)
    assert join_view is not None, "transform.countWithin requires join_view"
    clash = [n for n in (p.countColumn, "__gs_rid") if n in (input_columns or [])]
    if clash:
        raise PipelineRuntimeError(
            f"transform.countWithin : colonne(s) de sortie déjà présente(s) en entrée : {clash}"
        )
    if p.predicate == "intersects":
        predicate_expr = "ST_Intersects(t.geometry, o.geometry)"
    else:  # contains
        predicate_expr = "ST_Contains(o.geometry, t.geometry)"
    # Regroupement par identifiant de ligne, jamais GROUP BY ALL : deux lignes d'entrée
    # identiques restent deux lignes (AUD-077, patron de transform.spatialRelator).
    return (
        f"WITH b AS (SELECT *, row_number() OVER () AS {_RID} FROM {_qi(input_view)}), "
        f"c AS (SELECT t.{_RID} AS rid, COUNT(o.geometry) AS n FROM b t "
        f"LEFT JOIN {_qi(join_view)} o ON {predicate_expr} GROUP BY t.{_RID}) "
        f"SELECT b.* EXCLUDE ({_RID}), c.n AS {_qi(p.countColumn)} "
        f"FROM b JOIN c ON c.rid = b.{_RID}"
    )


def _compile_merge_children(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformMergeChildrenParams.model_validate(params)
    assert join_view is not None, "transform.mergeChildren requires join_view"
    assert join_columns is not None
    if p.childrenColumn in (input_columns or []):
        raise PipelineRuntimeError(
            f"transform.mergeChildren : colonne {p.childrenColumn!r} déjà présente en entrée"
        )
    child_cols = [c for c in join_columns if c != p.childOn]
    struct_fields = ", ".join(f"{_qi(c)} := o.{_qi(c)}" for c in child_cols)
    # FILTER + COALESCE(..., []) : un parent sans enfant reçoit [] (pas [{...: NULL}]).
    children_expr = (
        f"COALESCE(list(struct_pack({struct_fields})) "
        f"FILTER (WHERE o.{_qi(p.childOn)} IS NOT NULL), [])"
    )
    # Regroupement par identifiant de ligne (AUD-077) : deux parents identiques restent deux.
    return (
        f"WITH b AS (SELECT *, row_number() OVER () AS {_RID} FROM {_qi(input_view)}), "
        f"c AS (SELECT t.{_RID} AS rid, {children_expr} AS kids FROM b t "
        f"LEFT JOIN {_qi(join_view)} o ON t.{_qi(p.parentOn)} = o.{_qi(p.childOn)} "
        f"GROUP BY t.{_RID}) "
        f"SELECT b.* EXCLUDE ({_RID}), c.kids AS {_qi(p.childrenColumn)} "
        f"FROM b JOIN c ON c.rid = b.{_RID}"
    )
```

Vérifier que `compile_transform_sql` transmet bien `input_columns`/`join_columns` à toute op `needs_columns` (c'est le cas pour detectChanges/mergeChildren : même chemin).

- [ ] **Step 5 : contrats**

Dans `core/app/pipelines/ops/contracts.py`, ajouter `needs_columns=True` à `transform.join` (l.157) et à `transform.countWithin` (l.193). Rien d'autre (la géométrie de droite est écartée par join : pas de `output_srid`).

- [ ] **Step 6 : densify conserve les lignes NULL**

Dans `core/app/pipelines/ops/execute.py`, ajouter sous `_write_geometry_rows` :

```python
def _reinsert_null_geometry(conn, *, input_view: str, view_name: str) -> None:
    """Op n→n : réinsère les lignes à géométrie NULL écartées par `_read_geometry_rows`
    (AUD-077) — perte silencieuse sinon."""
    conn.execute(
        f"INSERT INTO {_qi(view_name)} BY NAME "
        f"SELECT * FROM {_qi(input_view)} WHERE geometry IS NULL"
    )
```

Et dans `_execute_densify`, après `_write_geometry_rows(conn, df, view_name=view_name)` :

```python
    _reinsert_null_geometry(conn, input_view=input_view, view_name=view_name)
```

Si l'entrée ne contient que des NULL, `df` est vide et la table créée a une colonne `geometry` non typée GEOMETRY : le test `test_densify_keeps_rows_with_null_geometry` couvre le cas mixte ; ajouter un cas « que des NULL » au test si l'INSERT échoue en type (`geometry` créée en BLOB) — dans ce cas créer la table vide par `CREATE TEMP TABLE view AS SELECT * FROM input LIMIT 0` avant l'insertion (écart à consigner dans le rapport).

- [ ] **Step 7 : vérifier**

Run : `cd core && uv run pytest tests/test_pipeline_compiler_l5.py tests/test_pipeline_ops_execute.py tests/test_pipeline_compiler.py tests/test_pipeline_ops_contracts.py -v`
Expected : PASS. Puis la suite pipelines complète : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests -k "pipeline or analysis" -q` → vert. Les tests existants qui attendaient `SELECT * … USING` ou `GROUP BY ALL` en texte doivent être mis à jour pour asserter le comportement (lignes/colonnes), pas le SQL.

- [ ] **Step 8 : commit**

```bash
git add core/app/pipelines/compiler.py core/app/pipelines/ops/schemas.py core/app/pipelines/ops/contracts.py core/app/pipelines/ops/execute.py core/tests/test_pipeline_compiler_l5.py core/tests/test_pipeline_ops_execute.py
git commit -m "fix(core): join sans colonnes dupliquées, comptages sans fusion de lignes, reproject strict (AUD-077)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : `transform.spatialRelator` (déjà correct), `analysis.py` outil `countWithin` (même op — vérifier `test_pipeline_analysis*.py`), schéma JSON du catalogue (`GET /pipelines/ops`, régénéré en Task 9).

---

### Task 2 : Bornes et troncatures — lecture géométrique plafonnée, TEMP TABLE en run, neighborFinder borné, readers sans troncature silencieuse, géométrie des lecteurs SQL (AUD-078, AUD-082)

**Files :**
- Modify : `core/app/pipelines/ops/execute.py` (`_read_geometry_rows` l.19)
- Modify : `core/app/pipelines/ops/filtering.py` (`compile_neighbor_finder` l.73-93)
- Modify : `core/app/pipelines/runtime.py` (`_execute_transform_chain` l.940-952, `_prepare` l.746-758)
- Modify : `core/app/pipelines/ops/cloudfiles.py` (`read_arcgisonline` l.591-679)
- Modify : `core/app/pipelines/ops/wfs.py` (`read_wfs` l.74-140)
- Modify : `core/app/pipelines/ops/schemas.py` (`_IncrementalReader` l.34)
- Test : `core/tests/test_pipeline_bounds_l5.py` (nouveau)

**Interfaces :**
- Consumes : `PipelineRuntimeError`, `_qi`.
- Produces : `MAX_GEOMETRY_ROWS = 1_000_000`, `MAX_GEOMETRY_VERTICES = 20_000_000` (execute.py) ; `NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE = 5_000` (filtering.py) ; `_IncrementalReader.geometryColumn: str | None`, `.geometryFormat: Literal["wkt","wkb_hex","geojson"]`, `.geometrySrid: int` ; `_decode_connector_geometry(conn, view_name: str, params: dict) -> int | None` (runtime.py).

- [ ] **Step 1 : tests qui échouent**

`core/tests/test_pipeline_bounds_l5.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 2 (AUD-078/082) : bornes d'entrée des ops Python, neighborFinder borné,
troncatures signalées, géométrie des lecteurs SQL décodée."""

import duckdb
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import execute, filtering


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def test_read_geometry_rows_refuses_too_many_rows(conn, monkeypatch):
    monkeypatch.setattr(execute, "MAX_GEOMETRY_ROWS", 3)
    conn.execute("CREATE TABLE src AS SELECT ST_Point(i, i) AS geometry FROM range(5) t(i)")
    with pytest.raises(PipelineRuntimeError, match="5"):
        execute._read_geometry_rows(conn, "src")


def test_read_geometry_rows_refuses_too_many_vertices(conn, monkeypatch):
    monkeypatch.setattr(execute, "MAX_GEOMETRY_VERTICES", 10)
    conn.execute(
        "CREATE TABLE src AS SELECT ST_GeomFromText("
        "'LINESTRING(0 0,1 1,2 2,3 3,4 4,5 5,6 6,7 7,8 8,9 9,10 10,11 11)') AS geometry"
    )
    with pytest.raises(PipelineRuntimeError, match="sommets"):
        execute._read_geometry_rows(conn, "src")


def test_neighbor_finder_without_distance_refuses_large_inputs(conn, monkeypatch):
    monkeypatch.setattr(filtering, "NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE", 2)
    conn.execute("CREATE TABLE a AS SELECT ST_Point(i, i) AS geometry FROM range(3) t(i)")
    conn.execute("CREATE TABLE b AS SELECT ST_Point(0, 0) AS geometry")
    with pytest.raises(PipelineRuntimeError, match="maxDistance"):
        filtering.execute_neighbor_finder(
            conn, input_view="a", view_name="out", params={}, join_view="b"
        )


def test_connector_geometry_is_decoded_from_wkt(conn):
    from app.pipelines.runtime import _decode_connector_geometry

    conn.execute("CREATE TEMP TABLE v AS SELECT 1 AS id, 'POINT(2 48)' AS wkt")
    srid = _decode_connector_geometry(
        conn, "v", {"geometryColumn": "wkt", "geometryFormat": "wkt", "geometrySrid": 4326}
    )
    assert srid == 4326
    cols = [d[0] for d in conn.execute("DESCRIBE v").fetchall()]
    assert cols == ["id", "geometry"]
    assert conn.execute("SELECT ST_X(geometry) FROM v").fetchone()[0] == 2


def test_connector_without_geometry_column_is_untouched(conn):
    from app.pipelines.runtime import _decode_connector_geometry

    conn.execute("CREATE TEMP TABLE v AS SELECT 1 AS id")
    assert _decode_connector_geometry(conn, "v", {}) is None
```

Ajouter dans le fichier de test existant d'arcgisonline (`core/tests/test_pipeline_ops_cloudfiles*.py` — `grep -l read_arcgisonline core/tests/*.py`) un test qui simule une réponse `{"features":[…2 lignes…], "exceededTransferLimit": true}` avec `maxFeatures=2` et attend `PipelineRuntimeError` contenant « tronqué » ; même chose dans le test WFS existant (`grep -l read_wfs core/tests/*.py`) : réponse de `maxFeatures+1` entités → `PipelineRuntimeError` « tronqué ». Réutiliser le transport factice déjà utilisé par ces fichiers (fixture/`monkeypatch` existants — lire le fichier avant d'écrire).

Note : `neighborFinder` devient une op `execute` (Step 4) ; vérifier l'emplacement actuel de son contrat (`contracts.py` ~l.655, `compile=_filtering.compile_neighbor_finder`) et de ses tests (`grep -ln neighborFinder core/tests`).

- [ ] **Step 2 : vérifier l'échec**

Run : `cd core && uv run pytest tests/test_pipeline_bounds_l5.py -v`
Expected : FAIL (`AttributeError: MAX_GEOMETRY_ROWS`, `execute_neighbor_finder`, `_decode_connector_geometry`).

- [ ] **Step 3 : plafonds de lecture géométrique**

Dans `core/app/pipelines/ops/execute.py`, au-dessus de `_read_geometry_rows` :

```python
# AUD-078 : plafond commun de toute op Python (shapely/pandas) — la lecture matérialise
# tout en mémoire. Bornes larges (les ops topologiques gardent leur _Budget plus serré).
MAX_GEOMETRY_ROWS = 1_000_000
MAX_GEOMETRY_VERTICES = 20_000_000
```

Et dans `_read_geometry_rows`, après le contrôle de la colonne `geometry` et avant le `fetchdf()` :

```python
    n, vertices = conn.execute(
        f"SELECT count(*), coalesce(sum(ST_NPoints(geometry)), 0) "
        f"FROM {_qi(input_view)} WHERE geometry IS NOT NULL"
    ).fetchone()
    if n > MAX_GEOMETRY_ROWS:
        raise PipelineRuntimeError(
            f"entrée trop volumineuse pour cette opération : {n} lignes (max {MAX_GEOMETRY_ROWS})"
        )
    if vertices > MAX_GEOMETRY_VERTICES:
        raise PipelineRuntimeError(
            f"entrée trop volumineuse pour cette opération : {vertices} sommets "
            f"(max {MAX_GEOMETRY_VERTICES})"
        )
```

- [ ] **Step 4 : neighborFinder borné**

Dans `core/app/pipelines/ops/filtering.py`, garder `compile_neighbor_finder` tel quel et ajouter :

```python
# AUD-078 : sans maxDistance la requête est un produit cartésien — plafond explicite.
NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE = 5_000


def execute_neighbor_finder(
    conn, *, input_view: str, view_name: str, params: dict, join_view: str | None = None
) -> None:
    p = TransformNeighborFinderParams.model_validate(params)
    if p.maxDistance is None:
        (n,) = conn.execute(f"SELECT count(*) FROM {_qi(input_view)}").fetchone()
        if n > NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE:
            raise PipelineRuntimeError(
                f"transform.neighborFinder : {n} lignes sans maxDistance "
                f"(max {NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE}) — renseigner maxDistance"
            )
    sql = compile_neighbor_finder(params, input_view=input_view, join_view=join_view)
    conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
```

Problème : le runtime n'appelle `execute` qu'avec `(conn, input_view, view_name, params, **extra)` — pas de `join_view`. Plutôt que d'élargir le contrat `execute`, garder `compile=` et faire le contrôle dans le compilateur n'est pas possible (pas de connexion). Solution retenue (la plus courte) : **le runtime contrôle avant compilation**. Remplacer la fonction ci-dessus par une simple vérification appelée depuis `_execute_transform_chain`, juste avant `compiler.compile_transform_sql(...)` :

```python
# runtime.py, dans la branche `else` (op compilée), avant compile_transform_sql :
                if contract.pre_check is not None:
                    contract.pre_check(conn, input_view=input_view, params=node.params)
```

Ajouter à `OperationContract` (`core/app/pipelines/ops/operation_contract.py`) le champ optionnel :

```python
    # Contrôle borné exécuté par le runtime avant compilation (AUD-078) ; None = aucun.
    pre_check: Callable[..., None] | None = None
```

et dans `filtering.py`, à la place de `execute_neighbor_finder` :

```python
NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE = 5_000


def pre_check_neighbor_finder(conn, *, input_view: str, params: dict) -> None:
    """AUD-078 : sans maxDistance la requête est un produit cartésien — plafond explicite."""
    p = TransformNeighborFinderParams.model_validate(params)
    if p.maxDistance is not None:
        return
    (n,) = conn.execute(f"SELECT count(*) FROM {_qi(input_view)}").fetchone()
    if n > NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE:
        raise PipelineRuntimeError(
            f"transform.neighborFinder : {n} lignes sans maxDistance "
            f"(max {NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE}) — renseigner maxDistance"
        )
```

Dans `contracts.py`, contrat `transform.neighborFinder` : ajouter `pre_check=_filtering.pre_check_neighbor_finder`. Adapter le test du Step 1 :

```python
def test_neighbor_finder_without_distance_refuses_large_inputs(conn, monkeypatch):
    monkeypatch.setattr(filtering, "NEIGHBOR_FINDER_MAX_ROWS_WITHOUT_DISTANCE", 2)
    conn.execute("CREATE TABLE a AS SELECT ST_Point(i, i) AS geometry FROM range(3) t(i)")
    with pytest.raises(PipelineRuntimeError, match="maxDistance"):
        filtering.pre_check_neighbor_finder(conn, input_view="a", params={})
```

(`pre_check` lève `PipelineRuntimeError` : il est dans le `try duckdb.Error` du runtime mais n'est pas une `duckdb.Error`, il remonte tel quel.)

- [ ] **Step 5 : TEMP TABLE en run, VIEW en aperçu**

Dans `core/app/pipelines/runtime.py`, `_execute_transform_chain`, remplacer :

```python
                conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
            stat = NodeStat(node.id, node.op, _view_row_count(conn, view_name))
```

par :

```python
                # AUD-078 : en run, matérialiser — une VIEW est ré-évaluée par chaque nœud
                # aval (coût quadratique en profondeur) et par le comptage. En aperçu, la
                # VIEW reste (LIMIT 50 en bout de chaîne) et le comptage est sauté.
                kind = "VIEW" if preview else "TABLE"
                conn.execute(f"CREATE TEMP {kind} {_qi(view_name)} AS {sql}")
            stat = NodeStat(
                node.id, node.op, None if preview else _view_row_count(conn, view_name)
            )
```

Vérifier que `NodeStat.rowCount` accepte `None` (`grep -n "class NodeStat" -A8 core/app/pipelines/runtime.py`) ; sinon typer `int | None` et vérifier les consommateurs de `rowCount` en aperçu (`grep -rn "rowCount" core/app shell/src --include=*.py --include=*.ts --include=*.tsx`). Les `execute` ops qui créent une TEMP VIEW (`_create_view` dans attrs.py) restent des vues : hors périmètre, leur coût est borné par la table matérialisée en amont.

- [ ] **Step 6 : troncatures signalées**

`core/app/pipelines/ops/cloudfiles.py`, `read_arcgisonline` : là où la boucle s'arrête parce que `len(rows) >= want`, lever si la source signale encore des données :

```python
        if len(rows) >= want and (page.get("exceededTransferLimit") or len(batch) == page_size):
            raise PipelineRuntimeError(
                f"reader.arcgisonline : résultat tronqué à {want} entités — augmenter "
                "maxFeatures ou filtrer à la source (where/geometry)"
            )
```

(adapter `page`/`batch`/`page_size` aux noms réels des variables de la boucle l.591-679 — lire la boucle avant d'éditer.)

`core/app/pipelines/ops/wfs.py`, `read_wfs` : demander une entité de plus que la limite et refuser si elle arrive :

```python
    limit = p.maxFeatures
    query["count" if version.startswith("2") else "maxFeatures"] = str(limit + 1)
    ...
    if len(features) > limit:
        raise PipelineRuntimeError(
            f"reader.wfs : résultat tronqué à {limit} entités — augmenter maxFeatures "
            "ou filtrer (bbox)"
        )
```

(noms réels `p`, `query`, `version`, `features` à vérifier dans `read_wfs` l.74-140.)

- [ ] **Step 7 : géométrie des lecteurs SQL**

`core/app/pipelines/ops/schemas.py`, remplacer `_IncrementalReader` :

```python
class _IncrementalReader(BaseModel):
    incremental: IncrementalSpec | None = None
    # AUD-082 : colonne source portant la géométrie (texte WKT, WKB hexadécimal ou GeoJSON),
    # décodée en `geometry` après lecture ; sans elle la sortie n'a pas de géométrie.
    geometryColumn: str | None = None
    geometryFormat: Literal["wkt", "wkb_hex", "geojson"] = "wkt"
    geometrySrid: int = Field(4326, ge=1)
```

`core/app/pipelines/runtime.py`, ajouter près de `_view_row_count` :

```python
_GEOMETRY_DECODERS = {
    "wkt": "ST_GeomFromText({c})",
    "wkb_hex": "ST_GeomFromHEXEWKB({c})",
    "geojson": "ST_GeomFromGeoJSON({c})",
}


def _decode_connector_geometry(conn, view_name: str, params: dict) -> int | None:
    """AUD-082 : décode `geometryColumn` d'un reader connecteur en colonne `geometry`.
    Retourne le SRID déclaré, ou None si aucune colonne géométrie n'est configurée."""
    col = params.get("geometryColumn")
    if not col:
        return None
    cols = [d[0] for d in conn.execute(f"DESCRIBE {_qi(view_name)}").fetchall()]
    if col not in cols:
        raise PipelineRuntimeError(f"colonne géométrie {col!r} absente (colonnes : {cols})")
    expr = _GEOMETRY_DECODERS[params.get("geometryFormat", "wkt")].format(c=_qi(col))
    raw = f"{view_name}__raw"
    conn.execute(f"ALTER TABLE {_qi(view_name)} RENAME TO {_qi(raw)}")
    exclude = f"{_qi(col)}, geometry" if "geometry" in cols and col != "geometry" else _qi(col)
    conn.execute(
        f"CREATE TEMP TABLE {_qi(view_name)} AS "
        f"SELECT * EXCLUDE ({exclude}), {expr} AS geometry FROM {_qi(raw)}"
    )
    conn.execute(f"DROP TABLE {_qi(raw)}")
    return int(params.get("geometrySrid", 4326))
```

Et dans `_prepare`, juste après `view_by_node[node.id] = view_name` (l.746), avant le bloc incrémental :

```python
        if node.op.startswith("reader.connector."):
            try:
                decoded_srid = _decode_connector_geometry(conn, view_name, node.params)
            except duckdb.Error as exc:
                raise _node_error(node, exc) from exc
            if decoded_srid is not None:
                srid_by_node[node.id] = decoded_srid
```

Vérifier que tous les readers connecteurs matérialisent bien une TEMP TABLE (`connector_runtime._run_dlt_and_attach` : oui ; `reader.connector.blob` : `grep -n "CREATE TEMP" core/app/pipelines/connector_runtime.py`). Si l'un crée une VIEW, `ALTER TABLE … RENAME` échoue : dans ce cas utiliser `ALTER VIEW` selon `SELECT table_type FROM information_schema.tables WHERE table_name = ?` (consigner l'écart).

- [ ] **Step 8 : vérifier**

Run : `cd core && uv run pytest tests/test_pipeline_bounds_l5.py -v && CORE_TEST_DATABASE_URL=… uv run pytest tests -k "pipeline or wfs or arcgis or connector" -q`
Expected : PASS.

- [ ] **Step 9 : commit**

```bash
git add core/app/pipelines/ops/execute.py core/app/pipelines/ops/filtering.py core/app/pipelines/ops/operation_contract.py core/app/pipelines/ops/contracts.py core/app/pipelines/runtime.py core/app/pipelines/ops/cloudfiles.py core/app/pipelines/ops/wfs.py core/app/pipelines/ops/schemas.py core/tests/
git commit -m "fix(core): plafonds d'entrée, nœuds matérialisés en run, lecteurs sans troncature silencieuse (AUD-078/082)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : `geom2.py` (`_Budget` plus serré, inchangé, passe aussi par `_read_geometry_rows`), `reader.connector.*` du sidecar desktop (même `_prepare`), `reader.ogcapi*`/`reader.arcgisfs` s'ils paginent avec plafond (`grep -n "_max_rows()" core/app/pipelines/ops/*.py` — appliquer le même refus « tronqué » à tout lecteur qui coupe en silence).

---

### Task 3 : Ops de qualité — validateGeometry, measure, spatialJoin (AUD-079, AUD-021)

**Files :**
- Create : `core/app/pipelines/ops/quality.py`
- Modify : `core/app/pipelines/ops/contracts.py` (`LANE_MODULES` l.686)
- Modify : `core/tests/test_pipeline_ops_contracts.py` (compte attendu d'op, si codé en dur)
- Test : `core/tests/test_pipeline_ops_quality.py` (nouveau)

**Interfaces :**
- Consumes : `OperationContract`, `OutputColumn`, `_output_srid_reconcile_join`, `_qi`, `PipelineRuntimeError` ; helpers `attrs._udf`, `attrs._no_clash`, `attrs._columns`, `attrs._create_view`.
- Produces : ops `transform.validateGeometry`, `transform.measure`, `transform.spatialJoin` ; modèles `TransformValidateGeometryParams`, `TransformMeasureParams`, `TransformSpatialJoinParams` ; module `app.pipelines.ops.quality` dans `LANE_MODULES`.

- [ ] **Step 1 : tests qui échouent**

`core/tests/test_pipeline_ops_quality.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 3 : validateGeometry, measure, spatialJoin (AUD-079, AUD-021)."""

import duckdb
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import quality
from app.pipelines.ops.contracts import OPERATIONS

BOWTIE = "POLYGON((0 0,2 2,2 0,0 2,0 0))"


@pytest.fixture()
def conn():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


def _cols(conn, view):
    return [d[0] for d in conn.execute(f'DESCRIBE "{view}"').fetchall()]


def test_ops_are_registered():
    for op in ("transform.validateGeometry", "transform.measure", "transform.spatialJoin"):
        assert op in OPERATIONS


def test_validate_geometry_flags_with_reason(conn):
    conn.execute(
        f"CREATE TABLE src AS SELECT 1 AS id, ST_GeomFromText('{BOWTIE}') AS geometry "
        "UNION ALL SELECT 2, ST_GeomFromText('POINT(0 0)')"
    )
    quality.execute_validate_geometry(
        conn,
        input_view="src",
        view_name="out",
        params={"mode": "flag", "validColumn": "ok", "reasonColumn": "why"},
    )
    rows = conn.execute("SELECT id, ok, why FROM out ORDER BY id").fetchall()
    assert rows[0][1] is False and "Self-intersection" in rows[0][2]
    assert rows[1][1] is True and rows[1][2] is None


def test_validate_geometry_repairs(conn):
    conn.execute(f"CREATE TABLE src AS SELECT ST_GeomFromText('{BOWTIE}') AS geometry")
    quality.execute_validate_geometry(
        conn, input_view="src", view_name="out", params={"mode": "repair", "validColumn": "ok"}
    )
    assert conn.execute("SELECT ST_IsValid(geometry), ok FROM out").fetchone() == (True, False)


def test_measure_geodesic_area_in_square_meters(conn):
    conn.execute(
        "CREATE TABLE src AS SELECT ST_GeomFromText("
        "'POLYGON((2 49,2.01 49,2.01 49.01,2 49.01,2 49))') AS geometry"
    )
    quality.execute_measure(
        conn,
        input_view="src",
        view_name="out",
        params={"measure": "area", "method": "geodesic", "column": "m2"},
        input_srid=4326,
    )
    (area,) = conn.execute("SELECT m2 FROM out").fetchone()
    assert 800_000 < area < 830_000


def test_measure_planar_uses_native_units(conn):
    conn.execute("CREATE TABLE src AS SELECT ST_GeomFromText('LINESTRING(0 0, 3 4)') AS geometry")
    quality.execute_measure(
        conn,
        input_view="src",
        view_name="out",
        params={"measure": "length", "method": "planar", "column": "len"},
        input_srid=2154,
    )
    assert conn.execute("SELECT len FROM out").fetchone()[0] == 5


def test_spatial_join_reports_prefixed_attributes(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'p1' AS ref, ST_GeomFromText("
        "'POLYGON((0 0,1 0,1 1,0 1,0 0))') AS geometry "
        "UNION ALL SELECT 'p2', ST_GeomFromText('POLYGON((5 5,6 5,6 6,5 6,5 5))')"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 'UA' AS zone, ST_GeomFromText("
        "'POLYGON((0 0,0.7 0,0.7 1,0 1,0 0))') AS geometry "
        "UNION ALL SELECT 'N', ST_GeomFromText('POLYGON((0.7 0,1 0,1 1,0.7 1,0.7 0))')"
    )
    sql = quality.compile_spatial_join(
        {"how": "left", "match": "largestOverlap"},
        input_view="a",
        join_view="b",
        input_srid=4326,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b"),
    )
    rows = conn.execute(f"SELECT ref, join_zone FROM ({sql}) ORDER BY ref").fetchall()
    assert rows == [("p1", "UA"), ("p2", None)]


def test_spatial_join_all_matches_duplicates_rows(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT 'p1' AS ref, ST_GeomFromText("
        "'POLYGON((0 0,1 0,1 1,0 1,0 0))') AS geometry"
    )
    conn.execute(
        "CREATE TABLE b AS SELECT 'x' AS zone, ST_Point(0.2,0.2) AS geometry "
        "UNION ALL SELECT 'y', ST_Point(0.8,0.8)"
    )
    sql = quality.compile_spatial_join(
        {"how": "inner", "match": "all"},
        input_view="a",
        join_view="b",
        input_srid=4326,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b"),
    )
    assert conn.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0] == 2


def test_spatial_join_refuses_column_clash(conn):
    with pytest.raises(PipelineRuntimeError, match="join_zone"):
        quality.compile_spatial_join(
            {},
            input_view="a",
            join_view="b",
            input_srid=4326,
            input_columns=["join_zone", "geometry"],
            join_columns=["zone", "geometry"],
        )
```

- [ ] **Step 2 : vérifier l'échec**

Run : `cd core && uv run pytest tests/test_pipeline_ops_quality.py -v`
Expected : FAIL (`ImportError: cannot import name 'quality'`).

- [ ] **Step 3 : implémenter `core/app/pipelines/ops/quality.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Module de voie « qualité » (SP-L5, AUD-079/021) : validation/réparation de géométrie,
mesures planes ou géodésiques, jointure spatiale avec report d'attributs.

Agrégé par app.pipelines.ops.contracts.LANE_MODULES ; ne jamais importer contracts/runtime/
registries au niveau module (cycle d'import)."""

from collections.abc import Callable
from typing import Literal

import shapely.wkb
from pydantic import BaseModel, Field, model_validator
from shapely.validation import explain_validity

from app.pipelines.compiler import _output_srid_reconcile_join
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.attrs import _columns, _create_view, _no_clash, _udf
from app.pipelines.ops.operation_contract import OperationContract, OutputColumn
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_DUCKDB = "MIT (DuckDB)"
_RID = '"__gs_rid"'


# --------------------------------------------------------------------------- validateGeometry


class TransformValidateGeometryParams(BaseModel):
    """Contrôle OGC de chaque géométrie. `flag` : ajoute `validColumn` (booléen, NULL si
    géométrie absente) et, si `reasonColumn` est renseigné, la raison de l'invalidité.
    `repair` : remplace aussi la géométrie par `ST_MakeValid` (le drapeau décrit l'état
    AVANT réparation)."""

    mode: Literal["flag", "repair"] = "flag"
    validColumn: OutputColumn = "geometry_valid"
    reasonColumn: OutputColumn | None = None


def execute_validate_geometry(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformValidateGeometryParams.model_validate(params)
    have = _columns(conn, input_view)
    extra = [p.reasonColumn] if p.reasonColumn else []
    _no_clash("transform.validateGeometry", have, p.validColumn, *extra)
    sel = [f"ST_IsValid(geometry) AS {_qi(p.validColumn)}"]
    if p.reasonColumn:
        fn = _udf(
            conn,
            view_name,
            "why",
            lambda wkb: None
            if (r := explain_validity(shapely.wkb.loads(bytes(wkb)))) == "Valid Geometry"
            else r,
            ["BLOB"],
            "VARCHAR",
        )
        sel.append(f"{fn}(ST_AsWKB(geometry)) AS {_qi(p.reasonColumn)}")
    geom = "ST_MakeValid(geometry)" if p.mode == "repair" else "geometry"
    _create_view(
        conn,
        view_name,
        f"SELECT * EXCLUDE (geometry), {geom} AS geometry, {', '.join(sel)} "
        f"FROM {_qi(input_view)}",
    )


# --------------------------------------------------------------------------- measure


class TransformMeasureParams(BaseModel):
    """Ajoute une mesure par géométrie. `planar` : unités du SCR (mètres pour un SCR
    projeté métrique). `geodesic` : mètres / m² sur l'ellipsoïde WGS84, quel que soit le
    SCR d'entrée (reprojection interne en EPSG:4326)."""

    measure: Literal["area", "length", "perimeter"]
    method: Literal["planar", "geodesic"] = "geodesic"
    column: OutputColumn


_PLANAR = {"area": "ST_Area", "length": "ST_Length", "perimeter": "ST_Perimeter"}
_SPHEROID = {
    "area": "ST_Area_Spheroid",
    "length": "ST_Length_Spheroid",
    "perimeter": "ST_Perimeter_Spheroid",
}


def execute_measure(
    conn, *, input_view: str, view_name: str, params: dict, input_srid: int | None = None, **_
) -> None:
    p = TransformMeasureParams.model_validate(params)
    _no_clash("transform.measure", _columns(conn, input_view), p.column)
    if p.method == "planar":
        expr = f"{_PLANAR[p.measure]}(geometry)"
    else:
        if not input_srid:
            raise PipelineRuntimeError(
                "transform.measure : SRID d'entrée inconnu — utiliser transform.setSrid"
            )
        g = "geometry"
        if input_srid != 4326:
            g = f"ST_Transform(geometry, 'EPSG:{input_srid}', 'EPSG:4326', true)"
        # *_Spheroid attend (lat, lon) : ST_FlipCoordinates (vérifié DuckDB 1.5.5).
        expr = f"{_SPHEROID[p.measure]}(ST_FlipCoordinates({g}))"
    _create_view(conn, view_name, f"SELECT *, {expr} AS {_qi(p.column)} FROM {_qi(input_view)}")


# --------------------------------------------------------------------------- spatialJoin


class TransformSpatialJoinParams(BaseModel):
    """Jointure spatiale avec report des attributs de la seconde entrée, préfixés par
    `prefix`. `match` : `all` (une ligne par correspondance), `first` (une seule, arbitraire
    mais stable), `largestOverlap` (celle de plus grande surface d'intersection — polygones).
    `how=left` garde les lignes sans correspondance (attributs NULL). La géométrie de sortie
    est celle de l'entrée principale, ou l'intersection."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    predicate: Literal["intersects", "within", "contains", "dwithin"] = "intersects"
    distance: float | None = Field(None, gt=0)
    how: Literal["inner", "left"] = "left"
    match: Literal["all", "first", "largestOverlap"] = "first"
    prefix: str = Field("join_", pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,30}$")
    outputGeometry: Literal["left", "intersection"] = "left"

    @model_validator(mode="after")
    def _distance_for_dwithin(self) -> "TransformSpatialJoinParams":
        if (self.predicate == "dwithin") != (self.distance is not None):
            raise ValueError("distance est requis pour dwithin, et seulement pour lui")
        return self


def compile_spatial_join(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformSpatialJoinParams.model_validate(params)
    assert join_view is not None, "transform.spatialJoin requires join_view"
    right = [c for c in (join_columns or []) if c != "geometry"]
    out = [f"{p.prefix}{c}" for c in right]
    _no_clash("transform.spatialJoin", input_columns or [], *out, _RID.strip('"'))
    pred = {
        "intersects": "ST_Intersects(t.geometry, o.geometry)",
        "within": "ST_Within(t.geometry, o.geometry)",
        "contains": "ST_Contains(t.geometry, o.geometry)",
        "dwithin": f"ST_DWithin(t.geometry, o.geometry, {p.distance})",
    }[p.predicate]
    join_kw = "LEFT JOIN" if p.how == "left" else "JOIN"
    right_sel = "".join(f", o.{_qi(c)} AS {_qi(n)}" for c, n in zip(right, out, strict=True))
    geom = (
        "t.geometry"
        if p.outputGeometry == "left"
        else "coalesce(ST_Intersection(t.geometry, o.geometry), t.geometry)"
    )
    base = (
        f"SELECT t.* EXCLUDE (geometry), {geom} AS geometry{right_sel}, t.{_RID} AS {_RID}, "
        f"ST_Area(ST_Intersection(t.geometry, o.geometry)) AS __gs_overlap "
        f"FROM (SELECT *, row_number() OVER () AS {_RID} FROM {_qi(input_view)}) t "
        f"{join_kw} {_qi(join_view)} o ON {pred}"
    )
    if p.match == "all":
        return f"SELECT * EXCLUDE ({_RID}, __gs_overlap) FROM ({base})"
    order = "__gs_overlap DESC NULLS LAST" if p.match == "largestOverlap" else "1"
    return (
        f"SELECT * EXCLUDE ({_RID}, __gs_overlap) FROM ({base}) "
        f"QUALIFY row_number() OVER (PARTITION BY {_RID} ORDER BY {order}) = 1"
    )


def _c(op, schema, **kw) -> OperationContract:
    return OperationContract(
        op=f"transform.{op}",
        kind="transform",
        params_schema=schema,
        engine="duckdb",
        engine_license=_DUCKDB,
        **kw,
    )


CONTRACTS.extend(
    [
        _c(
            "validateGeometry",
            TransformValidateGeometryParams,
            execute=execute_validate_geometry,
        ),
        _c(
            "measure",
            TransformMeasureParams,
            execute=execute_measure,
            needs_runtime_context=True,
        ),
        _c(
            "spatialJoin",
            TransformSpatialJoinParams,
            accepts_secondary_input=True,
            needs_columns=True,
            compile=compile_spatial_join,
            output_srid=_output_srid_reconcile_join,
        ),
    ]
)
```

Remarques à vérifier en codant : (1) `needs_runtime_context=True` passe `secret_resolver`, `preview`, `input_srid` → la signature `execute_measure(..., input_srid=None, **_)` les absorbe ; (2) `_output_srid_reconcile_join` reprojette-t-il la seconde entrée ? Lire sa docstring dans `compiler.py` : si la réconciliation n'est que déclarative (refus si SRID différents), le comportement est celui de `spatialRelator`, identique ; (3) si `ST_Area(ST_Intersection(...))` coûte trop pour `match=first`, le calculer seulement pour `largestOverlap` (`NULL AS __gs_overlap` sinon) — faire ce changement d'emblée :

```python
    overlap = (
        "ST_Area(ST_Intersection(t.geometry, o.geometry))"
        if p.match == "largestOverlap"
        else "NULL::DOUBLE"
    )
```

et utiliser `{overlap} AS __gs_overlap` dans `base`.

- [ ] **Step 4 : enregistrer la voie**

Dans `core/app/pipelines/ops/contracts.py`, `LANE_MODULES` (l.686) : ajouter `quality` à l'import des modules de voie et à la liste, au même format que `reliquats`. Si `core/tests/test_pipeline_ops_contracts.py` (ou autre) code en dur le nombre d'op exposées (`grep -rn "== 91\|== 121\|== 152" core/tests`), passer à +3.

- [ ] **Step 5 : vérifier**

Run : `cd core && uv run pytest tests/test_pipeline_ops_quality.py tests/test_pipeline_ops_contracts.py -v`
Expected : PASS. Puis `uv run lint-imports` → contrat OK (le module importe `attrs`, voie sœur : vérifier qu'aucun contrat n'interdit voie→voie ; sinon copier les 4 helpers utilisés plutôt que de les importer).

- [ ] **Step 6 : commit**

```bash
git add core/app/pipelines/ops/quality.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_ops_quality.py core/tests/test_pipeline_ops_contracts.py
git commit -m "feat(core): ops validateGeometry, measure et spatialJoin à report d'attributs (AUD-079/021)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : outil d'analyse `spatialJoin` (`analysis.py:182`, op `transform.intersection` sans attributs) — **laissé tel quel** (le widget Analyse a sa propre sortie de colonnes `keep`/`added` ; le basculer exige de typer les colonnes préfixées : reporté au lot shell/analyse, consigné). Catalogue `GET /pipelines/ops` : 3 op de plus (flag-indépendantes). Palette shell : aucune modification (libellés génériques).

---

### Task 4 : Qualité des données — collisions de sortie, clé NULL/doublon, validateAttributes, seuil de rejet, pré-contrôle de schéma, feature_count (AUD-080, AUD-088 F3/F14)

**Files :**
- Modify : `core/app/pipelines/ops/schemas.py` (`TransformValidateAttributesParams` l.595, `TransformDetectChangesParams` l.617, `WriterCollectionParams` l.66)
- Modify : `core/app/pipelines/compiler.py` (`_compile_validate_attributes` l.649, `_compile_detect_changes` l.696)
- Modify : `core/app/pipelines/ops/contracts.py` (`transform.validateAttributes` l.486 : `needs_columns=True`)
- Modify : `core/app/pipelines/runtime.py` (`_node_error` l.988)
- Modify : `core/app/pipelines/collection_writer.py` (`write_rows` l.344-516)
- Test : `core/tests/test_pipeline_quality_l5.py` (nouveau), `core/tests/test_collection_writer*.py` (existant)

**Interfaces :**
- Consumes : `_RID`, `PipelineRuntimeError` (Task 1 dans compiler.py), `OutputColumn`.
- Produces : `TransformValidateAttributesParams.notBlankColumns: list[str]`, `.notBlankResultColumn: OutputColumn | None` ; statut `'invalid'` de detectChanges pour une clé NULL ; `WriterCollectionParams.maxRejectRate: float | None` (0..1).

- [ ] **Step 1 : tests qui échouent**

`core/tests/test_pipeline_quality_l5.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 4 (AUD-080) : collisions de colonnes de sortie, clé NULL/doublon de
detectChanges, validateAttributes enrichi, message d'erreur lisible."""

import duckdb
import pytest

from app.pipelines import compiler
from app.pipelines.errors import PipelineRuntimeError


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _cols(conn, v):
    return [d[0] for d in conn.execute(f'DESCRIBE "{v}"').fetchall()]


def _sql(conn, op, params, join=True):
    return compiler.compile_transform_sql(
        op,
        params,
        input_view="a",
        join_view="b" if join else None,
        input_srid=None,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b") if join else None,
    )


def test_detect_changes_null_key_is_invalid_not_inserted_and_deleted(conn):
    conn.execute("CREATE TABLE a AS SELECT NULL::INT AS k, 'x' AS v")
    conn.execute("CREATE TABLE b AS SELECT NULL::INT AS k, 'x' AS v")
    rows = conn.execute(
        _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})
    ).fetchall()
    assert sorted(r[-1] for r in rows) == ["invalid", "invalid"]


def test_detect_changes_duplicate_key_fails(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, 'x' AS v UNION ALL SELECT 1, 'y'")
    conn.execute("CREATE TABLE b AS SELECT 1 AS k, 'x' AS v")
    sql = _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})
    with pytest.raises(duckdb.InvalidInputException, match="clé dupliquée"):
        conn.execute(sql).fetchall()


def test_detect_changes_refuses_status_column_clash(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, 'x' AS s")
    conn.execute("CREATE TABLE b AS SELECT 1 AS k, 'x' AS s")
    with pytest.raises(PipelineRuntimeError, match="s"):
        _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})


def test_validate_attributes_not_blank_and_null_aware_unique(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT * FROM (VALUES (1, 'x'), (2, '  '), (NULL, 'z'), (NULL, 'w')) "
        "t(k, label)"
    )
    conn.execute("CREATE TABLE b AS SELECT 1 AS unused")
    sql = _sql(
        conn,
        "transform.validateAttributes",
        {
            "notBlankColumns": ["label"],
            "notBlankResultColumn": "label_ok",
            "uniqueColumns": ["k"],
            "uniqueResultColumn": "k_unique",
        },
        join=False,
    )
    rows = conn.execute(f"SELECT k, label_ok, k_unique FROM ({sql})").fetchall()
    by_k = {r[0]: r for r in rows if r[0] is not None}
    assert by_k[1][1:] == (True, True)
    assert by_k[2][1] is False  # '  ' est vide après trim
    assert [r[2] for r in rows if r[0] is None] == [None, None]  # clé NULL : indéterminé


def test_validate_attributes_refuses_result_column_clash(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, true AS ok")
    conn.execute("CREATE TABLE b AS SELECT 1 AS unused")
    with pytest.raises(PipelineRuntimeError, match="ok"):
        _sql(
            conn,
            "transform.validateAttributes",
            {"nonNullColumns": ["k"], "nonNullResultColumn": "ok"},
            join=False,
        )


def test_node_error_strips_multi_word_duckdb_prefix():
    from app.configs.schemas import PipelineNode
    from app.pipelines.runtime import _node_error

    node = PipelineNode(id="n1", kind="transform", op="transform.filter", params={"expr": "1"})
    err = _node_error(node, Exception("Invalid Input Error: clé dupliquée"))
    assert str(err) == "nœud 'n1' (transform.filter) : clé dupliquée"
```

Dans le fichier de test du writer (`grep -ln "def write_rows\|write_rows(" core/tests/*.py` → ex. `core/tests/test_collection_writer.py`), ajouter trois tests en réutilisant ses fixtures (lire le fichier, ne pas inventer de fixture) :
1. `test_write_rows_fails_when_reject_rate_exceeds_max` : `mode="append"`, `maxRejectRate=0.1`, 10 lignes dont 2 invalides → `PipelineRuntimeError` « taux de rejet 20 % » et **aucune** ligne écrite (la transaction du run est annulée par l'appelant : vérifier `count(*)` = état initial).
2. `test_write_rows_refuses_unknown_input_columns_before_writing` : une colonne d'entrée absente de la cible → `PipelineRuntimeError` nommant la colonne, au lieu de N rejets `unknown_property`.
3. `test_append_and_replace_update_feature_count` : après `append` de 3 lignes sur une collection à `feature_count=5` → 8 ; après `replace` de 2 lignes → 2.

- [ ] **Step 2 : vérifier l'échec**

Run : `cd core && uv run pytest tests/test_pipeline_quality_l5.py -v`
Expected : FAIL.

- [ ] **Step 3 : schémas**

`core/app/pipelines/ops/schemas.py` :

```python
class TransformValidateAttributesParams(BaseModel):
    """Valide des attributs explicites et écrit un booléen par vérification demandée.
    `nonNull` : toutes les colonnes non NULL. `notBlank` : non NULL et non vides après
    suppression des espaces. `unique` : la combinaison est unique ; NULL si une partie de la
    clé est NULL (indéterminé, jamais « unique »)."""

    nonNullColumns: list[str] = Field(default_factory=list)
    nonNullResultColumn: OutputColumn | None = None
    notBlankColumns: list[str] = Field(default_factory=list)
    notBlankResultColumn: OutputColumn | None = None
    uniqueColumns: list[str] = Field(default_factory=list)
    uniqueResultColumn: OutputColumn | None = None

    @model_validator(mode="after")
    def _at_least_one_check(self) -> "TransformValidateAttributesParams":
        pairs = [
            (self.nonNullColumns, self.nonNullResultColumn),
            (self.notBlankColumns, self.notBlankResultColumn),
            (self.uniqueColumns, self.uniqueResultColumn),
        ]
        if not any(cols and res is not None for cols, res in pairs):
            raise ValueError(
                "transform.validateAttributes requires at least one check (colonnes + colonne "
                "de résultat)"
            )
        return self


class TransformDetectChangesParams(BaseModel):
    """Compare l'entrée principale (« avant ») à la seconde (« après ») sur `keyColumns`.
    Statuts : inserted/deleted/updated/unchanged, et `invalid` pour une ligne dont une partie
    de la clé est NULL (jamais rapprochable ; writer.collection la rejette en quarantaine).
    Une clé dupliquée d'un côté fait échouer le nœud."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    keyColumns: list[str] = Field(..., min_length=1)
    statusColumn: OutputColumn
```

`WriterCollectionParams` : ajouter

```python
    maxRejectRate: float | None = Field(
        None,
        ge=0,
        le=1,
        description=(
            "Seuil de qualité : si la part de lignes rejetées dépasse cette valeur (0 à 1), "
            "le run échoue et rien n'est écrit."
        ),
    )
```

- [ ] **Step 4 : compilateur**

`core/app/pipelines/compiler.py`, remplacer `_compile_validate_attributes` (et ajouter `input_columns`/`join_columns` à sa signature ; passer `needs_columns=True` sur son contrat) :

```python
def _compile_validate_attributes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformValidateAttributesParams.model_validate(params)
    outputs = [
        r for r in (p.nonNullResultColumn, p.notBlankResultColumn, p.uniqueResultColumn) if r
    ]
    clash = [c for c in outputs if c in (input_columns or [])]
    if clash or len(set(outputs)) != len(outputs):
        raise PipelineRuntimeError(
            f"transform.validateAttributes : colonne(s) de résultat en collision : "
            f"{clash or outputs}"
        )
    extra_cols = []
    if p.nonNullColumns and p.nonNullResultColumn:
        checks = " AND ".join(f"{_qi(c)} IS NOT NULL" for c in p.nonNullColumns)
        extra_cols.append(f"({checks}) AS {_qi(p.nonNullResultColumn)}")
    if p.notBlankColumns and p.notBlankResultColumn:
        checks = " AND ".join(
            f"coalesce(trim(CAST({_qi(c)} AS VARCHAR)), '') <> ''" for c in p.notBlankColumns
        )
        extra_cols.append(f"({checks}) AS {_qi(p.notBlankResultColumn)}")
    if p.uniqueColumns and p.uniqueResultColumn:
        partition = ", ".join(_qi(c) for c in p.uniqueColumns)
        any_null = " OR ".join(f"{_qi(c)} IS NULL" for c in p.uniqueColumns)
        extra_cols.append(
            f"(CASE WHEN {any_null} THEN NULL "
            f"ELSE COUNT(*) OVER (PARTITION BY {partition}) = 1 END) "
            f"AS {_qi(p.uniqueResultColumn)}"
        )
    return f"SELECT *, {', '.join(extra_cols)} FROM {_qi(input_view)}"
```

Dans `_compile_detect_changes`, après les `assert` :

```python
    clash = [p.statusColumn] if p.statusColumn in (*input_columns, *join_columns) else []
    if clash:
        raise PipelineRuntimeError(
            f"transform.detectChanges : colonne de statut {p.statusColumn!r} déjà présente"
        )
    keys = ", ".join(_qi(k) for k in p.keyColumns)
    null_t = " OR ".join(f"t.{_qi(k)} IS NULL" for k in p.keyColumns)
    null_o = " OR ".join(f"o.{_qi(k)} IS NULL" for k in p.keyColumns)
```

remplacer `status_expr` par :

```python
    status_expr = (
        "CASE "
        f"WHEN (t.__gs_present AND ({null_t})) OR (o.__gs_present AND ({null_o})) "
        "THEN 'invalid' "
        "WHEN t.__gs_present IS NULL THEN 'inserted' "
        "WHEN o.__gs_present IS NULL THEN 'deleted' "
        f"WHEN {diff_expr} THEN 'updated' "
        "ELSE 'unchanged' END"
    )
```

la condition de jointure par `ON {key_join} AND NOT ({null_t}) AND NOT ({null_o})` (une clé NULL ne se rapproche jamais : chaque côté sort seul en `invalid`), et envelopper les deux sous-requêtes d'un contrôle de doublon :

```python
    def side(view: str) -> str:
        return (
            f"(SELECT *, TRUE AS __gs_present, "
            f"CASE WHEN count(*) OVER (PARTITION BY {keys}) > 1 "
            f"AND NOT ({' OR '.join(f'{_qi(k)} IS NULL' for k in p.keyColumns)}) "
            f"THEN error('transform.detectChanges : clé dupliquée') END AS __gs_dup "
            f"FROM {_qi(view)})"
        )
```

puis `FROM {side(input_view)} t FULL OUTER JOIN {side(join_view)} o ON …`. `__gs_dup` n'apparaît pas dans `data_select` (liste explicite) : rien à exclure. Attention : DuckDB peut élaguer une colonne non projetée et ne jamais évaluer `error()` — si le test `test_detect_changes_duplicate_key_fails` passe sans lever, forcer l'évaluation en ajoutant `WHERE t.__gs_dup IS NULL OR TRUE` n'est pas fiable ; utiliser plutôt un filtre `WHERE coalesce(t.__gs_dup, o.__gs_dup) IS NULL` (référence effective, toujours vraie quand aucune erreur). Le test tranche.

- [ ] **Step 5 : message d'erreur lisible**

`core/app/pipelines/runtime.py`, `_node_error` : remplacer `r"^\w+ Error:\s*"` par `r"^[\w ]+ Error:\s*"`.

- [ ] **Step 6 : writer — pré-contrôle, seuil, feature_count**

Dans `core/app/pipelines/collection_writer.py`, `write_rows` (l.344-516), lire la fonction entière puis :

(a) Pré-contrôle de schéma juste après le calcul des colonnes d'entrée et des `ColumnInfo` de la cible (avant toute écriture) :

```python
    target_names = {c.name for c in target_columns} | {"geometry"}
    ignored = {statusColumn} if statusColumn else set()
    unknown = sorted(set(input_columns) - target_names - ignored - _INTERNAL_COLUMNS)
    if unknown:
        raise PipelineRuntimeError(
            f"writer.collection : colonne(s) absente(s) de la collection cible : {unknown} — "
            "les retirer (transform.select) ou les ajouter à la collection"
        )
    missing = sorted(
        c.name for c in target_columns if c.required and c.name not in input_columns
    )
    if missing and mode not in ("delete", "update"):
        raise PipelineRuntimeError(
            f"writer.collection : colonne(s) obligatoire(s) absente(s) de l'entrée : {missing}"
        )
```

(`target_columns`, `input_columns`, `statusColumn`, `mode` : remplacer par les noms réels de `write_rows` ; `_INTERNAL_COLUMNS` = les colonnes que le writer ignore déjà — `id`, `tenant_id` s'il y en a ; si ce concept n'existe pas, utiliser `set()`.)

(b) Seuil de rejet, après la boucle d'écriture et avant le retour du `WriteResult` :

```python
    if p.maxRejectRate is not None and n_in and rejected / n_in > p.maxRejectRate:
        raise PipelineRuntimeError(
            f"writer.collection : taux de rejet {rejected / n_in:.0%} supérieur au seuil "
            f"{p.maxRejectRate:.0%} ({rejected}/{n_in}) — rien n'est écrit"
        )
```

(lever une `PipelineRuntimeError` annule la transaction du run, quarantaine comprise — c'est le comportement voulu : « rien n'est écrit » ; vérifier dans `run_pipeline_task` que la session est bien rollback sur exception.)

(c) `feature_count` pour `append`/`insert`/`replace` : à l'endroit où upsert/update/delete mettent déjà à jour le compteur, ajouter :

```python
    if mode in ("append", "insert"):
        collection.feature_count = (collection.feature_count or 0) + inserted
    elif mode == "replace":
        collection.feature_count = inserted
```

(d) Statut `invalid` : dans la règle existante qui rejette selon `statusColumn` (quarantaine), ajouter `'invalid'` → rejet avec règle `invalid_key` (lire comment `rejectWhenFalse`/`statusColumn` sont traités et suivre le même chemin `reject(row, rule="invalid_key", …)`).

- [ ] **Step 7 : vérifier**

Run : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests/test_pipeline_quality_l5.py tests/test_collection_writer*.py tests -k "detect_changes or validate_attributes or writer" -v`
Expected : PASS.

- [ ] **Step 8 : commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/app/pipelines/runtime.py core/app/pipelines/collection_writer.py core/tests/
git commit -m "fix(core): detectChanges clé NULL/doublon, validateAttributes, seuil de rejet et pré-contrôle du writer (AUD-080)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : `writer.dataset` et `writer.export` (pas de `feature_count` — RAS) ; route `/collections/{id}/analysis` (écrit via `run_pipeline` + `writer.collection` : bénéficie du pré-contrôle — vérifier que `analysis.py` ne passe jamais de colonne hors `keep`) ; `ops/attrs.py` autres ops à colonne de sortie libre (déjà `_no_clash`).

---

### Task 5 : Planification et déclencheurs fiables + alerte notifiée au groupe (AUD-084, AUD-130 partiel) — migration 0087

**Files :**
- Modify : `core/app/configs/schemas.py` (`PipelineRefreshPolicy` l.347-360)
- Modify : `core/app/configs/pipeline_validation.py` (l.95-120)
- Modify : `core/app/pipelines/repository.py` (`list_due_pipelines` l.463-520, `create_run`/`create_run_unless_active` l.22/69)
- Modify : `core/app/pipelines/jobs.py` (`run_pipeline_task` l.408, balayage l.464-540)
- Modify : `core/app/pipelines/routes.py` (`get_pipeline_next_run` l.97, `trigger_pipeline_webhook_route` l.341)
- Modify : `core/app/pipelines/service.py` (`run_pipeline_service` l.95, `trigger_pipeline_by_webhook_service` l.275)
- Modify : `core/app/pipelines/models.py` (`PipelineRun`)
- Modify : `core/app/webhooks/triggers.py` (l.130-175)
- Modify : `core/app/sharing/repository.py`, `core/app/alerts/jobs.py` (l.575-592)
- Create : `core/alembic/versions/0087_pipeline_run_idempotency_key.py`
- Test : `core/tests/test_pipeline_schedule_l5.py` (nouveau), `core/tests/test_migration_0087_pipeline_idempotency.py` (nouveau), `core/tests/test_pipeline_routes.py`, `core/tests/test_alert_jobs.py`

**Interfaces :**
- Consumes : `croniter`, `zoneinfo.ZoneInfo`, `User.erased_at`, `ItemShare`, `GroupMember`.
- Produces : `PipelineRefreshPolicy.timezone: str = "UTC"` ; `MIN_SCHEDULE_INTERVAL_MINUTES = 5` ; `CIRCUIT_BREAKER_FAILURES = 3` ; `pipeline_runs.idempotency_key varchar(128) NULL` + index unique partiel `ux_pipeline_runs_idempotency (pipeline_item_id, idempotency_key) WHERE idempotency_key IS NOT NULL` ; `run_pipeline_service(..., idempotency_key: str | None = None) -> str` (renvoie le run existant si la clé est déjà connue) ; `share_recipient_ids(session, *, tenant_id: str, item_id: str) -> list[str]`.

- [ ] **Step 1 : migration — test qui échoue**

`core/tests/test_migration_0087_pipeline_idempotency.py` : copier **intégralement** `core/tests/test_migration_0082_pipeline_heartbeat.py` puis remplacer : le préfixe `heartbeat_` du nom de base par `idem_` ; `command.upgrade(cfg, "0081")` par `command.upgrade(cfg, "<TÊTE_PRÉCÉDENTE>")` (la `down_revision` réelle de 0087) ; chaque `"0082"` par `"0087"` ; `heartbeat_at` par `idempotency_key` ; et ajouter après le premier `command.upgrade(cfg, "0087")` :

```python
        insp = sa.inspect(engine)
        assert "ux_pipeline_runs_idempotency" in {i["name"] for i in insp.get_indexes(TABLE)}
        with engine.begin() as conn:
            conn.execute(sa.text("UPDATE pipeline_runs SET idempotency_key = 'k1'"))
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO pipeline_runs (id, tenant_id, pipeline_item_id, status, "
                    "created_at, idempotency_key) VALUES ('r2', 't1', 'i1', 'queued', now(), 'k1')"
                )
            )
```

(l'assertion « lignes existantes : NULL » devient : `SELECT idempotency_key FROM pipeline_runs` is None avant l'UPDATE.)

Run : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests/test_migration_0087_pipeline_idempotency.py -v` → FAIL (révision 0087 inconnue).

- [ ] **Step 2 : migration**

`core/alembic/versions/0087_pipeline_run_idempotency_key.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.idempotency_key — idempotence du déclencheur webhook (AUD-084).

Revision ID: 0087
Revises: 0082
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0087"
down_revision = "0082"  # remplacer par la tête réelle (`uv run alembic heads`) à l'exécution
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pipeline_runs", sa.Column("idempotency_key", sa.String(128), nullable=True)
    )
    op.create_index(
        "ux_pipeline_runs_idempotency",
        "pipeline_runs",
        ["pipeline_item_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_pipeline_runs_idempotency", table_name="pipeline_runs")
    op.drop_column("pipeline_runs", "idempotency_key")
```

`core/app/pipelines/models.py`, classe `PipelineRun` : ajouter la colonne et l'index (le comparateur modèle↔Alembic l'exige) :

```python
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
```

et dans `__table_args__` (créer le tuple s'il n'existe pas, en conservant les entrées existantes) :

```python
        Index(
            "ux_pipeline_runs_idempotency",
            "pipeline_item_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
            sqlite_where=text("idempotency_key IS NOT NULL"),
        ),
```

Run : test de migration + `uv run pytest tests/test_alembic_model_parity*.py -v` (nom réel : `grep -ln "compare_metadata\|model.*alembic" core/tests/*.py`) → PASS. Puis `ALTER TABLE` manuel sur `postgis-test` (Global Constraints).

- [ ] **Step 3 : tests planification/déclencheurs qui échouent**

`core/tests/test_pipeline_schedule_l5.py` (SQLite, même amorçage que `test_pipeline_routes.py::_make_app`) :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 5 (AUD-084) : fuseau, plancher, circuit-breaker, propriétaire anonymisé,
idempotence du webhook."""

from datetime import UTC, datetime, timedelta

import pytest

from app.configs.schemas import PipelineRefreshPolicy
from app.pipelines import repository as pipelines_repo
from app.pipelines.models import PipelineRun
from tests.test_pipeline_routes import (
    _defer_collector,
    _make_app,
    _promote_owner_to_admin,
    _seed_webhook_pipeline,
)


def test_refresh_policy_validates_timezone():
    PipelineRefreshPolicy(enabled=True, cron="0 6 * * *", timezone="Europe/Paris")
    with pytest.raises(ValueError):
        PipelineRefreshPolicy(enabled=True, cron="0 6 * * *", timezone="Mars/Olympus")


def test_refresh_policy_refuses_sub_five_minute_cron():
    with pytest.raises(ValueError, match="5 minutes"):
        PipelineRefreshPolicy(enabled=True, cron="* * * * *")


def test_next_run_honours_timezone(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    r = client.get("/v1/pipelines/next-run", params={"cron": "0 6 * * *", "tz": "Europe/Paris"})
    assert r.status_code == 200
    nxt = datetime.fromisoformat(r.json()["nextRun"])
    assert nxt.utcoffset() in (timedelta(hours=1), timedelta(hours=2))
    assert nxt.hour == 6


def _schedule(client, item_id, cron="*/5 * * * *"):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig

    with client.session_factory() as s:
        cfg = configs_repo.get_config_by_item(s, item_id)
        body = cfg.config.model_dump()
        body["pipeline"]["refreshPolicy"] = {"enabled": True, "cron": cron}
        configs_repo.update_config(
            s, cfg.id, BuilderConfig.model_validate(body), tenant_id=client.tenant.id
        )
        s.commit()


def _add_runs(client, item_id, statuses):
    with client.session_factory() as s:
        for i, st in enumerate(statuses):
            s.add(
                PipelineRun(
                    id=f"r{i}",
                    tenant_id=client.tenant.id,
                    pipeline_item_id=item_id,
                    status=st,
                    created_at=datetime.now(UTC).replace(tzinfo=None)
                    - timedelta(hours=10 - i),
                )
            )
        s.commit()


def test_circuit_breaker_skips_after_three_consecutive_failures(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "failed"])
    with client.session_factory() as s:
        assert pipelines_repo.list_due_pipelines(s) == []


def test_two_failures_then_success_is_still_scheduled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    _add_runs(client, item_id, ["failed", "failed", "succeeded"])
    with client.session_factory() as s:
        assert [i for i, _ in pipelines_repo.list_due_pipelines(s)] == [item_id]


def test_erased_owner_is_never_scheduled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _schedule(client, item_id)
    from app.users.models import User

    with client.session_factory() as s:
        s.get(User, client.user.id).erased_at = datetime.now(UTC).replace(tzinfo=None)
        s.commit()
        assert pipelines_repo.list_due_pipelines(s) == []


def test_webhook_idempotency_key_returns_the_same_run(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    raw = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    _defer_collector(client)
    h = {"Authorization": f"Bearer {raw}", "Idempotency-Key": "evt-42"}
    first = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    second = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["runId"] == second.json()["runId"]


def test_webhook_409_carries_retry_after(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    raw = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    _defer_collector(client)
    h = {"Authorization": f"Bearer {raw}"}
    client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    r = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h)
    assert r.status_code == 409 and r.headers["Retry-After"] == "60"
```

(`_seed_webhook_pipeline`, `_promote_owner_to_admin`, `_defer_collector` existent dans `test_pipeline_routes.py` l.473-560/848 ; si le seed pose déjà une `refreshPolicy`, `_schedule` l'écrase.)

Dans `core/tests/test_alert_jobs.py`, ajouter après `test_audits_carry_the_owner_and_firing_notifies_in_app` :

```python
def test_firing_alert_also_notifies_members_of_shared_groups(env, monkeypatch):
    """AUD-130 : une alerte partagée à un groupe notifie aussi ses membres."""
    from app.notifications.models import Notification
    from app.sharing.models import Group, GroupMember, ItemShare
    from app.users.models import User

    _, Session, tenant, alert_item_id = env
    monkeypatch.setattr(alert_jobs, "send_webhook", lambda *a, **k: None)
    with Session() as s:
        owner = s.execute(
            text("SELECT owner_id FROM items WHERE id = :i"), {"i": alert_item_id}
        ).scalar_one()
        bob = User(
            id="u-bob",
            tenant_id=tenant.id,
            oidc_sub="bob",
            username="bob",
            first_name="",
            last_name="",
            role_id=s.get(User, owner).role_id,
        )
        s.add(bob)
        s.add(Group(id="g1", tenant_id=tenant.id, name="Équipe", created_by=owner))
        s.flush()
        s.add(GroupMember(group_id="g1", user_id="u-bob", tenant_id=tenant.id))
        s.add(ItemShare(item_id=alert_item_id, group_id="g1", tenant_id=tenant.id, role="viewer"))
        s.commit()
    _run_eval(env)
    with Session() as s:
        recipients = set(
            s.scalars(select(Notification.recipient_user_id).where(Notification.kind == "alert"))
        )
    assert recipients == {owner, "u-bob"}
```

(vérifier les champs obligatoires réels de `User` et `Group` — `grep -n "mapped_column" core/app/users/models.py core/app/sharing/models.py` — et compléter les arguments manquants.)

Run : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests/test_pipeline_schedule_l5.py tests/test_alert_jobs.py -k "shared_groups or schedule or circuit or erased or idempotency or retry_after or timezone or cron" -v` → FAIL.

- [ ] **Step 4 : politique de planification**

`core/app/configs/schemas.py`, `PipelineRefreshPolicy` : ajouter

```python
    # AUD-084 : fuseau IANA d'interprétation du cron (06:00 « heure de Paris »).
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _min_interval(self) -> "PipelineRefreshPolicy":
        import croniter as _croniter

        if not _croniter.croniter.is_valid(self.cron):
            return self  # la validation existante (pipeline_validation) produit l'erreur
        it = _croniter.croniter(self.cron, datetime(2026, 1, 5, tzinfo=UTC))
        first = it.get_next(datetime)
        if (it.get_next(datetime) - first) < timedelta(minutes=MIN_SCHEDULE_INTERVAL_MINUTES):
            raise ValueError(
                f"planification trop fréquente : intervalle minimal {MIN_SCHEDULE_INTERVAL_MINUTES} "
                "minutes (le balayage tourne toutes les 5 minutes)"
            )
        return self
```

avec `MIN_SCHEDULE_INTERVAL_MINUTES = 5` au niveau module et les imports `datetime, timedelta, UTC`, `field_validator`, `model_validator` s'ils manquent. Un échantillon de deux occurrences ne voit pas un cron irrégulier (`0,1 * * * *`) : échantillonner 20 occurrences et prendre l'écart minimal :

```python
        ticks = [it.get_next(datetime) for _ in range(20)]
        gap = min(b - a for a, b in zip(ticks, ticks[1:], strict=False))
        if gap < timedelta(minutes=MIN_SCHEDULE_INTERVAL_MINUTES):
```

(remplacer les lignes `first`/`if` par ce bloc.) Attention : une config **existante** en base avec un cron `* * * * *` ne doit pas casser sa lecture — la validation « stricte à l'écriture seulement » existe déjà (P29, `pipeline_validation.py`) : placer ce contrôle d'intervalle **dans `pipeline_validation.py`** (écriture) plutôt que dans le modèle si le modèle est aussi utilisé en lecture (`grep -n "PipelineRefreshPolicy" core/app -r`). Le test `test_refresh_policy_refuses_sub_five_minute_cron` cible alors la fonction de validation d'écriture : l'adapter en conséquence (appeler la fonction réelle de `pipeline_validation.py` l.95-120).

- [ ] **Step 5 : balayage — fuseau, circuit-breaker, propriétaire anonymisé**

`core/app/pipelines/repository.py`, en tête : `CIRCUIT_BREAKER_FAILURES = 3` et `from zoneinfo import ZoneInfo`. Dans `list_due_pipelines` :

(a) filtrer les propriétaires anonymisés dès les candidats :

```python
    erased = set(
        session.scalars(
            select(Item.id)
            .join(User, User.id == Item.owner_id)
            .where(Item.id.in_([c[0] for c in candidates]), User.erased_at.is_not(None))
        )
    )
    candidates = [c for c in candidates if c[0] not in erased]
```

(b) circuit-breaker : charger les `CIRCUIT_BREAKER_FAILURES` derniers runs terminés par item :

```python
def _recent_terminal_statuses(session: Session, item_ids: list[str]) -> dict[str, list[str]]:
    if not item_ids:
        return {}
    rn = (
        func.row_number()
        .over(partition_by=PipelineRun.pipeline_item_id, order_by=PipelineRun.created_at.desc())
        .label("rn")
    )
    sub = (
        select(PipelineRun.pipeline_item_id, PipelineRun.status, rn)
        .where(
            PipelineRun.pipeline_item_id.in_(item_ids),
            PipelineRun.status.in_(("succeeded", "failed", "cancelled")),
        )
        .subquery()
    )
    out: dict[str, list[str]] = {}
    for item_id, status in session.execute(
        select(sub.c.pipeline_item_id, sub.c.status)
        .where(sub.c.rn <= CIRCUIT_BREAKER_FAILURES)
        .order_by(sub.c.pipeline_item_id, sub.c.rn)
    ):
        out.setdefault(item_id, []).append(status)
    return out
```

et dans la boucle, avant le calcul du prochain tick :

```python
        recent = recent_by_item.get(item_id, [])
        if len(recent) == CIRCUIT_BREAKER_FAILURES and all(s == "failed" for s in recent):
            # AUD-084 : circuit ouvert — plus de run planifié tant qu'un run manuel n'a pas
            # réussi (le propriétaire est notifié à chaque échec, pas à chaque tick).
            continue
```

(`recent_by_item = _recent_terminal_statuses(session, [c[0] for c in candidates])` avant la boucle.)

(c) fuseau : remplacer les deux `croniter.croniter(policy.cron, X)` par `croniter.croniter(policy.cron, X.astimezone(ZoneInfo(policy.timezone)))` (croniter renvoie alors un datetime aware dans ce fuseau, comparable à `now` UTC).

`core/app/pipelines/routes.py`, `get_pipeline_next_run` : ajouter `tz: str = Query("UTC")`, valider par `ZoneInfo(tz)` (400 si inconnu), et calculer `croniter.croniter(cron, datetime.now(ZoneInfo(tz)))`.

- [ ] **Step 6 : notification de succès seulement au rétablissement**

`core/app/pipelines/jobs.py`, l.408 : remplacer `_notify(factory, tenant_id=tenant_id, item_id=item_id, status="success")` par :

```python
        # AUD-084 : un pipeline planifié toutes les 5 min ne notifie plus chaque succès —
        # seulement le rétablissement après un échec (les échecs restent tous notifiés).
        if _previous_run_failed(factory, item_id=item_id, run_id=run_id):
            _notify(factory, tenant_id=tenant_id, item_id=item_id, status="success")
```

et ajouter :

```python
def _previous_run_failed(session_factory, *, item_id: str, run_id: str) -> bool:
    try:
        with request_scoped_session(session_factory) as session:
            prev = session.scalar(
                select(PipelineRun.status)
                .where(
                    PipelineRun.pipeline_item_id == item_id,
                    PipelineRun.id != run_id,
                    PipelineRun.status.in_(("succeeded", "failed")),
                )
                .order_by(PipelineRun.created_at.desc())
                .limit(1)
            )
        return prev == "failed"
    except Exception:  # best-effort, comme _notify
        return False
```

Un run **manuel** réussi notifiait aussi : l'utilisateur voit déjà le résultat dans le panneau d'exécution ; même règle. Vérifier les tests existants qui attendent une notification de succès (`grep -rn "status=\"success\"\|'success'" core/tests/test_pipeline_jobs*.py`) et les adapter (précéder d'un run `failed`).

- [ ] **Step 7 : idempotence et 409 du webhook**

`core/app/pipelines/service.py`, `run_pipeline_service` : ajouter `idempotency_key: str | None = None` ; en tête, après les contrôles d'accès :

```python
    if idempotency_key is not None:
        existing = session.scalar(
            select(PipelineRun.id).where(
                PipelineRun.pipeline_item_id == item_id,
                PipelineRun.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            return existing
```

et passer `idempotency_key` jusqu'à `create_run_unless_active(..., idempotency_key=...)` → `create_run(..., idempotency_key=...)` qui pose `run.idempotency_key`. Le 409 « déjà en cours » : ajouter `headers={"Retry-After": "60"}` à l'`HTTPException(409, …)` existante. `trigger_pipeline_by_webhook_service` gagne le même paramètre et le transmet. Route `/trigger` :

```python
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
```

transmis au service.

`core/app/webhooks/triggers.py` (l.130-175) : le déclencheur S3 transmet les paramètres de l'objet **seulement s'ils sont déclarés** par le pipeline (sinon `resolve_params` refuse) et l'etag comme clé d'idempotence :

```python
        declared = {p.name for p in (payload.parameters or [])}
        event_params = {
            k: v
            for k, v in {"objectKey": key, "etag": etag, "bucket": bucket}.items()
            if k in declared and v is not None
        }
        run_pipeline_service(
            session,
            user=owner,
            item_id=item_id,
            defer_task=defer_task,
            actor_kind="trigger",
            params=event_params or None,
            idempotency_key=f"s3:{bucket}/{key}@{etag}" if etag else None,
        )
```

(noms réels de `key`/`etag`/`bucket`/`payload`/`owner` à lire dans la boucle — l'etag est présent dans l'événement S3 `Records[].s3.object.eTag` ; tronquer la clé à 128 caractères : `[:128]`.)

- [ ] **Step 8 : alerte notifiée au groupe**

`core/app/sharing/repository.py`, ajouter :

```python
def share_recipient_ids(session: Session, *, tenant_id: str, item_id: str) -> list[str]:
    """Membres actifs (non anonymisés) des groupes avec lesquels l'item est partagé."""
    return list(
        session.scalars(
            select(GroupMember.user_id)
            .join(ItemShare, ItemShare.group_id == GroupMember.group_id)
            .join(User, User.id == GroupMember.user_id)
            .where(
                ItemShare.item_id == item_id,
                ItemShare.tenant_id == tenant_id,
                User.erased_at.is_(None),
            )
            .distinct()
        )
    )
```

`core/app/alerts/jobs.py` l.575-592 : remplacer l'appel unique par une boucle :

```python
            if (
                owner_id is not None
                and not retry
                and (notify_status == "failed" or new_state == "firing")
            ):
                message = notify_error or _render_message(
                    payload, rule_name=rule_name, value=value, state=new_state
                )
                # AUD-130 : propriétaire + membres des groupes de partage.
                recipients = {owner_id, *share_recipient_ids(
                    session, tenant_id=tenant_id, item_id=item_id
                )}
                for recipient in sorted(recipients):
                    notify_best_effort(
                        _session_factory(),
                        tenant_id=tenant_id,
                        recipient_user_id=recipient,
                        kind="alert",
                        status="failure",
                        item_id=item_id,
                        item_resource_type="alert",
                        item_title=rule_name,
                        error=message,
                    )
```

avec `from app.sharing.repository import share_recipient_ids`. Vérifier par `uv run lint-imports` que `alerts → sharing` est autorisé (déjà importé : `app.sharing.authorization`).

- [ ] **Step 9 : vérifier**

Run : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests/test_pipeline_schedule_l5.py tests/test_pipeline_routes.py tests/test_alert_jobs.py tests/test_migration_0087_pipeline_idempotency.py tests -k "pipeline_jobs or webhook or trigger" -v`
Expected : PASS.

- [ ] **Step 10 : commit**

```bash
git add core/alembic/versions/0087_pipeline_run_idempotency_key.py core/app/pipelines/ core/app/configs/schemas.py core/app/configs/pipeline_validation.py core/app/webhooks/triggers.py core/app/sharing/repository.py core/app/alerts/jobs.py core/tests/
git commit -m "fix(core): planification avec fuseau et coupe-circuit, webhook idempotent, alerte notifiée au groupe (AUD-084/130)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : sweep harvest (`app/harvest/repository.list_due_sources`) et `ReportSchedule`/alertes (même cron UTC, même absence de coupe-circuit) — **hors lot**, à consigner en suivi ; `PipelineScheduleEditor` shell (Task 7 : champ fuseau) ; outil MCP qui lance un run (`grep -rn "run_pipeline_service" core/app/mcp`) — signature additive, rien à changer.

---

### Task 6 : Aperçu et diagnostic d'exécution — brouillon non enregistré, sidecar, erreurs 400, nœud fautif, horodatages UTC (AUD-008, AUD-009, AUD-087, AUD-088 F4/F5/F11, AUD-162) — migration 0088

**Files :**
- Modify : `core/app/pipelines/errors.py`, `core/app/pipelines/runtime.py` (`_node_error`, `_prepare`, `_execute_transform_chain` l.895, `preview_pipeline`)
- Modify : `core/app/pipelines/routes.py` (`RunStatus`, `_run_status` l.156, `preview_pipeline_route` l.271, route nouvelle `POST /pipelines/preview`, jetons webhook)
- Modify : `core/app/pipelines/jobs.py` (`RunTracker`, `PostgresRunTracker`, `run_pipeline_task` l.426/450)
- Modify : `core/app/pipelines/sidecar/{app,tracker}.py`
- Modify : `core/app/pipelines/repository.py` (`mark_failed` l.286), `core/app/pipelines/models.py`
- Create : `core/alembic/versions/0088_pipeline_run_failed_node.py`
- Modify (shell) : `shell/src/api/domains/pipelines.hooks.ts`, `shell/src/api/domains/pipelines.ts`, `shell/src/api/types.ts` (l.961, `PipelineRun` l.1795), `shell/src/desktop/DesktopItemClient.ts`, `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`, `shell/src/pages/PipelineBuilderPage.tsx`, `shell/src/i18n/domains/automation.ts`
- Test : `core/tests/test_pipeline_diagnostics_l5.py`, `core/tests/test_migration_0088_pipeline_failed_node.py`, `core/tests/test_pipeline_sidecar_app.py`, `shell/src/api/domains/pipelines.hooks.test.ts`, `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces :**
- Consumes : `0087` (tête précédente), `apiErrorMessage(error, fallback)`.
- Produces : `PipelineRuntimeError(message, *, node_id: str | None = None)` avec attribut `.node_id` ; `pipeline_runs.failed_node_id varchar(64) NULL` ; `RunTracker.mark_failed(error: str, failed_node_id: str | None = None)` ; `RunStatus.failedNodeId: str | None` ; `POST /v1/pipelines/preview?upTo=` (corps `{pipeline, params}` obligatoire, privilège `automation.manage`) ; shell `previewPipeline(pk: string | null, upToNodeId, draft?)`, `PipelineRun.failedNodeId?: string | null`, `previewDraftKey(draft: PipelinePayload): string` ; `isoUtc(dt: datetime | None) -> str | None` (routes.py).

- [ ] **Step 1 : migration 0088**

`core/tests/test_migration_0088_pipeline_failed_node.py` : copie intégrale de `test_migration_0082_pipeline_heartbeat.py` avec `heartbeat_` → `failednode_`, `"0081"` → `"0087"`, `"0082"` → `"0088"`, `heartbeat_at` → `failed_node_id`. Run → FAIL.

`core/alembic/versions/0088_pipeline_run_failed_node.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""pipeline_runs.failed_node_id — nœud fautif d'un run en échec (AUD-087).

Revision ID: 0088
Revises: 0087
Create Date: 2026-10-17
"""

import sqlalchemy as sa

from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("failed_node_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_runs", "failed_node_id")
```

`models.py`, `PipelineRun` : `failed_node_id: Mapped[str | None] = mapped_column(String(64), nullable=True)`. Run test de migration + parité modèle → PASS ; `ALTER TABLE` manuel sur `postgis-test`.

- [ ] **Step 2 : tests cœur qui échouent**

`core/tests/test_pipeline_diagnostics_l5.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 6 : nœud fautif, expression refusée en 400, aperçu d'un brouillon non
enregistré, horodatages UTC explicites."""

from app.configs.schemas import PipelineNode
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.runtime import _node_error
from tests.test_pipeline_routes import _make_app, _seed_preview_pipeline

DRAFT = {
    "nodes": [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "y"}},
        {
            "id": "w1",
            "kind": "writer",
            "op": "writer.export",
            "params": {"format": "csv", "key": "o.csv"},
        },
    ],
    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
}


def test_node_error_carries_the_node_id():
    node = PipelineNode(id="n7", kind="transform", op="transform.filter", params={"expr": "1"})
    assert _node_error(node, Exception("boom")).node_id == "n7"
    assert PipelineRuntimeError("x").node_id is None


def test_unsaved_draft_preview_route(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    seen = {}

    def fake(*, payload, **kw):
        seen["c"] = payload.nodes[0].params["collectionId"]
        return [{"id": 1}]

    monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake)
    r = client.post("/v1/pipelines/preview?upTo=r1", json={"pipeline": DRAFT})
    assert r.status_code == 200 and seen["c"] == "y"


def test_unsaved_draft_preview_requires_a_body(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    assert client.post("/v1/pipelines/preview?upTo=r1", json={}).status_code == 422


def test_preview_maps_sandbox_and_value_errors_to_400(monkeypatch):
    from app.analytics.sql_sandbox import SqlSandboxError  # chemin réel : grep SqlSandboxError

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_preview_pipeline(client)
    for exc in (SqlSandboxError("fonction interdite"), ValueError("param invalide")):

        def fake(*, payload, _e=exc, **kw):
            raise _e

        monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake)
        r = client.post(f"/v1/pipelines/{item_id}/preview?upTo=r1")
        assert r.status_code == 400, exc
```

Vérifier le module réel de `SqlSandboxError` (`grep -rn "class SqlSandboxError" core/app`) et corriger l'import du test.

Ajouter à `core/tests/test_pipeline_sidecar_app.py`, en réutilisant ses fixtures (`client`, `_payload_dict`, `_write_geojson` — lire le fichier) :

```python
def test_sidecar_preview_uses_the_draft_body(client, tmp_path):
    """AUD-162 : le brouillon envoyé prime sur la version stockée."""
    stored = _payload_dict(_write_geojson(tmp_path / "a.geojson", n=1))
    client.put("/pipelines/p1", json=stored)
    draft = _payload_dict(_write_geojson(tmp_path / "b.geojson", n=3))
    r = client.post("/pipelines/p1/preview?upTo=r1", json={"pipeline": draft})
    assert r.status_code == 200 and len(r.json()) == 3
```

(adapter la forme d'appel de `_payload_dict`/`_write_geojson`, la route de dépôt `PUT`/`POST` et l'id du reader à ceux du fichier.)

Run : `cd core && uv run pytest tests/test_pipeline_diagnostics_l5.py tests/test_pipeline_sidecar_app.py -v` → FAIL.

- [ ] **Step 3 : erreur porteuse du nœud**

`core/app/pipelines/errors.py`, remplacer la classe :

```python
class PipelineRuntimeError(Exception):
    """Erreur d'exécution : la tâche procrastinate l'attrape et marque le run 'failed',
    jamais 'zombie'. `node_id` : nœud fautif quand il est connu (AUD-087)."""

    def __init__(self, *args: object, node_id: str | None = None) -> None:
        super().__init__(*args)
        self.node_id = node_id
```

`runtime.py`, `_node_error` : `return PipelineRuntimeError(f"…", node_id=node.id)`. Dans `_execute_transform_chain`, envelopper l'appel l.895 :

```python
        try:
            _validate_node_exprs(conn, node)
        except PipelineRuntimeError as exc:
            exc.node_id = exc.node_id or node.id
            raise
        except Exception as exc:  # SqlSandboxError et voisins : refus métier, jamais un 500
            raise PipelineRuntimeError(
                f"nœud '{node.id}' ({node.op}) : {exc}", node_id=node.id
            ) from exc
```

et autour de `contract.execute(...)`/`pre_check`/compilation : toute `PipelineRuntimeError` levée sans `node_id` reçoit celui du nœud — ajouter après `except duckdb.Error as exc: raise _node_error(node, exc) from exc` :

```python
        except PipelineRuntimeError as exc:
            exc.node_id = exc.node_id or node.id
            raise
```

Même chose dans `_prepare` autour de `reader_fn(...)` (readers) et de la matérialisation `withCollectionId` des nœuds binaires.

- [ ] **Step 4 : traçage du nœud fautif**

`jobs.py` : `RunTracker.mark_failed(self, error: str, failed_node_id: str | None = None) -> None` ; `PostgresRunTracker.mark_failed` transmet à `pipelines_repo.mark_failed(session, run_id=…, error=error, failed_node_id=failed_node_id)` ; `repository.mark_failed(..., failed_node_id: str | None = None)` pose `run.failed_node_id = failed_node_id`. Dans `run_pipeline_task` l.426 : `tracker.mark_failed(str(exc), getattr(exc, "node_id", None))`. `sidecar/tracker.py:84` : même signature, ajoute `failedNodeId=failed_node_id` à `_update`. `retry_pipeline_run_service`/mark_running d'un nouvel essai : vérifier qu'un run rejoué part d'une nouvelle ligne (sinon remettre `failed_node_id = None` dans `mark_running`).

- [ ] **Step 5 : routes**

`routes.py` :

```python
def isoUtc(dt: datetime | None) -> str | None:  # noqa: N802 — nom aligné sur les champs camelCase
    """AUD-088 F11 : les colonnes sont des DateTime naïfs en UTC ; sans suffixe, le
    navigateur les lit en heure locale (décalage d'1-2 h affiché)."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()
```

(nommer `iso_utc` si ruff N802 n'est pas désactivé — préférer `iso_utc`, et l'utiliser partout ci-dessous.) `RunStatus` gagne `failedNodeId: str | None = None` ; `_run_status` utilise `iso_utc(r.started_at)`, `iso_utc(r.finished_at)`, `iso_utc(r.next_retry_at)`, `failedNodeId=r.failed_node_id`. Jetons webhook : `createdAt=iso_utc(token.created_at)`, `lastUsedAt=iso_utc(r.last_used_at)`.

`preview_pipeline_route` : remplacer `except PipelineRuntimeError` par `except (PipelineRuntimeError, ValueError) as exc:` (SqlSandboxError est désormais convertie en amont ; si elle n'hérite pas de `ValueError` et peut fuir d'ailleurs, l'ajouter au tuple).

Nouvelle route, déclarée **avant** `/pipelines/{item_id}/preview` :

```python
class PipelineDraftPreviewRequest(BaseModel):
    pipeline: PipelinePayload
    params: dict[str, Any] | None = None


@router.post("/pipelines/preview")
def preview_unsaved_pipeline_route(
    body: PipelineDraftPreviewRequest,
    upTo: str = Query(...),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """AUD-009 : aperçu d'un pipeline jamais enregistré (pas encore d'item). Même porte que
    la création d'un pipeline ; les lectures restent soumises à can() nœud par nœud."""
    require_privilege(session, user, Privilege.AUTOMATION_MANAGE.value)
    try:
        return preview_pipeline(
            session=session,
            payload=body.pipeline,
            tenant_id=user.tenant_id,
            user=user,
            up_to=upTo,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            params=body.params,
        )
    except (PipelineRuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

(imports `require_privilege`/`Privilege` : reprendre ceux déjà utilisés par la création de pipeline — `grep -n "AUTOMATION_MANAGE" core/app/pipelines/*.py`. La route `/pipelines/{item_id}/preview` vérifie `write` sur l'item : un brouillon sans item ne peut lire que ce que `_prepare` autorise déjà par `can()` sur chaque collection — vérifier que `preview_pipeline` ne contourne aucun contrôle quand `item_id` est absent : il n'en reçoit pas, OK.) Si le mode démo (`is_read_only_mode`) bloque les routes d'écriture par une garde de chemin, vérifier que `POST /pipelines/preview` est traité comme l'aperçu existant.

`sidecar/app.py` l.143 :

```python
    @app.post("/pipelines/{item_id}/preview")
    def preview_pipeline_route(
        item_id: str, upTo: str = Query(...), body: _PreviewBody | None = None
    ) -> list[dict]:
        payload = body.pipeline if body and body.pipeline is not None else store.get(item_id)
```

avec `class _PreviewBody(BaseModel): pipeline: PipelinePayload | None = None` au niveau module.

Run : `cd core && CORE_TEST_DATABASE_URL=… uv run pytest tests/test_pipeline_diagnostics_l5.py tests/test_pipeline_sidecar_app.py tests/test_pipeline_routes.py tests/test_migration_0088_pipeline_failed_node.py -v` → PASS. Régénérer OpenAPI + types TS (Global Constraints).

- [ ] **Step 6 : shell — tests qui échouent**

`shell/src/api/domains/pipelines.hooks.test.ts` (nouveau) :

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import { previewDraftKey } from "./pipelines.hooks";
import type { PipelinePayload } from "../types";

const base: PipelinePayload = {
  nodes: [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "a" } },
  ],
  edges: [],
};

describe("previewDraftKey (AUD-008)", () => {
  it("ignores node positions, titles and notes", () => {
    const moved: PipelinePayload = {
      ...base,
      nodes: [{ ...base.nodes[0], x: 120, y: 40, title: "Lecture" }],
      notes: [{ id: "n", x: 0, y: 0, width: 10, height: 10, label: "x" }],
    };
    expect(previewDraftKey(moved)).toBe(previewDraftKey(base));
  });
  it("changes when a param changes", () => {
    const edited: PipelinePayload = {
      ...base,
      nodes: [{ ...base.nodes[0], params: { collectionId: "b" } }],
    };
    expect(previewDraftKey(edited)).not.toBe(previewDraftKey(base));
  });
});
```

(type réel de `notes` : `PipelineCanvasNote` — aligner les champs sur `shell/src/api/types.ts`.)

Dans `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`, ajouter (en suivant le patron existant du fichier : `QueryClient` + `ItemClientProvider` + client partiel) :

```tsx
it("shows the server error detail (AUD-087)", async () => {
  const client = {
    previewPipeline: vi.fn().mockRejectedValue(
      new ApiError(400, "nœud 'f1' (transform.filter) : colonne inconnue « pop »"),
    ),
  };
  renderPanel(client, { pipelineId: "p1", nodeId: "f1" });
  expect(await screen.findByRole("alert")).toHaveTextContent("colonne inconnue « pop »");
});

it("announces truncation when the row limit is reached", async () => {
  const rows = Array.from({ length: 50 }, (_, i) => ({ id: i }));
  renderPanel({ previewPipeline: vi.fn().mockResolvedValue(rows) }, { pipelineId: "p1", nodeId: "r1" });
  expect(await screen.findByText(/50 premières lignes/)).toBeInTheDocument();
});

it("renders object cells as JSON, not [object Object]", async () => {
  renderPanel(
    { previewPipeline: vi.fn().mockResolvedValue([{ tags: { a: 1 } }]) },
    { pipelineId: "p1", nodeId: "r1" },
  );
  expect(await screen.findByText('{"a":1}')).toBeInTheDocument();
});

it("previews an unsaved pipeline (pipelineId null)", async () => {
  const previewPipeline = vi.fn().mockResolvedValue([{ id: 1 }]);
  renderPanel({ previewPipeline }, { pipelineId: null, nodeId: "r1", draft: DRAFT });
  await screen.findByText("1");
  expect(previewPipeline).toHaveBeenCalledWith(null, "r1", DRAFT);
});
```

(`renderPanel`/`DRAFT` : réutiliser l'helper du fichier s'il existe, sinon l'écrire en tête du fichier sur le modèle des tests existants ; constructeur réel d'`ApiError` : `grep -n "constructor" shell/src/api/ApiError.ts` ou équivalent — adapter les arguments.)

Run : `cd shell && npx vitest run src/api/domains/pipelines.hooks.test.ts src/builder/pipeline/PipelinePreviewPanel.test.tsx` → FAIL.

- [ ] **Step 7 : shell — implémentation**

`shell/src/api/domains/pipelines.hooks.ts` :

```ts
// AUD-008 : la clé d'aperçu ne dépend que de ce qui change le résultat — jamais des
// positions (chaque frame de drag relançait l'aperçu côté serveur), titres ou notes.
export function previewDraftKey(draft: PipelinePayload | undefined): string {
  if (!draft) return "";
  return JSON.stringify({
    nodes: draft.nodes.map(({ id, kind, op, params }) => ({ id, kind, op, params })),
    edges: draft.edges,
    parameters: draft.parameters ?? null,
  });
}

export function usePipelinePreview(
  pipelineId: string | null,
  nodeId: string | null,
  draft?: PipelinePayload,
) {
  const client = useItemClientInternal();
  const key = previewDraftKey(draft);
  const [debouncedKey, setDebouncedKey] = useState(key);
  useEffect(() => {
    const id = setTimeout(() => setDebouncedKey(key), 400);
    return () => clearTimeout(id);
  }, [key]);
  return useQuery({
    queryKey: ["pipeline-preview", pipelineId, nodeId, debouncedKey],
    queryFn: () => client.previewPipeline(pipelineId, nodeId!, draft),
    enabled: nodeId !== null && (pipelineId !== null || draft !== undefined),
    placeholderData: keepPreviousData,
  });
}
```

(imports `useEffect`, `useState` de `react`, `keepPreviousData` de `@tanstack/react-query`. `queryFn` lit `draft` courant au moment de l'exécution — c'est celui de la clé debouncée à 400 ms près ; acceptable.)

`shell/src/api/domains/pipelines.ts` :

```ts
    async previewPipeline(
      pk: string | null,
      upToNodeId: string,
      draft?: PipelinePayload,
    ): Promise<Record<string, unknown>[]> {
      const path = pk === null ? "/pipelines/preview" : `/pipelines/${pk}/preview`;
      return request<Record<string, unknown>[]>(
        "POST",
        `${path}?upTo=${encodeURIComponent(upToNodeId)}`,
        draft !== undefined ? { pipeline: withoutBaseVersion(draft) } : undefined,
      );
    },
```

`shell/src/api/types.ts` l.961 : signature `previewPipeline(pk: string | null, upToNodeId: string, draft?: PipelinePayload)` ; `PipelineRun` (l.1795) : `failedNodeId?: string | null;`. `shell/src/desktop/DesktopItemClient.ts` : même signature ; `pk === null` → lever `new Error("aperçu indisponible avant enregistrement en mode bureau")` (le sidecar stocke par item ; lire la méthode actuelle l.121-131 et garder le reste). Tout autre implémentation d'`ItemClient` (mocks de test : `grep -rln "previewPipeline" shell/src shell/e2e`) : aligner la signature.

`PipelinePreviewPanel.tsx` : prop `pipelineId: string | null` ; erreur :

```tsx
  if (previewQuery.isError)
    return (
      <p role="alert" className="text-sm text-danger">
        {apiErrorMessage(previewQuery.error, t("pipelinePreview.unavailable"))}
      </p>
    );
```

`formatCell` : avant `return String(value);` ajouter

```ts
  if (value !== null && typeof value === "object") return JSON.stringify(value);
```

et, au-dessus du tableau, quand `rows.length >= PREVIEW_LIMIT` (constante `const PREVIEW_LIMIT = 50;` = `limit` serveur) :

```tsx
      {rows.length >= PREVIEW_LIMIT && (
        <p className="text-xs text-ink-2">{t("pipelinePreview.truncated", { count: PREVIEW_LIMIT })}</p>
      )}
```

`automation.ts` : `"pipelinePreview.truncated": "Aperçu limité aux {count} premières lignes."`.

`PipelineBuilderPage.tsx` l.543 : monter le panneau dès qu'un nœud est sélectionné, enregistré ou non :

```tsx
                  {!readOnly && (
                    <PipelinePreviewPanel
                      pipelineId={pk}
                      nodeId={selectedNode.id}
                      draft={draft}
                      isDraftStale={isDraftStale}
                    />
                  )}
```

Nœud fautif : à l'endroit où `validation.nodeErrors` est passé au canevas (l.516), fusionner l'échec du dernier run :

```tsx
  const nodeErrors = useMemo(() => {
    const failed = latestRun?.status === "failed" ? latestRun.failedNodeId : null;
    if (!failed) return validation.nodeErrors;
    return {
      ...validation.nodeErrors,
      [failed]: [...(validation.nodeErrors[failed] ?? []), latestRun?.error ?? ""],
    };
  }, [validation.nodeErrors, latestRun]);
```

et `nodeErrors={nodeErrors}`. (Le badge d'erreur du nœud existe déjà via `errorCount`.)

Run : `cd shell && npx vitest run src/api src/builder/pipeline src/pages/PipelineBuilderPage.test.tsx` → PASS ; `npm run lint && npx tsc --noEmit` → OK.

- [ ] **Step 8 : commit**

```bash
git add core/ shell/src/ shell/src/api/generated/core-schema.d.ts
git commit -m "feat(pipelines): aperçu d'un brouillon non enregistré, nœud fautif et erreurs lisibles (AUD-008/009/087/162)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Vérifier `git show --stat` : uniquement les fichiers de la tâche + `core/openapi.json` + types générés.

Jumelles : aperçu sidecar (fait), `DesktopItemClient` (fait), outil MCP d'aperçu s'il existe (`grep -rn "preview_pipeline" core/app/mcp`) — même conversion d'erreurs ; `VisualQueryWizardPage` utilise `PipelineRunPanel`/aperçu ? (`grep -rn "PipelinePreviewPanel\|usePipelinePreview" shell/src`) — signature additive ; horodatages naïfs des autres domaines (`grep -rn "\.isoformat()" core/app/*/routes.py`) — **hors lot**, consigner.

---

### Task 7 : Éditeur — drop au bon endroit, insertion au milieu d'arête, champs fidèles à l'undo, connexion refusée annoncée, exécution avertie, titre conservé, fuseau de planification, collection cible créable (AUD-087, AUD-088 F1/F2)

**Files :**
- Modify : `shell/src/builder/pipeline/PipelineCanvas.tsx`, `shell/src/builder/pipeline/graphOps.ts` (l.76), `shell/src/builder/pipeline/PipelineNodeInspector.tsx` (l.81-165, 323-340), `shell/src/builder/pipeline/PipelineRunPanel.tsx` (l.153-215), `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`, `shell/src/pages/PipelineBuilderPage.tsx` (l.338-441, 556), `shell/src/lib/useUrlSyncedState.ts`, `shell/src/api/types.ts`, `shell/src/api/domains/pipelines.ts`, `shell/src/i18n/domains/automation.ts`
- Modify (cœur) : `core/app/pipelines/runtime.py` (`describe_pipeline_output`), `core/app/pipelines/routes.py` (route `POST /pipelines/target-collection`)
- Test : `shell/src/builder/pipeline/graphOps.test.ts`, `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`, `shell/src/lib/useUrlSyncedState.test.tsx`, `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`, `core/tests/test_pipeline_target_collection_l5.py`

**Interfaces :**
- Consumes : `create_empty_collection(...)`, `EmptyCollectionColumn`, `get_introspector`, `get_ddl_applier` (`app.collections.routes`), `preview_pipeline` (Task 6), `PIPELINE_OP_DND_TYPE`.
- Produces : `PipelineCanvas` prop `onDropOp?: (op: string, position: { x: number; y: number }) => void` ; `insertNodeOnEdge` place le nœud au milieu ; `PipelineRunPanel` prop `hasUnsavedChanges?: boolean` ; `describe_pipeline_output(**preview_kwargs) -> OutputSchema` (`columns: list[tuple[str, str]]`, `srid: int | None`, `geometry_types: list[str]`) ; `POST /v1/pipelines/target-collection` corps `{title, pipeline, writerNodeId}` → `{collectionId}` (201) ; shell `createPipelineTargetCollection(input: {title: string; pipeline: PipelinePayload; writerNodeId: string}): Promise<{collectionId: string}>`.

- [ ] **Step 1 : tests shell qui échouent**

`graphOps.test.ts`, ajouter :

```ts
it("insertNodeOnEdge places the new node at the edge midpoint (AUD-087)", () => {
  const nodes = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "writer", op: "writer.export", x: 200, y: 100, params: {} },
  ] as PipelineNode[];
  const edges = [{ id: "e", from: "a", to: "b" }];
  const out = insertNodeOnEdge(nodes, edges, "e", {
    id: "n", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {},
  });
  const n = out.nodes.find((x) => x.id === "n")!;
  expect([n.x, n.y]).toEqual([100, 50]);
});
```

`PipelineNodeInspector.test.tsx`, ajouter (patron de rendu du fichier) :

```tsx
it("clearing a numeric field removes the param instead of writing 0", async () => {
  const onChange = vi.fn();
  renderInspector({ op: "transform.buffer", params: { distance: 10 }, onChange });
  const input = screen.getByLabelText(/distance/);
  await userEvent.clear(input);
  expect(onChange).toHaveBeenLastCalledWith(expect.not.objectContaining({ distance: 0 }));
  expect(onChange.mock.lastCall![0].distance).toBeUndefined();
});

it("list fields follow params changed from outside (undo)", () => {
  const { rerender } = renderInspector({ op: "transform.sort", params: { by: [] , keyColumns: ["a"] } });
  rerender(inspectorElement({ op: "transform.sort", params: { keyColumns: ["b"] } }));
  expect(screen.getByDisplayValue("b")).toBeInTheDocument();
});
```

(choisir une op réelle du catalogue de test du fichier ayant un champ `string[]` et un champ numérique — lire les fixtures du fichier ; `renderInspector`/`inspectorElement` : helpers à écrire en tête si absents, sur le modèle des tests existants.)

`useUrlSyncedState.test.tsx` (nouveau ou existant) :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useUrlSyncedState } from "./useUrlSyncedState";

describe("useUrlSyncedState", () => {
  it("keeps location.state when updating the param (AUD-088 : titre perdu)", () => {
    const { result } = renderHook(
      () => ({ s: useUrlSyncedState<string>("tab", null), loc: useLocation() }),
      {
        wrapper: ({ children }) => (
          <MemoryRouter initialEntries={[{ pathname: "/p", state: { title: "Mon pipeline" } }]}>
            {children}
          </MemoryRouter>
        ),
      },
    );
    act(() => result.current.s[1]("run"));
    expect(result.current.loc.search).toBe("?tab=run");
    expect(result.current.loc.state).toEqual({ title: "Mon pipeline" });
  });
});
```

`PipelineRunPanel.test.tsx`, ajouter :

```tsx
it("warns that unsaved changes will not run", () => {
  renderRunPanel({ hasUnsavedChanges: true });
  expect(screen.getByText(/version enregistrée/)).toBeInTheDocument();
});

it("keeps polling a run already active on mount", async () => {
  const getPipelineRuns = vi
    .fn()
    .mockResolvedValueOnce([{ id: "r", status: "running" }])
    .mockResolvedValue([{ id: "r", status: "succeeded" }]);
  vi.useFakeTimers({ shouldAdvanceTime: true });
  renderRunPanel({ client: { getPipelineRuns } });
  await vi.advanceTimersByTimeAsync(2000);
  expect(getPipelineRuns.mock.calls.length).toBeGreaterThanOrEqual(2);
  vi.useRealTimers();
});
```

Run : `cd shell && npx vitest run src/builder/pipeline src/lib/useUrlSyncedState.test.tsx` → FAIL.

- [ ] **Step 2 : shell — implémentation**

`graphOps.ts`, `insertNodeOnEdge` : avant le `return`, positionner le nœud :

```ts
  const from = nodes.find((n) => n.id === edge.from);
  const to = nodes.find((n) => n.id === edge.to);
  const placed =
    from && to
      ? { ...newNode, x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
      : newNode;
  return {
    nodes: [...nodes, placed],
    edges: [...rest, { id: genEdgeId(), from: edge.from, to: placed.id }, downstream],
  };
```

`PipelineCanvas.tsx` : importer `useReactFlow` de `@xyflow/react` et `PIPELINE_OP_DND_TYPE` de `./PipelinePalette` ; ajouter la prop `onDropOp?: (op: string, position: { x: number; y: number }) => void` à `PipelineCanvasInner` ; dans le corps : `const { screenToFlowPosition } = useReactFlow();` ; sur `<ReactFlow …>` :

```tsx
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes(PIPELINE_OP_DND_TYPE)) e.preventDefault();
        }}
        onDrop={(e) => {
          const op = e.dataTransfer.getData(PIPELINE_OP_DND_TYPE);
          if (!op || !onDropOp) return;
          e.preventDefault();
          e.stopPropagation();
          // AUD-087 : coordonnées du flux (pan/zoom compris), pas de l'écran.
          onDropOp(op, screenToFlowPosition({ x: e.clientX, y: e.clientY }));
        }}
```

Connexion refusée : état `const [refusal, setRefusal] = useState<string | null>(null);` ; dans `onConnect`, remplacer les deux `return` silencieux :

```ts
      if (hasIncomingEdge(edges, connection.target, role)) {
        setRefusal(t("pipelineCanvas.connectRefusedIncoming"));
        return;
      }
      if (wouldCreateCycle(nodes, edges, { from: connection.source, to: connection.target })) {
        setRefusal(t("pipelineCanvas.connectRefusedCycle"));
        return;
      }
      setRefusal(null);
```

(appliquer la même chose à `completeConnection`, chemin clavier, s'il a les mêmes gardes) et rendre, à côté du `<p role="status">` existant :

```tsx
      {refusal && (
        <p role="status" className="text-xs text-danger">
          {refusal}
        </p>
      )}
```

`automation.ts` :

```ts
  "pipelineCanvas.connectRefusedIncoming":
    "Connexion refusée : cette entrée du nœud est déjà reliée.",
  "pipelineCanvas.connectRefusedCycle": "Connexion refusée : elle créerait une boucle.",
  "pipelineRun.unsavedWarning":
    "Modifications non enregistrées : « Exécuter » lance la version enregistrée.",
  "pipelineBuilder.createTargetCollection": "Créer une collection à partir de ce flux",
  "pipelineBuilder.createTargetCollectionFailed": "Création de la collection impossible.",
  "pipelineSchedule.timezone": "Fuseau horaire",
```

`PipelineBuilderPage.tsx` : supprimer `onDragOver`/`onDrop` de la `<div>` racine (l.437-441) et passer `onDropOp={onDropOnCanvas}` au `<PipelineCanvas>` (l.505). Passer `hasUnsavedChanges={hasUnsavedChanges}` à `<PipelineRunPanel>` (l.556).

`PipelineNodeInspector.tsx` :
- champ numérique (l.330-336) :

```tsx
          onChange={(e) =>
            setField(
              name,
              prop.type === "number" || prop.type === "integer"
                ? e.target.value === ""
                  ? undefined
                  : Number(e.target.value)
                : e.target.value,
            )
          }
```

et dans `setField`, retirer la clé quand la valeur est `undefined` :

```ts
  function setField(name: string, value: unknown) {
    if (readOnly) return;
    const newParams = { ...params, [name]: value };
    if (value === undefined) delete newParams[name];
    setParams(newParams);
    onChange(newParams);
  }
```

- `StringListField` : remplacer `defaultValue={value.join(", ")}` par un état local resynchronisé :

```tsx
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  useEffect(() => {
    setText((cur) =>
      cur
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .join(", ") === joined
        ? cur
        : joined,
    );
  }, [joined]);
```

et `value={text}` + `onChange={(e) => { setText(e.target.value); onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean)); }}`.
- `JsonField` : resynchroniser quand la prop change et que le brouillon local est valide :

```tsx
  const serialized = JSON.stringify(value ?? (expect === "array" ? [] : {}), null, 2);
  useEffect(() => {
    setDraft(serialized);
    setError(null);
  }, [serialized]);
```

`PipelineRunPanel.tsx` : prop `hasUnsavedChanges?: boolean` ; rendu au-dessus du bouton « Exécuter » :

```tsx
      {hasUnsavedChanges && (
        <p className="text-xs text-warning">{t("pipelineRun.unsavedWarning")}</p>
      )}
```

(`text-warning` : vérifier le token réel dans `styles/tokens.css` — sinon `text-ink-2`.) Et dans `loadRuns`, après `setRuns(latest)` :

```ts
      const s = latest[0]?.status;
      if (s === "queued" || s === "running" || s === "cancel_requested" || s === "retrying") {
        setRunning(true);
        void poll();
      }
```

`useUrlSyncedState.ts` : conserver l'état de navigation :

```ts
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  ...
        { replace: true, state: location.state },
  ...
    [paramName, setSearchParams, location.state],
```

(import `useLocation` de `react-router-dom`.)

`PipelineScheduleEditor.tsx` : ajouter un `<select>` « Fuseau horaire » (options : `UTC`, `Europe/Paris`, plus `Intl.supportedValuesOf("timeZone")` si disponible) écrivant `refreshPolicy.timezone`, et passer `tz` à l'appel `next-run` existant (`grep -n "next-run\|nextRun" shell/src/api/domains/pipelines.ts`). `PipelineRefreshPolicy` (types.ts) : `timezone?: string`.

Run : `cd shell && npx vitest run src/builder/pipeline src/lib src/pages/PipelineBuilderPage.test.tsx && npm run lint` → PASS.

- [ ] **Step 3 : collection cible — test cœur qui échoue**

`core/tests/test_pipeline_target_collection_l5.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 7 (AUD-088 F2) : créer la collection cible d'un writer depuis l'éditeur."""

from app.pipelines import runtime
from app.pipelines.runtime import OutputSchema
from tests.test_pipeline_routes import _make_app, _promote_owner_to_admin

PIPE = {
    "nodes": [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "x"}},
        {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": ""}},
    ],
    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
}


def test_target_collection_maps_types_and_geometry(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    _promote_owner_to_admin(client)
    monkeypatch.setattr(
        "app.pipelines.routes.describe_pipeline_output",
        lambda **kw: OutputSchema(
            columns=[("name", "VARCHAR"), ("pop", "BIGINT"), ("geometry", "GEOMETRY")],
            srid=2154,
            geometry_types=["POLYGON", "MULTIPOLYGON"],
        ),
    )
    captured = {}

    def fake_create(session, **kw):
        captured.update(kw)

        class C:
            id = "c-new"

        return C()

    monkeypatch.setattr("app.pipelines.routes.create_empty_collection", fake_create)
    r = client.post(
        "/v1/pipelines/target-collection",
        json={"title": "Communes", "pipeline": PIPE, "writerNodeId": "w1"},
    )
    assert r.status_code == 201 and r.json() == {"collectionId": "c-new"}
    assert [(c.name, c.sqlType) for c in captured["columns"]] == [
        ("name", "text"),
        ("pop", "bigint"),
    ]
    assert captured["geometry_type"] == "MultiPolygon" and captured["srid"] == 2154


def test_target_collection_refuses_mixed_geometry(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    _promote_owner_to_admin(client)
    monkeypatch.setattr(
        "app.pipelines.routes.describe_pipeline_output",
        lambda **kw: OutputSchema(
            columns=[("geometry", "GEOMETRY")], srid=4326, geometry_types=["POINT", "POLYGON"]
        ),
    )
    r = client.post(
        "/v1/pipelines/target-collection",
        json={"title": "X", "pipeline": PIPE, "writerNodeId": "w1"},
    )
    assert r.status_code == 400


def test_describe_pipeline_output_is_exported():
    assert callable(runtime.describe_pipeline_output)
```

Run → FAIL.

- [ ] **Step 4 : cœur — `describe_pipeline_output` et route**

`runtime.py` : factoriser `preview_pipeline` en extrayant le corps commun dans `_run_preview(*, …, consume: Callable[[Any, str, int | None], T]) -> T` qui fait tout jusqu'à `view_name = view_by_node[up_to]` puis `return consume(conn, view_name, srid_by_node[up_to])` (le `finally` existant inchangé). `preview_pipeline` devient `return _run_preview(..., consume=_rows_consumer(limit))` avec `_rows_consumer` = le code de conversion GeoJSON actuel déplacé tel quel. Ajouter :

```python
@dataclass(frozen=True)
class OutputSchema:
    columns: list[tuple[str, str]]  # (nom, type DuckDB)
    srid: int | None
    geometry_types: list[str]  # ST_GeometryType distincts, ex. ["POLYGON", "MULTIPOLYGON"]


def describe_pipeline_output(**kwargs) -> OutputSchema:
    """Schéma de sortie du nœud `up_to` (mêmes arguments que preview_pipeline, sans
    limit) : sert à créer une collection cible typée (AUD-088 F2)."""

    def consume(conn, view_name: str, srid: int | None) -> OutputSchema:
        cols = [(d[0], d[1]) for d in conn.execute(f"DESCRIBE {_qi(view_name)}").fetchall()]
        types: list[str] = []
        if any(c == "geometry" for c, _ in cols):
            types = [
                r[0]
                for r in conn.execute(
                    f"SELECT DISTINCT ST_GeometryType(geometry)::VARCHAR FROM {_qi(view_name)} "
                    "WHERE geometry IS NOT NULL LIMIT 10"
                ).fetchall()
            ]
        return OutputSchema(columns=cols, srid=srid, geometry_types=types)

    return _run_preview(**kwargs, consume=consume)
```

(le `DESCRIBE` sur la vue d'aperçu reste borné par le délai d'aperçu ; `SELECT DISTINCT` évalue toute la chaîne — même borne temporelle que l'aperçu, acceptable.)

`routes.py` :

```python
_DUCKDB_TO_SQL = {
    "VARCHAR": "text",
    "BOOLEAN": "boolean",
    "TINYINT": "integer",
    "SMALLINT": "integer",
    "INTEGER": "integer",
    "BIGINT": "bigint",
    "HUGEINT": "bigint",
    "FLOAT": "double precision",
    "DOUBLE": "double precision",
    "DATE": "date",
    "TIMESTAMP": "timestamptz",
    "TIMESTAMP WITH TIME ZONE": "timestamptz",
}
_GEOM_MULTI = {
    "POINT": "MultiPoint",
    "MULTIPOINT": "MultiPoint",
    "LINESTRING": "MultiLineString",
    "MULTILINESTRING": "MultiLineString",
    "POLYGON": "MultiPolygon",
    "MULTIPOLYGON": "MultiPolygon",
}


class TargetCollectionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    pipeline: PipelinePayload
    writerNodeId: str


class TargetCollectionCreated(BaseModel):
    collectionId: str


@router.post(
    "/pipelines/target-collection", response_model=TargetCollectionCreated, status_code=201
)
def create_pipeline_target_collection_route(
    body: TargetCollectionRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
) -> TargetCollectionCreated:
    """AUD-088 F2 : crée une collection vide au schéma du flux qui alimente un writer."""
    require_privilege(session, user, Privilege.AUTOMATION_MANAGE.value)
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    pred = next((e.from_ for e in body.pipeline.edges if e.to == body.writerNodeId), None)
    if pred is None:
        raise HTTPException(status_code=400, detail="le writer n'a pas d'entrée")
    try:
        schema = describe_pipeline_output(
            session=session,
            payload=body.pipeline,
            tenant_id=user.tenant_id,
            user=user,
            up_to=pred,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
        )
    except (PipelineRuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    kinds = {_GEOM_MULTI.get(t) for t in schema.geometry_types}
    if None in kinds or len(kinds) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"géométries hétérogènes en sortie ({schema.geometry_types}) : "
            "filtrer par type avant d'écrire",
        )
    columns = [
        EmptyCollectionColumn(name=n, sqlType=_DUCKDB_TO_SQL.get(t.split("(")[0], "text"))
        for n, t in schema.columns
        if n not in ("geometry", "id", "tenant_id", "geom")
    ]
    target = create_empty_collection(
        session,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=body.title,
        columns=columns,
        geometry_type=kinds.pop() if kinds else None,
        srid=schema.srid if kinds else None,
        introspect=introspect,
        apply_ddl=apply_ddl,
    )
    session.commit()
    return TargetCollectionCreated(collectionId=target.id)
```

Vérifier : l'attribut réel de l'origine d'arête (`from_` ou alias `from` — `grep -n "class PipelineEdge" -A6 core/app/configs/schemas.py`) ; `kinds` vide quand pas de géométrie (`set()` → `None` absent, OK) — attention `kinds = {…}` sur liste vide = `set()` : `None in set()` est faux, `len` 0, passe ; que `create_empty_collection` commite ou non (lire l'analyse `analysis.py` : elle n'appelle pas `commit` elle-même → la route commite) ; quota appliqué par `create_empty_collection` (point unique). Importer `describe_pipeline_output`, `create_empty_collection`, `EmptyCollectionColumn`, `get_introspector`, `get_ddl_applier`, `Introspector` comme dans `analysis_routes.py`. `uv run lint-imports` : `pipelines → collections` déjà autorisé (analysis_routes).

Run : `cd core && uv run pytest tests/test_pipeline_target_collection_l5.py tests/test_pipeline_routes.py -v` → PASS. Régénérer OpenAPI + types TS.

- [ ] **Step 5 : shell — bouton dans l'inspecteur du writer**

`shell/src/api/domains/pipelines.ts` (+ union de noms de méthodes et `ItemClient` dans `types.ts`, + `DesktopItemClient` qui lève « indisponible en mode bureau ») :

```ts
    async createPipelineTargetCollection(input: {
      title: string;
      pipeline: PipelinePayload;
      writerNodeId: string;
    }): Promise<{ collectionId: string }> {
      return request<{ collectionId: string }>("POST", "/pipelines/target-collection", {
        ...input,
        pipeline: withoutBaseVersion(input.pipeline),
      });
    },
```

Dans `PipelineBuilderPage.tsx`, sous l'inspecteur, quand `selectedNode.op === "writer.collection" && !readOnly && !selectedNode.params.collectionId` :

```tsx
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={async () => {
                      setTargetError(null);
                      try {
                        const { collectionId } = await client.createPipelineTargetCollection({
                          title: `${title} — sortie`,
                          pipeline: draft,
                          writerNodeId: selectedNode.id,
                        });
                        updateSelectedNodeParams({ ...selectedNode.params, collectionId });
                      } catch (e) {
                        setTargetError(
                          apiErrorMessage(e, t("pipelineBuilder.createTargetCollectionFailed")),
                        );
                      }
                    }}
                  >
                    {t("pipelineBuilder.createTargetCollection")}
                  </Button>
                  {targetError && (
                    <p role="alert" className="text-xs text-danger">
                      {targetError}
                    </p>
                  )}
```

(`const [targetError, setTargetError] = useState<string | null>(null);` ; `title` = variable de titre réelle de la page ; `Button` du kit.) Test : dans `PipelineBuilderPage.test.tsx`, cliquer le bouton avec un client mock renvoyant `{collectionId: "c9"}` et vérifier que le brouillon du writer contient `collectionId: "c9"` (patron de rendu existant du fichier).

Run : `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx src/builder/pipeline && npm run lint && npx tsc --noEmit` → PASS.

- [ ] **Step 6 : commit**

```bash
git add shell/src core/app/pipelines/runtime.py core/app/pipelines/routes.py core/tests/test_pipeline_target_collection_l5.py core/openapi.json
git commit -m "fix(shell): éditeur de pipeline — drop, insertion, champs, connexion refusée, titre, collection cible (AUD-087/088)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : `useUrlTab` (s'appuie sur `useUrlSyncedState` — corrigé du même coup ; vérifier les autres `setSearchParams(..., {replace:true})` qui jetteraient un `state` utile : `grep -rn "replace: true" shell/src`) ; drop par clic palette (`onAddViaPalette`, coordonnées flux déjà relatives — OK) ; insertion clavier d'un nœud sur arête (même `insertNodeOnEdge`).

---

### Task 8 : Lineage visible, gabarits liés à de vraies collections, exemple de widget valide (AUD-086, AUD-022, AUD-173)

**Files :**
- Create : `shell/src/builder/pipeline/LineagePanel.tsx`, `shell/src/builder/pipeline/LineagePanel.test.tsx`
- Modify : `shell/src/api/types.ts` (types `Lineage`, méthode `getLineage`), `shell/src/api/domains/impact.ts` (ou le domaine qui porte `getImpact` l.910), `shell/src/desktop/DesktopItemClient.ts`, `shell/src/pages/ItemDetailPage.tsx` (~l.300), `shell/src/pages/PipelineBuilderPage.tsx`
- Modify : `shell/src/shell/NewItemButton.tsx` (l.240-300), `shell/src/api/domains/items.ts` (l.133-175), `shell/src/builder/templates.ts`
- Modify : `core/app/configs/builder_templates.py`, `core/app/mcp/tools/configs.py` (l.232-248)
- Modify : `examples/external-widget/manifest.json`, `docs/guides/2026-07-13-ecrire-un-widget-web-component.md` (l.18)
- Test : `core/tests/test_builder_templates_bindings.py`, `core/tests/test_external_widget_example.py`, `shell/src/shell/NewItemButton.test.tsx`

**Interfaces :**
- Consumes : `GET /v1/items/{id}/lineage` → `LineageRead{target, nodes[{type,id,title,resourceType,direction}], edges[{from,to}], hiddenCount}` (existant).
- Produces : shell `getLineage(itemId: string): Promise<Lineage>` ; `<LineagePanel itemId={string} />` ; `templateDataSources(templateId: string): string[]` (shell `templates.ts`) ; `createConfigItem({..., bindings?: Record<string, string>})` ; cœur `build_config_from_template(template_id: str, bindings: dict[str, str] | None = None)` ; MCP `create_item(..., bindings: dict[str, str] | None)`.

- [ ] **Step 1 : tests qui échouent**

`core/tests/test_external_widget_example.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-173 : l'exemple livré doit être accepté tel quel par le cœur."""

import json
from pathlib import Path

from app.extensions.schemas import ExtensionCreate

ROOT = Path(__file__).resolve().parents[2]


def test_example_manifest_is_accepted():
    manifest = json.loads((ROOT / "examples/external-widget/manifest.json").read_text())
    ExtensionCreate.model_validate(manifest)
```

(vérifier le nom réel du modèle d'entrée — `grep -n "^class" core/app/extensions/schemas.py` — et si le manifeste n'a pas la forme exacte du corps de création, valider seulement `ModuleUrl` sur `manifest["moduleUrl"]`.)

`core/tests/test_builder_templates_bindings.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""AUD-022 : un gabarit instancié pointe sur les collections choisies, pas sur des slugs
fictifs."""

import pytest

from app.configs.builder_templates import build_config_from_template, template_data_sources

TEMPLATE = "incidents"  # id réel d'un gabarit à source de données — vérifier templates.data.json


def test_every_template_data_source_is_bindable():
    for slug in template_data_sources(TEMPLATE):
        cfg = build_config_from_template(TEMPLATE, bindings={slug: "col-123"})
        assert slug not in cfg.model_dump_json()
        assert "col-123" in cfg.model_dump_json()


def test_unknown_binding_is_refused():
    with pytest.raises(ValueError):
        build_config_from_template(TEMPLATE, bindings={"inexistant": "col-1"})
```

`LineagePanel.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../../api/ItemClientContext";
import { LineagePanel } from "./LineagePanel";

describe("LineagePanel (AUD-086)", () => {
  it("lists upstream and downstream items as links", async () => {
    const client = {
      getLineage: vi.fn().mockResolvedValue({
        target: { id: "p1" },
        nodes: [
          { type: "collection", id: "c1", title: "Communes", resourceType: null, direction: "upstream" },
          { type: "item", id: "m1", title: "Carte", resourceType: "map", direction: "downstream" },
        ],
        edges: [],
        hiddenCount: 1,
      }),
    };
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ItemClientProvider client={client as never}>
            <LineagePanel itemId="p1" />
          </ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("link", { name: "Communes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Carte" })).toHaveAttribute("href", "/items/m1");
    expect(screen.getByText(/1 élément masqué/)).toBeInTheDocument();
  });
});
```

(chemin réel d'`ItemClientProvider` : reprendre l'import de `PipelinePreviewPanel.test.tsx` ; route de détail d'une collection : `grep -n "path:" shell/src/shell/routes.tsx | grep -i collection`.)

Run : `cd core && uv run pytest tests/test_external_widget_example.py tests/test_builder_templates_bindings.py -v` ; `cd shell && npx vitest run src/builder/pipeline/LineagePanel.test.tsx` → FAIL.

- [ ] **Step 2 : exemple de widget**

`examples/external-widget/manifest.json` : `"moduleUrl": "https://example.org/geostudio/external-widget/widget.js"`. Guide l.18 : même URL, et ajouter sous l'exemple la phrase « `moduleUrl` doit être une URL **https absolue** : le cœur refuse un chemin relatif ou `http://`. » (retirer la mention isolée de la l.116 si elle devient redondante). Le README de l'exemple (`examples/external-widget/README*`) : indiquer de remplacer l'URL par celle où `widget.js` est servi en https.

- [ ] **Step 3 : liaisons de gabarit (cœur)**

`core/app/configs/builder_templates.py` : lire le module (comment il charge `templates.data.json` et où apparaissent les slugs de source). Ajouter :

```python
def template_data_sources(template_id: str) -> list[str]:
    """Slugs de collection référencés par le gabarit (à lier à de vraies collections)."""
    raw = _template_raw(template_id)  # dict brut du gabarit (fonction de chargement existante)
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in _DATA_SOURCE_KEYS and isinstance(v, str) and v not in found:
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(raw)
    return found


def _bind(node, bindings: dict[str, str]):
    if isinstance(node, dict):
        return {
            k: bindings.get(v, v) if k in _DATA_SOURCE_KEYS and isinstance(v, str) else _bind(v, bindings)
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_bind(v, bindings) for v in node]
    return node
```

avec `_DATA_SOURCE_KEYS` = l'ensemble des clés qui portent un slug de collection dans `templates.data.json` (le lire : ex. `{"collectionId", "collection"}` — **ne retenir que les clés réellement présentes**). `build_config_from_template(template_id, bindings=None)` : si `bindings` est fourni, refuser toute clé absente de `template_data_sources(template_id)` (`ValueError(f"source de gabarit inconnue : {k}")`) puis appliquer `_bind` au dict brut avant `BuilderConfig.model_validate`. Si le gabarit nomme la source par un slug et la couche par `{"source": "incidents"}` en plus de l'id, inclure les deux clés.

MCP `create_item` (`mcp/tools/configs.py:232-248`) : ajouter l'argument `bindings: dict[str, str] | None = None` au schéma de l'outil et le passer à `build_config_from_template`. **Avant** l'appel, vérifier que chaque collection liée est lisible par l'utilisateur (`get_collection_for_read` ou l'équivalent déjà utilisé par les outils MCP — `grep -rn "def get_collection_for_read\|can(" core/app/mcp/tools/*.py | head`) : un id de collection d'un autre tenant ne doit pas se retrouver dans une config.

Run : `cd core && uv run pytest tests/test_builder_templates_bindings.py tests/test_external_widget_example.py tests -k "mcp and create_item" -v` → PASS.

- [ ] **Step 4 : liaisons de gabarit (shell)**

`shell/src/builder/templates.ts` : exporter

```ts
const DATA_SOURCE_KEYS = new Set(["collectionId"]); // aligner sur _DATA_SOURCE_KEYS du cœur

export function templateDataSources(templateId: string): string[] {
  const found: string[] = [];
  const walk = (n: unknown): void => {
    if (Array.isArray(n)) return n.forEach(walk);
    if (n && typeof n === "object")
      for (const [k, v] of Object.entries(n)) {
        if (DATA_SOURCE_KEYS.has(k) && typeof v === "string") {
          if (!found.includes(v)) found.push(v);
        } else walk(v);
      }
  };
  walk(getTemplate(templateId)); // accesseur existant du module — lire templates.ts
  return found;
}

export function bindTemplate<T>(config: T, bindings: Record<string, string>): T {
  const bind = (n: unknown): unknown => {
    if (Array.isArray(n)) return n.map(bind);
    if (n && typeof n === "object")
      return Object.fromEntries(
        Object.entries(n).map(([k, v]) => [
          k,
          DATA_SOURCE_KEYS.has(k) && typeof v === "string" ? (bindings[v] ?? v) : bind(v),
        ]),
      );
    return n;
  };
  return bind(config) as T;
}
```

`shell/src/api/domains/items.ts`, `createConfigItem` : nouveau champ d'entrée `bindings?: Record<string, string>` ; là où le gabarit est instancié, appliquer `bindTemplate(config, input.bindings ?? {})`.

`NewItemButton.tsx` (sélecteur de gabarit l.240-300) : sous le select de gabarit, pour chaque `slug` de `templateDataSources(templateId)`, un `CollectionParamSelect`-like (réutiliser le sélecteur de collection existant du dépôt : `grep -rln "CollectionParamSelect\|CollectionPicker" shell/src | head`) libellé `t("newItem.bindSource", { source: slug })` ; état `bindings` ; bouton « Créer » désactivé tant qu'une source n'est pas liée ; passer `bindings` à `createConfigItem`. Clé i18n dans le domaine qui porte déjà les textes de `NewItemButton` : `"newItem.bindSource": "Collection pour « {source} »"`.

`NewItemButton.test.tsx` : ajouter un test — choisir le gabarit `incidents`, vérifier que « Créer » est désactivé, choisir une collection pour chaque source, cliquer, vérifier `createConfigItem` appelé avec `bindings: { incidents: "<id choisi>" }` (adapter au gabarit et au mock de la liste de collections du fichier).

- [ ] **Step 5 : lineage dans le shell**

`types.ts` :

```ts
export interface LineageNode {
  type: "item" | "collection";
  id: string;
  title: string;
  resourceType: string | null;
  direction: "upstream" | "downstream";
}
export interface Lineage {
  target: { id: string };
  nodes: LineageNode[];
  edges: { from: string; to: string }[];
  hiddenCount: number;
}
```

(aligner exactement sur `LineageRead` — lire `core/app/lineage/routes.py` et les types générés `core-schema.d.ts` ; si `type` vaut autre chose, utiliser les valeurs réelles.) Méthode `getLineage(itemId)` dans le domaine qui porte `getImpact` :

```ts
    async getLineage(itemId: string): Promise<Lineage> {
      return request<Lineage>("GET", `/items/${itemId}/lineage`);
    },
```

(+ `DesktopItemClient` : `{ target: { id: itemId }, nodes: [], edges: [], hiddenCount: 0 }`.) Hook `useLineage(itemId)` à côté de `useImpact` (`impact.hooks.ts`), clé `["lineage", itemId]`.

`LineagePanel.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useLineage } from "../../api/domains/impact.hooks";
import { LoadingState } from "../../ui/kit/LoadingState";
import { plural, t } from "../../i18n";
import "../../i18n/domains/automation";

function href(n: { type: string; id: string }): string {
  return n.type === "collection" ? `/collections/${n.id}` : `/items/${n.id}`;
}

export function LineagePanel({ itemId }: { itemId: string }) {
  const q = useLineage(itemId);
  if (q.isLoading) return <LoadingState label={t("lineage.loading")} />;
  if (q.isError || !q.data) return null;
  const up = q.data.nodes.filter((n) => n.direction === "upstream");
  const down = q.data.nodes.filter((n) => n.direction === "downstream");
  const list = (label: string, nodes: typeof up) => (
    <div>
      <p className="text-xs font-medium text-ink-2">{label}</p>
      {nodes.length === 0 ? (
        <p className="text-xs text-ink-2">{t("lineage.none")}</p>
      ) : (
        <ul className="text-sm">
          {nodes.map((n) => (
            <li key={`${n.type}-${n.id}`}>
              <Link to={href(n)}>{n.title}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
  return (
    <section aria-label={t("lineage.title")} className="flex flex-col gap-2">
      {list(t("lineage.upstream"), up)}
      {list(t("lineage.downstream"), down)}
      {q.data.hiddenCount > 0 && (
        <p className="text-xs text-ink-2">
          {plural(q.data.hiddenCount, "lineage.hidden")}
        </p>
      )}
    </section>
  );
}
```

(chemins réels de `LoadingState`, `plural` et sa signature : `grep -n "export function plural" shell/src/i18n/*.ts` ; route réelle d'une collection.) Clés i18n (`automation.ts`) : `"lineage.title": "Lignée"`, `"lineage.loading": "Chargement de la lignée…"`, `"lineage.upstream": "Sources"`, `"lineage.downstream": "Utilisé par"`, `"lineage.none": "Aucun"`, `"lineage.hidden.one": "{count} élément masqué (droits insuffisants)"`, `"lineage.hidden.other": "{count} éléments masqués (droits insuffisants)"` (forme plurielle selon la convention réelle du dépôt).

Montage : `ItemDetailPage.tsx`, après le `</dl>` de `ItemFacts` (~l.300) : `<LineagePanel itemId={item.id} />` ; `PipelineBuilderPage.tsx`, dans la colonne latérale quand `pk !== null` (après l'historique de configuration) : `<LineagePanel itemId={pk} />`.

Run : `cd shell && npx vitest run src/builder/pipeline/LineagePanel.test.tsx src/shell/NewItemButton.test.tsx src/pages && npm run lint && npx tsc --noEmit` → PASS.

- [ ] **Step 6 : commit**

```bash
git add examples/external-widget docs/guides/2026-07-13-ecrire-un-widget-web-component.md core/app/configs/builder_templates.py core/app/mcp/tools/configs.py core/tests/test_builder_templates_bindings.py core/tests/test_external_widget_example.py shell/src core/openapi.json
git commit -m "feat: lignée visible, gabarits liés à de vraies collections, exemple de widget valide (AUD-086/022/173)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Jumelles : `useImpact`/`ImpactConfirmDialog` (même domaine, inchangé) ; route lineage côté collection `/collections/{id}/lineage` — page de détail de collection : monter le même panneau si une page de détail de collection existe (`grep -rn "CollectionDetail" shell/src/pages`) en ajoutant une prop `kind: "item" | "collection"` ; gabarits instanciés par le copilote (`create_form_app` — `grep -n "build_config_from_template" core/app -r`) : même paramètre `bindings` si le copilote passe un gabarit.

---

### Task 9 : Clôture — portes de qualité, E2E complète, jumelles, artefacts régénérés

**Files :** aucun nouveau ; `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts` si diff.

**Interfaces :**
- Consumes : tout ce qui précède.
- Produces : branche verte, liste des lignes d'inventaire et des jumelles pour le contrôleur.

- [ ] **Step 1 : régénération OpenAPI + types**

Run : `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && cd ../shell && npm run gen:api-types && git status --short core/openapi.json shell/src/api/generated/`
Expected : diff vide (déjà régénérés aux Tasks 6-8) ; sinon committer `chore(api): régénère OpenAPI et types TS`.

- [ ] **Step 2 : portes cœur**

Run :
```bash
cd core && uv run ruff check . && uv run ruff format --check . \
 && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles app/net_pin.py \
 && uv run lint-imports \
 && CORE_TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5433/geostudio_test_l5 uv run pytest --cov=app --cov-report=xml -q \
 && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```
Expected : tout vert. Échecs intermittents connus (`test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented`) : rejouer isolément avant de s'imputer quoi que ce soit. `test_feature_inventory.py` échoue tant que le contrôleur n'a pas ajouté les lignes du Step 5 : **attendu**, à signaler.

- [ ] **Step 3 : portes shell**

Run :
```bash
cd shell && rm -rf dist dist-export && npm run lint && npm run format:check \
 && npm run test -- --coverage && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
 && npm run build && node scripts/check-bundle-size.mjs dist/.vite/manifest.json .bundle-size-threshold \
 && npm run e2e
```
Expected : tout vert ; E2E **entièrement** verte (aucun échec « connu »). Un mock E2E de `POST /pipelines/{id}/preview` ou de `GET /pipelines/{id}/runs` sans `failedNodeId` reste compatible (champ optionnel) ; le nouveau `POST /pipelines/preview` doit être mocké dans `shell/e2e/mocks.ts` si un spec ouvre l'éditeur sur un pipeline neuf avec un nœud sélectionné (sinon le handler générique répond une forme fausse — piège du 2026-09-06).

- [ ] **Step 4 : pre-commit**

Run : `uvx pre-commit run --all-files` → 8 hooks verts (dont `check_claude_md_size.py`, non touché).

- [ ] **Step 5 : remise au contrôleur**

Lister dans le rapport (sans modifier `docs/revue/*`) :
- lignes d'inventaire à ajouter à `docs/revue/inventaire-fonctionnalites.jsonl` : `POST /v1/pipelines/preview` (aperçu d'un brouillon non enregistré), `POST /v1/pipelines/target-collection` (collection cible d'un writer), en-tête `Idempotency-Key` de `POST /v1/pipelines/{id}/trigger` (extension de surface existante), paramètre `tz` de `GET /v1/pipelines/next-run`, outil MCP `create_item` (paramètre `bindings`), ops `transform.validateGeometry`/`measure`/`spatialJoin` si l'inventaire recense les ops ; route shell : aucune nouvelle (panneau monté sur pages existantes) ;
- matrice FME : lignes GeometryValidator, AreaCalculator/LengthCalculator, SpatialRelator-avec-attributs (`docs/revue/…matrice-fme…`) à passer `implemented` par le contrôleur ;
- jumelles vérifiées (cocher chacune avec le fichier:ligne lu) : outil d'analyse `spatialJoin` (non basculé, raison), lecteurs paginés autres qu'arcgisonline/WFS, balayages harvest/ReportSchedule (même cron UTC sans coupe-circuit — suivi), horodatages naïfs des autres domaines (suivi), aperçu MCP, `DesktopItemClient`, sidecar, `useUrlTab`, gabarits copilote ;
- reportés (cf. en-tête) et écarts consignés en cours d'exécution (Tasks 1 Step 6, 2 Step 7, 4 Step 4).

- [ ] **Step 6 : vérification finale de l'historique**

Run : `git log --format='%h %s%n%b' origin/dev..HEAD | grep -c "Co-Authored-By: Claude Sonnet 5.5"` = nombre de commits du lot ; `git show --stat` de chacun : aucun fichier hors périmètre (en particulier `CLAUDE.md`, `docs/revue/*`, historique d'exécution).

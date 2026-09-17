# Vague 1 des transformers `planned_duckdb` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter 15 nouvelles op `transform.*` au catalogue de pipeline (`GET /pipelines/ops`),
couvrant 18 des 90 lignes `planned_duckdb` de la matrice FME→GeoStudio, en suivant exactement le
patron déjà prouvé par les 19 op `OperationContract` existantes.

**Architecture:** Chaque op = une classe de params Pydantic (`ops/schemas.py`) + une fonction pure
`_compile_xxx(params, *, input_view, join_view, input_srid) -> str` (`compiler.py`) + une entrée
`OperationContract` (`ops/contracts.py`). Zéro nouveau fichier, zéro nouveau champ sur
`OperationContract`, zéro changement `shell/` (le catalogue et l'inspecteur de nœud sont déjà
génériques).

**Tech Stack:** Python 3.12, Pydantic v2, DuckDB 1.5.5 + extension `spatial` (community, chargée par
le runtime).

## Global Constraints

- Chaque `_compile_xxx` a exactement la signature `(params: dict, *, input_view: str, join_view:
  str | None = None, input_srid: int | None = None) -> str` — fonction pure, aucune connexion
  DuckDB touchée (patron des 19 op existantes, `core/app/pipelines/compiler.py`).
- `engine="duckdb"`, `engine_license="MIT (DuckDB)"` sur les 15 entrées `OperationContract` —
  aucune n'utilise d'extension DuckDB tierce à licence différente de celle déjà en usage.
  `execution_model` reste au défaut `"in_process"`, `is_copyleft` au défaut `False`.
- Aucun fichier sous `shell/` n'est modifié dans ce plan.
- Toute fonction DuckDB spatial utilisée dans ce plan a été vérifiée par exécution réelle contre
  DuckDB 1.5.5 + extension `spatial` (commit `eb1e57c`) pendant l'écriture de ce plan — jamais
  depuis la documentation ou la mémoire (piège CLAUDE.md n°3). Les 3 anomalies trouvées sont
  documentées en §0 et câblées dans les tâches qui suivent, pas contournées.
- Régénérer `openapi.json` + `core-schema.d.ts` en Tâche 6 (diff **non vide** attendu — 15 nouveaux
  schémas de params).
- Portes de qualité (`ruff check`, `ruff format --check`, `mypy --strict` si `app.pipelines` est
  dans son périmètre, `lint-imports`, suite complète `core`) à repasser en Tâche 6.

---

## §0 — Déviations vérifiées par rapport au design (`2026-09-17-vague1-transformers-duckdb-design.md`)

Trois écarts découverts en vérifiant chaque signature DuckDB contre une connexion réelle avant
d'écrire ce plan (piège CLAUDE.md n°3/12 — ne jamais supposer). Consignés ici plutôt que
silencieusement absorbés :

1. **`ST_Translate` corrompt les géométries 3D dans cette version de DuckDB spatial.** Vérifié :
   `ST_Translate(ST_GeomFromText('POINT Z (1 2 3)'), 10, 20)` retourne `POINT Z (31 62 3)` au lieu
   de `POINT Z (11 22 3)` — le décalage appliqué n'a aucun rapport avec `dx`/`dy` fournis, sur les
   overloads 2 arguments **et** 3 arguments. `ST_Scale` et `ST_Rotate`, eux, sont vérifiés corrects
   sur des géométries 3D (`ST_Scale(POINT Z(1,2,3), 2, 2)` → `POINT Z (2 4 3)`, correct).
   **Conséquence** : `transform.translateGeometry` et `transform.rotateGeometry` (qui compose
   `ST_Translate` en interne pour tourner autour du centroïde plutôt que de l'origine) **refusent
   explicitement toute géométrie avec Z** via un garde SQL (`CASE WHEN ST_HasZ(geometry) THEN
   error(...)`), plutôt que de risquer une corruption silencieuse. `transform.scaleGeometry` n'a pas
   ce garde (vérifié sûr), mais n'expose pas de paramètre `zs` dans cette vague, pour garder les 3
   op géométriques affines à une forme de params cohérente (2D seulement) — un futur incrément peut
   ajouter `zs` à `transform.scaleGeometry` seul.
2. **Aucune fonction `ST_SetSRID`/`ST_SRID` n'existe dans l'extension `spatial` chargée.** Le SRID
   dans ce runtime de pipeline est un entier obligatoire porté hors-bande par
   `core/app/pipelines/runtime.py` (`srid_by_node: dict[str, int]`), jamais stocké sur la valeur
   `GEOMETRY` elle-même. **Conséquence** : `transform.setSrid` ne couvre que la sémantique
   « réassigner le SRID » (`CoordinateSystemSetter`) — `CoordinateSystemRemover` n'a pas de cible
   cohérente dans cette architecture (le SRID ne peut pas être « absent », il vaut toujours un
   entier), reste `coverage_status: planned_duckdb` dans la matrice, non couvert par ce chantier
   (Tâche 6 documente cette limite dans la `notes` de la ligne).
3. **`ST_Dimension` retourne la dimension TOPOLOGIQUE (0/1/2 = point/ligne/polygone), pas la
   dimension de coordonnées (2D/3D).** Vérifié : `ST_Dimension(ST_Point(1,2))` → `0`. Le besoin de
   `DimensionExtractor` (2D vs 3D) est couvert à la place par `ST_HasZ` (`CASE WHEN ST_HasZ(geometry)
   THEN 3 ELSE 2 END`), vérifié correct.

**Total révisé** : 15 op couvrant **18** des 90 lignes FME (`CoordinateSystemRemover` exclu), pas 19
comme indiqué dans le design — écart d'une ligne, documenté en Tâche 6.

---

### Task 1: Permutation et transformations affines simples (`swapCoordinates`, `translateGeometry`, `scaleGeometry`)

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `_qi()`, `compile_transform_sql()`, fixture `conn_spatial` (déjà existants dans
  `test_pipeline_compiler.py` — base à 2 points `(3.0, 45.0)` id=1 et `(3.001, 45.0)` id=2).
- Produces: `TransformSwapCoordinatesParams`, `TransformTranslateGeometryParams`,
  `TransformScaleGeometryParams` (`ops/schemas.py`) ; `_compile_swap_coordinates`,
  `_compile_translate_geometry`, `_compile_scale_geometry` (`compiler.py`) ; 3 entrées
  `OPERATIONS["transform.swapCoordinates"|"transform.translateGeometry"|"transform.scaleGeometry"]`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_compiler.py` :

```python
def test_compile_swap_coordinates(conn_spatial):
    sql = compile_transform_sql("transform.swapCoordinates", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == (45.0, 3.0)


def test_compile_translate_geometry(conn_spatial):
    sql = compile_transform_sql(
        "transform.translateGeometry", {"dx": 1.0, "dy": 2.0}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == pytest.approx((4.0, 47.0))


def test_compile_translate_geometry_rejects_3d_geometry(conn_spatial):
    # Régression : ST_Translate corrompt silencieusement les géométries 3D
    # dans cette version de DuckDB spatial (§0 du plan) — ce nœud doit
    # échouer bruyamment plutôt que produire des coordonnées fausses.
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql(
        "transform.translateGeometry", {"dx": 1.0, "dy": 2.0}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    with pytest.raises(duckdb.InvalidInputException, match="3D geometry not supported"):
        conn_spatial.execute("SELECT * FROM out3d").fetchall()


def test_compile_scale_geometry(conn_spatial):
    sql = compile_transform_sql(
        "transform.scaleGeometry", {"xs": 2.0, "ys": 3.0}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    x, y = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert (x, y) == pytest.approx((6.0, 135.0))


def test_compile_scale_geometry_keeps_z_untouched(conn_spatial):
    # Contrôle négatif du garde 3D : Scale, contrairement à Translate/Rotate,
    # est vérifié correct sur une géométrie avec Z (§0) — pas de garde ici.
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (2 3 4)'))")
    sql = compile_transform_sql(
        "transform.scaleGeometry", {"xs": 2.0, "ys": 2.0}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    x, y, z = conn_spatial.execute(
        "SELECT ST_X(geometry), ST_Y(geometry), ST_Z(geometry) FROM out3d"
    ).fetchone()
    assert (x, y, z) == pytest.approx((4.0, 6.0, 4.0))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "swap_coordinates or translate_geometry or scale_geometry" -v`

Expected: FAIL — `compile_transform_sql("transform.swapCoordinates", ...)` lève `ValueError: 'transform.swapCoordinates' is not a transform op` (op inconnue de `OPERATIONS`), même chose pour les deux autres.

- [ ] **Step 3: Add the three params classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter à la fin du fichier :

```python
class TransformSwapCoordinatesParams(BaseModel):
    """Permute X et Y de la géométrie (ex. données saisies en latitude/longitude
    au lieu de longitude/latitude)."""


class TransformTranslateGeometryParams(BaseModel):
    """Translation de la géométrie.

    Géométrie 3D (avec Z) refusée : ST_Translate de l'extension spatiale
    DuckDB corrompt les coordonnées d'une géométrie avec Z (vérifié
    empiriquement, design vague 1 transformers DuckDB §0)."""

    dx: float
    dy: float


class TransformScaleGeometryParams(BaseModel):
    """Mise à l'échelle de la géométrie autour de l'origine (0, 0) — PAS
    autour du centre de la géométrie (vérifié empiriquement contre DuckDB
    spatial réel)."""

    xs: float
    ys: float
```

- [ ] **Step 4: Add the three compile functions**

Dans `core/app/pipelines/compiler.py`, ajouter les imports des 3 nouvelles classes à l'import déjà
existant depuis `app.pipelines.ops.schemas` (ordre alphabétique, comme les imports existants), puis
ajouter ces 3 fonctions juste avant `def compile_transform_sql(`:

```python
def _compile_swap_coordinates(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformSwapCoordinatesParams.model_validate(params)  # forme seulement, aucun champ
    return (
        f"SELECT * EXCLUDE (geometry), ST_FlipCoordinates(geometry) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_translate_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformTranslateGeometryParams.model_validate(params)
    return (
        f"SELECT * EXCLUDE (geometry), (CASE WHEN ST_HasZ(geometry) THEN error("
        f"'transform.translateGeometry: 3D geometry not supported (ST_Translate "
        f"corrupts Z coordinates in this DuckDB spatial version)') "
        f"ELSE ST_Translate(geometry, {p.dx}, {p.dy}) END) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_scale_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformScaleGeometryParams.model_validate(params)
    return (
        f"SELECT * EXCLUDE (geometry), ST_Scale(geometry, {p.xs}, {p.ys}) AS geometry "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 5: Register the three contracts**

Dans `core/app/pipelines/ops/contracts.py` : ajouter `TransformSwapCoordinatesParams`,
`TransformTranslateGeometryParams`, `TransformScaleGeometryParams` à l'import existant depuis
`app.pipelines.ops.schemas` (ordre alphabétique), puis ajouter ces 3 entrées juste avant la ligne
finale `}` qui ferme le dict `OPERATIONS` (après l'entrée `"transform.merge"`) :

```python
    "transform.swapCoordinates": OperationContract(
        op="transform.swapCoordinates",
        kind="transform",
        params_schema=TransformSwapCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_swap_coordinates,
    ),
    "transform.translateGeometry": OperationContract(
        op="transform.translateGeometry",
        kind="transform",
        params_schema=TransformTranslateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_translate_geometry,
    ),
    "transform.scaleGeometry": OperationContract(
        op="transform.scaleGeometry",
        kind="transform",
        params_schema=TransformScaleGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_scale_geometry,
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "swap_coordinates or translate_geometry or scale_geometry" -v`

Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): ajoute transform.swapCoordinates/translateGeometry/scaleGeometry"
```

---

### Task 2: Rotation, création et réduction de précision (`rotateGeometry`, `createGeometry`, `roundCoordinates`)

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mêmes fixtures/helpers que Task 1.
- Produces: `TransformRotateGeometryParams`, `TransformCreateGeometryParams`,
  `TransformRoundCoordinatesParams` ; `_compile_rotate_geometry`, `_compile_create_geometry`,
  `_compile_round_coordinates` ; 3 entrées `OPERATIONS`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_compiler.py` :

```python
def test_compile_rotate_geometry_around_own_centroid(conn_spatial):
    # Un carré loin de l'origine tourné de 90° autour de SON PROPRE centre
    # (pas de l'origine (0,0) — ST_Rotate seul tourne autour de l'origine,
    # ce nœud recentre avant/après, design §4.1).
    conn_spatial.execute("CREATE TABLE square (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO square VALUES "
        "(1, ST_GeomFromText('POLYGON((10 10, 12 10, 12 12, 10 12, 10 10))'))"
    )
    import math

    sql = compile_transform_sql(
        "transform.rotateGeometry", {"radians": math.pi / 2}, input_view="square"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0]
    assert wkt == "POLYGON ((12 10, 12 12, 10 12, 10 10, 12 10))"


def test_compile_rotate_geometry_rejects_3d_geometry(conn_spatial):
    # rotateGeometry compose ST_Translate en interne (recentrage) — même
    # garde 3D que translateGeometry, même cause (§0).
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql(
        "transform.rotateGeometry", {"radians": 1.0}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    with pytest.raises(duckdb.InvalidInputException, match="3D geometry not supported"):
        conn_spatial.execute("SELECT * FROM out3d").fetchall()


def test_compile_create_geometry_replaces_geometry_with_literal_wkt(conn_spatial):
    sql = compile_transform_sql(
        "transform.createGeometry", {"wkt": "POINT(2.35 48.85)"}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out ORDER BY id").fetchall()
    assert rows == [("POINT (2.35 48.85)",), ("POINT (2.35 48.85)",)]


def test_compile_create_geometry_escapes_single_quotes(conn_spatial):
    # wkt vient d'un champ texte libre côté config — jamais interpolé sans
    # échappement dans le SQL généré (une géométrie littérale ne devrait
    # jamais contenir de guillemet simple, mais le compilateur ne doit pas
    # produire de SQL invalide/injectable si un jour c'est le cas).
    sql = compile_transform_sql(
        "transform.createGeometry", {"wkt": "POINT(1 2)'; DROP TABLE base; --"}, input_view="base"
    )
    assert "''" in sql


def test_compile_round_coordinates(conn_spatial):
    sql = compile_transform_sql(
        "transform.roundCoordinates", {"gridSize": 0.01}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out ORDER BY id").fetchall()
    assert rows == [("POINT (3 45)",), ("POINT (3 45)",)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "rotate_geometry or create_geometry or round_coordinates" -v`

Expected: FAIL — `ValueError: '...' is not a transform op` pour les 3 op.

- [ ] **Step 3: Add the three params classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter à la fin du fichier :

```python
class TransformRotateGeometryParams(BaseModel):
    """Rotation de la géométrie autour de son propre centroïde.

    PAS autour de l'origine (0, 0) : ST_Rotate de DuckDB tourne nativement
    autour de l'origine, ce nœud recentre avant/après. Géométrie 3D refusée,
    même limite que transform.translateGeometry (ce nœud compose
    ST_Translate en interne, design vague 1 transformers DuckDB §0)."""

    radians: float


class TransformCreateGeometryParams(BaseModel):
    """Remplace la géométrie de chaque ligne par une géométrie WKT littérale
    (ex. "POINT(2.35 48.85)"). Utile pour créer une géométrie constante ou
    tester un pipeline sans source spatiale réelle."""

    wkt: str


class TransformRoundCoordinatesParams(BaseModel):
    """Réduit la précision des coordonnées de la géométrie à une taille de
    grille donnée (ex. gridSize=0.0001 ≈ 11 m en EPSG:4326).

    PAS un nombre de décimales : une taille de grille (mêmes unités que le
    système de coordonnées courant)."""

    gridSize: float = Field(..., gt=0)
```

- [ ] **Step 4: Add the three compile functions**

Dans `core/app/pipelines/compiler.py`, ajouter les 3 nouveaux noms à l'import
`app.pipelines.ops.schemas` (ordre alphabétique), puis ajouter ces 3 fonctions après celles de
Task 1 :

```python
def _compile_rotate_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformRotateGeometryParams.model_validate(params)
    centered = "ST_Translate(geometry, -ST_X(ST_Centroid(geometry)), -ST_Y(ST_Centroid(geometry)))"
    rotated = f"ST_Rotate({centered}, {p.radians})"
    recentered = f"ST_Translate({rotated}, ST_X(ST_Centroid(geometry)), ST_Y(ST_Centroid(geometry)))"
    return (
        f"SELECT * EXCLUDE (geometry), (CASE WHEN ST_HasZ(geometry) THEN error("
        f"'transform.rotateGeometry: 3D geometry not supported (ST_Translate "
        f"corrupts Z coordinates in this DuckDB spatial version)') "
        f"ELSE {recentered} END) AS geometry FROM {_qi(input_view)}"
    )


def _compile_create_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformCreateGeometryParams.model_validate(params)
    escaped_wkt = p.wkt.replace("'", "''")
    return (
        f"SELECT * EXCLUDE (geometry), ST_GeomFromText('{escaped_wkt}') AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_round_coordinates(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformRoundCoordinatesParams.model_validate(params)
    return (
        f"SELECT * EXCLUDE (geometry), ST_ReducePrecision(geometry, {p.gridSize}) AS geometry "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 5: Register the three contracts**

Dans `core/app/pipelines/ops/contracts.py` : ajouter `TransformRotateGeometryParams`,
`TransformCreateGeometryParams`, `TransformRoundCoordinatesParams` à l'import
`app.pipelines.ops.schemas`, puis ajouter ces 3 entrées après celles de Task 1 :

```python
    "transform.rotateGeometry": OperationContract(
        op="transform.rotateGeometry",
        kind="transform",
        params_schema=TransformRotateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_rotate_geometry,
    ),
    "transform.createGeometry": OperationContract(
        op="transform.createGeometry",
        kind="transform",
        params_schema=TransformCreateGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_create_geometry,
    ),
    "transform.roundCoordinates": OperationContract(
        op="transform.roundCoordinates",
        kind="transform",
        params_schema=TransformRoundCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_round_coordinates,
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "rotate_geometry or create_geometry or round_coordinates" -v`

Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): ajoute transform.rotateGeometry/createGeometry/roundCoordinates"
```

---

### Task 3: Extraction et construction de coordonnées (`concatCoordinates`, `extractCoordinates`, `extractElevation`)

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mêmes fixtures/helpers que Task 1.
- Produces: `TransformConcatCoordinatesParams`, `TransformExtractCoordinatesParams`,
  `TransformExtractElevationParams` ; `_compile_concat_coordinates`,
  `_compile_extract_coordinates`, `_compile_extract_elevation` ; 3 entrées `OPERATIONS`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_compiler.py` :

```python
def test_compile_concat_coordinates_builds_a_point_from_attribute_columns(conn_spatial):
    conn_spatial.execute("CREATE TABLE xy (id INTEGER, lon DOUBLE, lat DOUBLE, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO xy VALUES (1, 3.0, 45.0, NULL)")
    sql = compile_transform_sql(
        "transform.concatCoordinates", {"xColumn": "lon", "yColumn": "lat"}, input_view="xy"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    wkt = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out").fetchone()[0]
    assert wkt == "POINT (3 45)"


def test_compile_extract_coordinates_default_column_names(conn_spatial):
    sql = compile_transform_sql("transform.extractCoordinates", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT x, y FROM out WHERE id = 1").fetchone()
    assert row == (3.0, 45.0)


def test_compile_extract_coordinates_custom_column_names(conn_spatial):
    sql = compile_transform_sql(
        "transform.extractCoordinates",
        {"xColumn": "longitude", "yColumn": "latitude"},
        input_view="base",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT longitude, latitude FROM out WHERE id = 1").fetchone()
    assert row == (3.0, 45.0)


def test_compile_extract_elevation_is_null_for_2d_geometry(conn_spatial):
    sql = compile_transform_sql("transform.extractElevation", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT elevation FROM out WHERE id = 1").fetchone()
    assert row == (None,)


def test_compile_extract_elevation_reads_z_for_3d_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql(
        "transform.extractElevation", {"column": "z"}, input_view="base3d"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    row = conn_spatial.execute("SELECT z FROM out3d").fetchone()
    assert row == (3.0,)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "concat_coordinates or extract_coordinates or extract_elevation" -v`

Expected: FAIL — `ValueError: '...' is not a transform op` pour les 3 op.

- [ ] **Step 3: Add the three params classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter à la fin du fichier :

```python
class TransformConcatCoordinatesParams(BaseModel):
    """Construit la géométrie (un point) à partir de deux colonnes attribut
    X/Y existantes — remplace la géométrie courante."""

    xColumn: str
    yColumn: str


class TransformExtractCoordinatesParams(BaseModel):
    """X et Y de la géométrie → deux colonnes attribut séparées."""

    xColumn: str = "x"
    yColumn: str = "y"


class TransformExtractElevationParams(BaseModel):
    """Composante Z de la géométrie → colonne attribut (NULL si la géométrie
    n'a pas de Z)."""

    column: str = "elevation"
```

- [ ] **Step 4: Add the three compile functions**

Dans `core/app/pipelines/compiler.py`, ajouter les 3 nouveaux noms à l'import
`app.pipelines.ops.schemas`, puis ajouter ces 3 fonctions après celles de Task 2 :

```python
def _compile_concat_coordinates(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformConcatCoordinatesParams.model_validate(params)
    return (
        f"SELECT * EXCLUDE (geometry), ST_Point({_qi(p.xColumn)}, {_qi(p.yColumn)}) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_extract_coordinates(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExtractCoordinatesParams.model_validate(params)
    return (
        f"SELECT *, ST_X(geometry) AS {_qi(p.xColumn)}, ST_Y(geometry) AS {_qi(p.yColumn)} "
        f"FROM {_qi(input_view)}"
    )


def _compile_extract_elevation(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExtractElevationParams.model_validate(params)
    return f"SELECT *, ST_Z(geometry) AS {_qi(p.column)} FROM {_qi(input_view)}"
```

- [ ] **Step 5: Register the three contracts**

Dans `core/app/pipelines/ops/contracts.py` : ajouter `TransformConcatCoordinatesParams`,
`TransformExtractCoordinatesParams`, `TransformExtractElevationParams` à l'import
`app.pipelines.ops.schemas`, puis ajouter ces 3 entrées après celles de Task 2 :

```python
    "transform.concatCoordinates": OperationContract(
        op="transform.concatCoordinates",
        kind="transform",
        params_schema=TransformConcatCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_concat_coordinates,
    ),
    "transform.extractCoordinates": OperationContract(
        op="transform.extractCoordinates",
        kind="transform",
        params_schema=TransformExtractCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_coordinates,
    ),
    "transform.extractElevation": OperationContract(
        op="transform.extractElevation",
        kind="transform",
        params_schema=TransformExtractElevationParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_elevation,
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "concat_coordinates or extract_coordinates or extract_elevation" -v`

Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): ajoute transform.concatCoordinates/extractCoordinates/extractElevation"
```

---

### Task 4: Métadonnées géométriques et SRID en lecture (`extractDimension`, `countVertices`, `extractSrid`)

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mêmes fixtures/helpers que Task 1.
- Produces: `TransformExtractDimensionParams`, `TransformCountVerticesParams`,
  `TransformExtractSridParams` ; `_compile_extract_dimension`, `_compile_count_vertices`,
  `_compile_extract_srid` ; 3 entrées `OPERATIONS`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_compiler.py` :

```python
def test_compile_extract_dimension_is_2_for_2d_geometry(conn_spatial):
    sql = compile_transform_sql("transform.extractDimension", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT dimension FROM out WHERE id = 1").fetchone()
    assert row == (2,)


def test_compile_extract_dimension_is_3_for_3d_geometry(conn_spatial):
    conn_spatial.execute("CREATE TABLE base3d (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute("INSERT INTO base3d VALUES (1, ST_GeomFromText('POINT Z (1 2 3)'))")
    sql = compile_transform_sql("transform.extractDimension", {}, input_view="base3d")
    conn_spatial.execute(f"CREATE TEMP VIEW out3d AS {sql}")
    row = conn_spatial.execute("SELECT dimension FROM out3d").fetchone()
    assert row == (3,)


def test_compile_count_vertices(conn_spatial):
    conn_spatial.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO line VALUES (1, ST_GeomFromText('LINESTRING(0 0, 1 1, 2 2)'))"
    )
    sql = compile_transform_sql(
        "transform.countVertices", {"column": "n"}, input_view="line"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT n FROM out").fetchone()
    assert row == (3,)


def test_compile_extract_srid_returns_the_pipeline_srid(conn_spatial):
    sql = compile_transform_sql(
        "transform.extractSrid", {}, input_view="base", input_srid=4326
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT srid FROM out WHERE id = 1").fetchone()
    assert row == (4326,)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "extract_dimension or count_vertices or extract_srid" -v`

Expected: FAIL — `ValueError: '...' is not a transform op` pour les 3 op.

- [ ] **Step 3: Add the three params classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter à la fin du fichier :

```python
class TransformExtractDimensionParams(BaseModel):
    """Dimension de COORDONNÉES de la géométrie (2 ou 3 selon la présence
    d'un Z) → colonne attribut.

    Distinct de la dimension topologique (point/ligne/polygone) : ST_Dimension
    de DuckDB retourne cette dernière (0/1/2), pas ce que ce nœud expose
    (vérifié empiriquement, design vague 1 transformers DuckDB §0)."""

    column: str = "dimension"


class TransformCountVerticesParams(BaseModel):
    """Nombre de sommets de la géométrie → colonne attribut."""

    column: str = "vertexCount"


class TransformExtractSridParams(BaseModel):
    """SRID (code EPSG) du système de coordonnées courant du pipeline →
    colonne attribut constante.

    Le SRID est un état porté par le runtime du pipeline, pas un attribut de
    la géométrie elle-même : DuckDB spatial ne stocke aucun SRID sur le type
    GEOMETRY (vérifié empiriquement, design vague 1 transformers DuckDB
    §0)."""

    column: str = "srid"
```

- [ ] **Step 4: Add the three compile functions**

Dans `core/app/pipelines/compiler.py`, ajouter les 3 nouveaux noms à l'import
`app.pipelines.ops.schemas`, puis ajouter ces 3 fonctions après celles de Task 3 :

```python
def _compile_extract_dimension(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExtractDimensionParams.model_validate(params)
    return (
        f"SELECT *, (CASE WHEN ST_HasZ(geometry) THEN 3 ELSE 2 END) AS {_qi(p.column)} "
        f"FROM {_qi(input_view)}"
    )


def _compile_count_vertices(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformCountVerticesParams.model_validate(params)
    return f"SELECT *, ST_NPoints(geometry) AS {_qi(p.column)} FROM {_qi(input_view)}"


def _compile_extract_srid(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExtractSridParams.model_validate(params)
    assert input_srid is not None, "transform.extractSrid requires input_srid"
    return f"SELECT *, {input_srid} AS {_qi(p.column)} FROM {_qi(input_view)}"
```

- [ ] **Step 5: Register the three contracts**

Dans `core/app/pipelines/ops/contracts.py` : ajouter `TransformExtractDimensionParams`,
`TransformCountVerticesParams`, `TransformExtractSridParams` à l'import `app.pipelines.ops.schemas`,
puis ajouter ces 3 entrées après celles de Task 3 :

```python
    "transform.extractDimension": OperationContract(
        op="transform.extractDimension",
        kind="transform",
        params_schema=TransformExtractDimensionParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_dimension,
    ),
    "transform.countVertices": OperationContract(
        op="transform.countVertices",
        kind="transform",
        params_schema=TransformCountVerticesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_count_vertices,
    ),
    "transform.extractSrid": OperationContract(
        op="transform.extractSrid",
        kind="transform",
        params_schema=TransformExtractSridParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_extract_srid,
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "extract_dimension or count_vertices or extract_srid" -v`

Expected: PASS (4 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): ajoute transform.extractDimension/countVertices/extractSrid"
```

---

### Task 5: SRID en écriture et formatage d'attributs (`setSrid`, `reprojectAttribute`, `formatCoordinates`)

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mêmes fixtures/helpers que Task 1 ; `transform_output_srid()` (déjà existant,
  `compiler.py`).
- Produces: `TransformSetSridParams`, `TransformReprojectAttributeParams`,
  `TransformFormatCoordinatesParams` ; `_compile_set_srid`, `_output_srid_set_srid`,
  `_compile_reproject_attribute`, `_compile_format_coordinates` ; 3 entrées `OPERATIONS`.

- [ ] **Step 1: Write the failing tests**

Ajouter à la fin de `core/tests/test_pipeline_compiler.py` :

```python
def test_compile_set_srid_does_not_change_the_geometry(conn_spatial):
    sql = compile_transform_sql(
        "transform.setSrid", {"targetSrid": 2154}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out WHERE id = 1").fetchone()
    assert row == ("POINT (3 45)",)


def test_set_srid_overrides_the_output_srid():
    from app.pipelines.compiler import transform_output_srid

    srid = transform_output_srid(
        "transform.setSrid", {"targetSrid": 2154}, input_srid=4326
    )
    assert srid == 2154


def test_compile_reproject_attribute_uses_correct_axis_order(conn_spatial):
    conn_spatial.execute(
        "CREATE TABLE attr_xy (id INTEGER, lon DOUBLE, lat DOUBLE, geometry GEOMETRY)"
    )
    conn_spatial.execute("INSERT INTO attr_xy VALUES (1, 3.0, 45.0, ST_Point(0, 0))")
    sql = compile_transform_sql(
        "transform.reprojectAttribute",
        {"xColumn": "lon", "yColumn": "lat", "sourceCrs": "EPSG:4326", "targetCrs": "EPSG:3857"},
        input_view="attr_xy",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    lon, lat = conn_spatial.execute("SELECT lon, lat FROM out WHERE id = 1").fetchone()
    assert lon == pytest.approx(333958.47, abs=1)
    assert lat == pytest.approx(5621521.49, abs=1)


def test_compile_format_coordinates_decimal_degrees(conn_spatial):
    conn_spatial.execute("CREATE TABLE lat_table (id INTEGER, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO lat_table VALUES (1, 48.858093)")
    sql = compile_transform_sql(
        "transform.formatCoordinates",
        {"sourceColumn": "lat", "targetColumn": "latText", "format": "decimalDegrees",
         "precision": 2},
        input_view="lat_table",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT latText FROM out").fetchone()
    assert row == (48.86,)


def test_compile_format_coordinates_dms(conn_spatial):
    conn_spatial.execute("CREATE TABLE lat_table (id INTEGER, lat DOUBLE)")
    conn_spatial.execute("INSERT INTO lat_table VALUES (1, 48.858093), (2, -48.858093)")
    sql = compile_transform_sql(
        "transform.formatCoordinates",
        {"sourceColumn": "lat", "targetColumn": "latText", "format": "dms", "precision": 2},
        input_view="lat_table",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute("SELECT latText FROM out ORDER BY id").fetchall()
    assert rows == [("48°51'29.13\"",), ("-48°51'29.13\"",)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "set_srid or reproject_attribute or format_coordinates" -v`

Expected: FAIL — `ValueError: '...' is not a transform op` pour les 3 op (`test_set_srid_overrides_the_output_srid` échoue avec un passthrough silencieux au lieu de `2154`, puisque `transform_output_srid` retombe sur `input_srid` pour toute op inconnue).

- [ ] **Step 3: Add the three params classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter à la fin du fichier :

```python
class TransformSetSridParams(BaseModel):
    """Réassigne le SRID du pipeline SANS reprojeter les coordonnées — à
    utiliser quand les coordonnées sont correctes mais le SRID détecté à la
    lecture est faux.

    Pour reprojeter réellement les coordonnées, utiliser transform.reproject.
    Ne couvre pas le retrait de SRID (CoordinateSystemRemover de la matrice
    FME) : le SRID est un entier obligatoire dans ce runtime, jamais absent
    (design vague 1 transformers DuckDB §0)."""

    targetSrid: int = Field(..., gt=0)


class TransformReprojectAttributeParams(BaseModel):
    """Reprojette une paire de coordonnées portée par DEUX COLONNES ATTRIBUT
    (pas la géométrie de la feature) — distinct de transform.reproject qui
    reprojette la géométrie. Écrase xColumn/yColumn en place."""

    xColumn: str
    yColumn: str
    sourceCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")
    targetCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")


class TransformFormatCoordinatesParams(BaseModel):
    """Formate une colonne attribut numérique (coordonnée en degrés
    décimaux) en texte : soit arrondie en degrés décimaux, soit convertie en
    degrés/minutes/secondes (DMS, sans indicateur d'hémisphère — à
    concaténer séparément si besoin)."""

    sourceColumn: str
    targetColumn: str
    format: Literal["decimalDegrees", "dms"] = "decimalDegrees"
    precision: int = Field(4, ge=0, le=10)
```

- [ ] **Step 4: Add the compile and output_srid functions**

Dans `core/app/pipelines/compiler.py`, ajouter les 3 nouveaux noms à l'import
`app.pipelines.ops.schemas`, puis ajouter ces fonctions après celles de Task 4 (`_compile_set_srid`
et `_output_srid_set_srid` juste avant `def compile_transform_sql(`, comme les fonctions
`_output_srid_*` existantes) :

```python
def _compile_set_srid(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformSetSridParams.model_validate(params)  # forme seulement, lu par _output_srid_set_srid
    return f"SELECT * FROM {_qi(input_view)}"


def _compile_reproject_attribute(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformReprojectAttributeParams.model_validate(params)
    point_expr = f"ST_Point({_qi(p.xColumn)}, {_qi(p.yColumn)})"
    transformed = f"ST_Transform({point_expr}, '{p.sourceCrs}', '{p.targetCrs}', true)"
    return (
        f"SELECT * EXCLUDE ({_qi(p.xColumn)}, {_qi(p.yColumn)}), "
        f"ST_X({transformed}) AS {_qi(p.xColumn)}, ST_Y({transformed}) AS {_qi(p.yColumn)} "
        f"FROM {_qi(input_view)}"
    )


def _compile_format_coordinates(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformFormatCoordinatesParams.model_validate(params)
    src = _qi(p.sourceColumn)
    if p.format == "decimalDegrees":
        expr = f"ROUND({src}, {p.precision})"
    else:
        deg = f"CAST(floor(abs({src})) AS INTEGER)"
        minutes = f"CAST(floor((abs({src}) - floor(abs({src}))) * 60) AS INTEGER)"
        seconds = (
            f"(abs({src}) - floor(abs({src})) - "
            f"floor((abs({src}) - floor(abs({src}))) * 60) / 60.0) * 3600"
        )
        sign = f"CASE WHEN {src} < 0 THEN '-' ELSE '' END"
        expr = f"{sign} || printf('%d°%d''%.{p.precision}f\"', {deg}, {minutes}, {seconds})"
    return f"SELECT *, ({expr}) AS {_qi(p.targetColumn)} FROM {_qi(input_view)}"
```

Puis, juste avant `def transform_output_srid(` (après `_output_srid_qgis`), ajouter :

```python
def _output_srid_set_srid(
    params: dict,
    *,
    op: str,
    input_srid: int,
    join_srid: int | None = None,
) -> int:
    p = TransformSetSridParams.model_validate(params)
    return p.targetSrid
```

- [ ] **Step 5: Register the three contracts**

Dans `core/app/pipelines/ops/contracts.py` : ajouter `TransformSetSridParams`,
`TransformReprojectAttributeParams`, `TransformFormatCoordinatesParams` à l'import
`app.pipelines.ops.schemas`, puis ajouter ces 3 entrées après celles de Task 4 (juste avant la
ligne finale `}` qui ferme `OPERATIONS`) :

```python
    "transform.setSrid": OperationContract(
        op="transform.setSrid",
        kind="transform",
        params_schema=TransformSetSridParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_set_srid,
        output_srid=_compiler._output_srid_set_srid,
    ),
    "transform.reprojectAttribute": OperationContract(
        op="transform.reprojectAttribute",
        kind="transform",
        params_schema=TransformReprojectAttributeParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_reproject_attribute,
    ),
    "transform.formatCoordinates": OperationContract(
        op="transform.formatCoordinates",
        kind="transform",
        params_schema=TransformFormatCoordinatesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_format_coordinates,
    ),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "set_srid or reproject_attribute or format_coordinates" -v`

Expected: PASS (6 tests).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(core): ajoute transform.setSrid/reprojectAttribute/formatCoordinates"
```

---

### Task 6: Clôture — garde-fous, régénération, matrice FME, CLAUDE.md

**Files:**
- Test: `core/tests/test_pipeline_ops_contracts.py`
- Test: `core/tests/test_pipeline_routes.py`
- Modify: `core/openapi.json` (régénéré)
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré)
- Modify: `docs/revue/matrice-couverture-fme.jsonl`
- Modify: `docs/revue/matrice-couverture-fme.md` (régénéré)
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `OPERATIONS` (`app.pipelines.ops.contracts`), `ops_catalog()`, l'existant
  `core/scripts/fme_coverage_cli.py`.
- Produces: rien de nouveau (tâche de clôture uniquement).

- [ ] **Step 1: Fix the two existing hardcoded-19 guard tests**

Ces deux tests existants font une égalité d'ENSEMBLE sur les 19 noms d'op littéraux (pas une
simple longueur) — vérifié dans le code, pas supposé. Ils échouent dès la fin de la Task 1 (20
entrées dans `OPERATIONS`, plus plusieurs échecs en cascade au fil des Tasks 2 à 5) tant qu'ils ne
sont pas mis à jour ; les fixer maintenant, avant de lancer la suite complète, plutôt que de
laisser une régression connue traîner jusqu'à cette tâche.

Dans `core/tests/test_pipeline_ops_contracts.py`, renommer
`test_operations_registry_has_exactly_the_nineteen_known_ops` en
`test_operations_registry_has_exactly_the_thirty_four_known_ops` et ajouter les 15 nouveaux noms
d'op au littéral `set(OPERATIONS) == {...}` (garder les 19 existants inchangés, ajouter à la
suite) :

```python
        "transform.swapCoordinates",
        "transform.translateGeometry",
        "transform.scaleGeometry",
        "transform.rotateGeometry",
        "transform.createGeometry",
        "transform.concatCoordinates",
        "transform.roundCoordinates",
        "transform.extractElevation",
        "transform.extractDimension",
        "transform.countVertices",
        "transform.extractCoordinates",
        "transform.extractSrid",
        "transform.setSrid",
        "transform.reprojectAttribute",
        "transform.formatCoordinates",
```

Dans le même fichier, renommer `test_all_nineteen_operations_default_exchange_to_none` en
`test_all_operations_default_exchange_to_none` (le corps de la fonction, qui itère
génériquement sur `OPERATIONS.items()`, n'a besoin d'aucun autre changement).

- [ ] **Step 2: Run to verify the renamed tests pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_contracts.py -v`

Expected: PASS — les Tasks 1 à 5 ont déjà porté `OPERATIONS` à 34 entrées ; ces deux renommages/
mises à jour documentent l'état réel, sans nouvelle implémentation.

- [ ] **Step 3: Add the total-count guard test**

Ajouter à la fin de `core/tests/test_pipeline_ops_contracts.py` (garde-fou redondant mais
peu coûteux avec le test d'ensemble exact du Step 1 — si l'un des deux est un jour désynchronisé
de l'autre, un troisième test faux positif serait pire qu'une petite redondance) :

```python
def test_operations_registry_has_thirty_four_entries_after_wave_1():
    from app.pipelines.ops.contracts import OPERATIONS

    assert len(OPERATIONS) == 34
```

Run: `cd core && uv run pytest tests/test_pipeline_ops_contracts.py -k thirty_four -v`

Expected: PASS.

- [ ] **Step 4: Fix the API route guard test the same way**

Dans `core/tests/test_pipeline_routes.py`, le test `test_get_pipelines_ops_returns_all_nineteen`
fait la même égalité d'ensemble sur 19 noms littéraux, contre la réponse JSON de
`GET /v1/pipelines/ops` cette fois. Le renommer
`test_get_pipelines_ops_returns_all_thirty_four`, remplacer le commentaire juste au-dessus
(`# Phase 1 (8) + spatial (5) + ... = 19 total.`) par
`# 19 op existantes (cf. design OperationContract) + 15 op vague 1 (géométrie/coordonnées/SRID,
# cf. design vague 1 transformers DuckDB) = 34 total.`, et ajouter les mêmes 15 noms d'op au
littéral `set(body) == {...}` (garder les 19 existants inchangés) :

```python
        "transform.swapCoordinates",
        "transform.translateGeometry",
        "transform.scaleGeometry",
        "transform.rotateGeometry",
        "transform.createGeometry",
        "transform.concatCoordinates",
        "transform.roundCoordinates",
        "transform.extractElevation",
        "transform.extractDimension",
        "transform.countVertices",
        "transform.extractCoordinates",
        "transform.extractSrid",
        "transform.setSrid",
        "transform.reprojectAttribute",
        "transform.formatCoordinates",
```

Run: `cd core && uv run pytest tests/test_pipeline_routes.py -k thirty_four -v`

Expected: PASS.

- [ ] **Step 5: Run the full core test suite**

Run: `cd core && uv run pytest`

Expected: PASS, 0 failed (aucune régression sur les 19 op existantes ni sur le reste du cœur).

- [ ] **Step 6: Quality gates**

Run, dans `core/` :

```bash
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
```

Expected: aucune erreur. Si `app.pipelines` est dans le périmètre de `mypy --strict` (vérifier
`core/pyproject.toml`, section `[tool.mypy]`/config CI — ne pas supposer), lancer aussi :

```bash
uv run mypy --strict app/pipelines
```

Expected: aucune erreur (les 15 nouvelles fonctions ont des signatures entièrement typées, même
patron que les fonctions existantes).

- [ ] **Step 7: Regenerate OpenAPI + TS types**

Run :

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Expected : `git diff core/openapi.json shell/src/api/generated/core-schema.d.ts` **non vide** — 15
nouveaux schémas de params apparaissent. C'est le signal attendu (contrairement au chantier
`OperationContract` de la veille), pas une anomalie.

- [ ] **Step 8: Update the FME coverage matrix**

Ouvrir `docs/revue/matrice-couverture-fme.jsonl`. Pour chacune des 18 lignes suivantes, changer
`"coverage_status": "planned_duckdb"` en `"coverage_status": "implemented"` et renseigner
`"geostudio_equivalent"` avec le nom d'op réel :

| `fme_transformer` | `geostudio_equivalent` |
|---|---|
| `CoordinateSwapper` | `transform.swapCoordinates` |
| `AttributeReprojector` | `transform.reprojectAttribute` |
| `GtransAttributeReprojector` | `transform.reprojectAttribute` |
| `PROJAttributeReprojector` | `transform.reprojectAttribute` |
| `CoordinateSystemSetter` | `transform.setSrid` |
| `CoordinateSystemExtractor` | `transform.extractSrid` |
| `DecimalDegreesCalculator` | `transform.formatCoordinates` |
| `DMSCalculator` | `transform.formatCoordinates` |
| `ElevationExtractor` | `transform.extractElevation` |
| `DimensionExtractor` | `transform.extractDimension` |
| `VertexCounter` | `transform.countVertices` |
| `CoordinateExtractor` | `transform.extractCoordinates` |
| `CoordinateConcatenator` | `transform.concatCoordinates` |
| `CoordinateRounder` | `transform.roundCoordinates` |
| `Offsetter` | `transform.translateGeometry` |
| `Scaler` | `transform.scaleGeometry` |
| `Rotator` | `transform.rotateGeometry` |
| `Creator` | `transform.createGeometry` |

Pour la ligne `CoordinateSystemRemover` (non couverte, §0) : laisser `coverage_status:
planned_duckdb` inchangé, mais remplacer son champ `notes` par :

```
Pas de cible cohérente dans ce runtime : le SRID est un entier obligatoire porté hors-bande par
core/app/pipelines/runtime.py, jamais stocké sur la géométrie elle-même (aucune fonction
ST_SetSRID/ST_SRID dans l'extension spatiale DuckDB chargée, vérifié empiriquement — vague 1
transformers DuckDB §0, 2026-09-17/18). transform.setSrid (vague 1) couvre uniquement
CoordinateSystemSetter (réassignation). Retirer un SRID n'a pas de sens ici : ne pourra être
couvert que si une notion de « SRID inconnu/absent » est introduite dans le modèle de pipeline —
chantier séparé, non entamé.
```

Puis régénérer la table Markdown et vérifier mécaniquement :

```bash
python3 core/scripts/fme_coverage_cli.py --write
python3 core/scripts/fme_coverage_cli.py --check
```

Expected : `--check` sort sans erreur (chaque `geostudio_equivalent` des 18 lignes `implemented`
existe bien dans `ops_catalog()` — vérifié mécaniquement, pas déclaré).

- [ ] **Step 9: Update CLAUDE.md**

Dans `CLAUDE.md`, section `### Livré`, ajouter une ligne (respecter la règle « une ligne par
chantier, jamais plus ») :

```
- **Vague 1 transformers DuckDB** — 15 nouvelles op `transform.*` (permutation, translation,
  échelle, rotation, création/arrondi de géométrie, extraction/construction de coordonnées,
  SRID en lecture/écriture, formatage DMS), catalogue à 34 op ; 18 des 90 lignes `planned_duckdb`
  de la matrice FME passées à `implemented`.
```

Run le garde-fou de taille avant de committer :

```bash
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold
```

Expected : pas d'erreur (ligne unique, pas de récit).

- [ ] **Step 10: Commit**

```bash
git add core/tests/test_pipeline_ops_contracts.py core/tests/test_pipeline_routes.py \
  core/openapi.json shell/src/api/generated/core-schema.d.ts \
  docs/revue/matrice-couverture-fme.jsonl docs/revue/matrice-couverture-fme.md CLAUDE.md
git commit -m "feat(core): clôture vague 1 des transformers DuckDB — 34 op, matrice FME à jour"
```

---

## Self-Review (effectuée pendant l'écriture de ce plan)

- **Couverture de la spec** : les 15 op listées en §3.1 du design ont chacune leur tâche (Task 1-5) ;
  §3.2 (hors périmètre) n'a volontairement aucune tâche ; §4.4 (portes de qualité/régénération/
  matrice/CLAUDE.md) est couvert par Task 6. L'écart `CoordinateSystemRemover` (§0) est documenté
  et câblé dans Task 6 plutôt que silencieusement oublié.
- **Aucun placeholder** : chaque étape de code montre le SQL/Python complet, vérifié par exécution
  réelle contre DuckDB 1.5.5 + spatial pendant l'écriture de ce plan (résultats numériques exacts
  utilisés dans les assertions de test, pas des valeurs inventées).
- **Cohérence des types/noms** : `_qi()`, `compile_transform_sql()`, `transform_output_srid()`
  réutilisés à l'identique dans toutes les tâches ; noms de fonctions `_compile_<snake_case du nom
  d'op>` cohérents sur les 15 op ; toutes les nouvelles classes `TransformXxxParams` suivent le
  patron déjà en usage (docstring = description utilisateur en 1er paragraphe, note technique après
  une ligne vide — vérifié contre `_user_facing_description()`, `ops/contracts.py`).

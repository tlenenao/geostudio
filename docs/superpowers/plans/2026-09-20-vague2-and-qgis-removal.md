# Vague 2 — transformers, lecteurs, retrait complet du sidecar QGIS — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un seul plan couvrant les trois volets de
`docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md` : 11 nouvelles op `transform.*`
(schéma dynamique + cardinalité/ordre, Tasks 1-10), 4 nouvelles op `reader.connector.*` (dialectes SQL +
objet/stockage, Tasks 11-17), et le retrait complet du sidecar QGIS — 9 nouvelles op de remplacement +
retrait mécanique total (Tasks 18-31). Catalogue de départ : 34 op (Vague 1, déjà livrée). Catalogue
d'arrivée : **58 op**, 0 trace de QGIS dans le dépôt.

**Architecture:** Toutes les nouvelles op suivent le patron `compile: dict → str` déjà prouvé par les 34 op
existantes (un fragment SQL DuckDB pur, jamais de connexion touchée dans `compiler.py`), à trois extensions
chirurgicales près : `needs_columns` (3 op, Task 7) résout la liste réelle des colonnes d'entrée via un
`DESCRIBE` avant `compile` ; les 4 lecteurs (Tasks 11-17) réutilisent tels quels
`_run_dlt_and_attach`/`SecretResolver` déjà en production ; le nouveau champ `execute` (Task 24)
généralise et remplace le branchement `transform.qgis` codé en dur, pour 3 op calculées en Python
(Shapely) plutôt qu'en SQL.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, DuckDB (extension `spatial`), dlt, SQLAlchemy, fsspec,
Shapely 2.x, pytest.

## Global Constraints

- Référence : `docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md` (document unique,
  §0-§9).
- **Ordre d'exécution interne obligatoire** : Tasks 1-10 (transform ops) → Tasks 11-17 (lecteurs) →
  Tasks 18-26 (9 nouvelles op de remplacement QGIS) → Tasks 27-31 (retrait mécanique du sidecar). Le retrait
  mécanique (Tasks 27-31) ne doit **jamais** s'exécuter avant que les Tasks 18-26 soient vertes — sinon les
  12 lignes vectorielles migrées régressent en même temps que QGIS disparaît (design §8).
- Comptes d'op intermédiaires (chaque test de non-régression `len(OPERATIONS)` doit refléter l'état
  *au moment de la tâche*, pas le total final) : 34 (départ) → **45** après Task 10 → **49** après Task 17
  → **58** après Task 26 (inchangé par le retrait mécanique des Tasks 27-31, qui ne fait que retirer
  `transform.qgis` — **vérifier à la Task 27 Step 1** si cette op était comptée dans le total de départ 34
  avant de fixer le nombre final attendu, ne pas le supposer).
- `mypy --strict` ne couvre pas `app.pipelines` aujourd'hui (liste exacte dans `CLAUDE.md` § Commandes :
  `app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`) — vérifier si `app.secrets`
  (touché par les Tasks 11-17) est concerné avant d'écrire du code Pydantic non strictement typé.
- `ruff check`/`ruff format --check`/`lint-imports`/suite complète `core` doivent rester verts après chaque
  tâche.
- Toute nouvelle classe Pydantic porte une docstring française courte (tooltip de nœud dans
  `PipelinePalette.tsx` — aucun fichier `shell/` à modifier pour les op elles-mêmes, le canevas lit
  `GET /pipelines/ops` dynamiquement ; le formulaire de secret est vérifié séparément, Task 16).
- Convention de nommage déjà établie (Vague 1) : `transform.<verbeCamelCase>`, jamais le nom FME littéral.
- **Piège CLAUDE.md n°3** : toute signature DuckDB spatial/SQLAlchemy/dlt/Shapely utilisée dans ce plan a
  été vérifiée empiriquement pendant le brainstorming (existence confirmée), mais le **comportement
  sémantique exact** (cas limites, formes de credentials) reste à reconfirmer avant chaque test — jamais
  supposé acquis par ce seul document.
- Dernière tâche (Task 31) : régénérer `openapi.json`/`core-schema.d.ts`, mettre à jour la matrice de
  couverture FME, l'inventaire de fonctionnalités, et `CLAUDE.md` (§ Commandes, § stack, § Livré, note de
  rupture pour les déploiements existants).

---

### Task 1: `transform.bulkRemoveAttributes` + `transform.bulkRenameAttributes`

Ces deux op inaugurent le patron de tâche répété pour tout le plan : nouvelle classe Pydantic dans
`schemas.py`, nouvelle fonction `_compile_xxx` dans `compiler.py`, nouvelle entrée `OPERATIONS` dans
`contracts.py`, test dans `test_pipeline_compiler.py`.

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: `compile_transform_sql(op, params, *, input_view, join_view=None, input_srid=None) -> str`
  (`core/app/pipelines/compiler.py`, déjà existant), fixture `conn` (`tests/test_pipeline_compiler.py`,
  déjà existante : table `base(id INTEGER, region VARCHAR, pop INTEGER)`).
- Produces: `TransformBulkRemoveAttributesParams`, `TransformBulkRenameAttributesParams`
  (`app/pipelines/ops/schemas.py`) ; `_compile_bulk_remove_attributes`, `_compile_bulk_rename_attributes`
  (`app/pipelines/compiler.py`) ; entrées `"transform.bulkRemoveAttributes"`/`"transform.bulkRenameAttributes"`
  dans `OPERATIONS` (`app/pipelines/ops/contracts.py`).

- [ ] **Step 1: Write the failing tests**

Ajouter à `core/tests/test_pipeline_compiler.py` (à la suite des tests existants qui utilisent la fixture
`conn`, avant la fixture `conn_spatial`) :

```python
def test_compile_bulk_remove_attributes(conn):
    sql = compile_transform_sql(
        "transform.bulkRemoveAttributes",
        {"pattern": "^pop$"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["id", "region"]


def test_compile_bulk_rename_attributes(conn):
    sql = compile_transform_sql(
        "transform.bulkRenameAttributes",
        {"pattern": "^(pop)$", "replacement": r"\1_count"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert sorted(cols) == ["id", "pop_count", "region"]


def test_compile_bulk_rename_attributes_escapes_single_quotes(conn):
    sql = compile_transform_sql(
        "transform.bulkRenameAttributes",
        {"pattern": "^(pop)$", "replacement": "it's_\\1"},
        input_view="base",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert "it's_pop" in cols
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k bulk -v`
Expected: FAIL — `ValueError: 'transform.bulkRemoveAttributes' is not a transform op`

- [ ] **Step 3: Add the Pydantic param classes**

Dans `core/app/pipelines/ops/schemas.py`, ajouter après `TransformFormatCoordinatesParams` (dernière classe
du fichier) :

```python
class TransformBulkRemoveAttributesParams(BaseModel):
    """Supprime toutes les colonnes dont le nom correspond à un motif regex."""

    pattern: str


class TransformBulkRenameAttributesParams(BaseModel):
    """Renomme en masse les colonnes correspondant à un motif regex, par gabarit de
    remplacement avec rétro-référence (ex. pattern="foo_(.*)", replacement="\\1_bar")."""

    pattern: str
    replacement: str
```

- [ ] **Step 4: Add the compiler functions**

Dans `core/app/pipelines/compiler.py` :
1. Ajouter `TransformBulkRemoveAttributesParams` et `TransformBulkRenameAttributesParams` à l'import
   `from app.pipelines.ops.schemas import (...)` en tête de fichier (ordre alphabétique, comme les autres).
2. Ajouter juste avant `def compile_transform_sql(...)` :

```python
def _compile_bulk_remove_attributes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformBulkRemoveAttributesParams.model_validate(params)
    escaped = p.pattern.replace("'", "''")
    return f"SELECT COLUMNS(c -> NOT regexp_matches(c, '{escaped}')) FROM {_qi(input_view)}"


def _compile_bulk_rename_attributes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformBulkRenameAttributesParams.model_validate(params)
    escaped_pattern = p.pattern.replace("'", "''")
    escaped_replacement = p.replacement.replace("'", "''")
    return (
        f"SELECT COLUMNS(c -> NOT regexp_matches(c, '{escaped_pattern}')), "
        f"COLUMNS('{escaped_pattern}') AS '{escaped_replacement}' "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 5: Register the two new ops**

Dans `core/app/pipelines/ops/contracts.py` :
1. Ajouter `TransformBulkRemoveAttributesParams`, `TransformBulkRenameAttributesParams` à l'import depuis
   `app.pipelines.ops.schemas`.
2. Ajouter dans `OPERATIONS`, juste avant `"writer.collection"` :

```python
    "transform.bulkRemoveAttributes": OperationContract(
        op="transform.bulkRemoveAttributes",
        kind="transform",
        params_schema=TransformBulkRemoveAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bulk_remove_attributes,
    ),
    "transform.bulkRenameAttributes": OperationContract(
        op="transform.bulkRenameAttributes",
        kind="transform",
        params_schema=TransformBulkRenameAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bulk_rename_attributes,
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k bulk -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.bulkRemoveAttributes et bulkRenameAttributes"
```

---

### Task 2: `transform.scanSchema`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: même patron que Task 1.
- Produces: `TransformScanSchemaParams` ; `_compile_scan_schema` ; entrée `"transform.scanSchema"`.

- [ ] **Step 1: Write the failing test**

```python
def test_compile_scan_schema(conn):
    sql = compile_transform_sql("transform.scanSchema", {}, input_view="base")
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT column_name, column_type FROM out ORDER BY column_name").fetchall()
    assert rows == [
        ("id", "INTEGER"),
        ("pop", "INTEGER"),
        ("region", "VARCHAR"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k scan_schema -v`
Expected: FAIL — `ValueError: 'transform.scanSchema' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

Dans `core/app/pipelines/ops/schemas.py`, ajouter après les classes de la Task 1 :

```python
class TransformScanSchemaParams(BaseModel):
    """Retourne une ligne par colonne de l'entrée (columnName, columnType) — méta-introspection
    du schéma, sans transformation ligne à ligne."""
```

(Aucun champ — Pydantic accepte une classe `BaseModel` sans attribut.)

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformScanSchemaParams`. Fonction :

```python
def _compile_scan_schema(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformScanSchemaParams.model_validate(params)  # forme seulement, aucun champ
    return f"SELECT column_name AS columnName, column_type AS columnType FROM (DESCRIBE {_qi(input_view)})"
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformScanSchemaParams`. Entrée `OPERATIONS` :

```python
    "transform.scanSchema": OperationContract(
        op="transform.scanSchema",
        kind="transform",
        params_schema=TransformScanSchemaParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_scan_schema,
    ),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k scan_schema -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.scanSchema"
```

---

### Task 3: `transform.explodeList` + `transform.explodeGeometry` (cardinalité changée)

Ces deux op **changent le nombre de lignes en sortie** — vérifié en design (§0) que `runtime.py` ne suppose
jamais 1:1, aucun changement de `runtime.py` requis. Falsification explicite requise (piège CLAUDE.md n°10).

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: fixture `conn_spatial` (`tests/test_pipeline_compiler.py`, déjà existante : table
  `base(id INTEGER, geometry GEOMETRY)`, 2 points).
- Produces: `TransformExplodeListParams`, `TransformExplodeGeometryParams` ; `_compile_explode_list`,
  `_compile_explode_geometry` ; entrées `"transform.explodeList"`/`"transform.explodeGeometry"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_compile_explode_list_multiplies_rows(conn):
    conn.execute("CREATE TABLE with_list (id INTEGER, tags VARCHAR[])")
    conn.execute("INSERT INTO with_list VALUES (1, ['a', 'b', 'c']), (2, ['x'])")
    sql = compile_transform_sql(
        "transform.explodeList", {"column": "tags"}, input_view="with_list"
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, tags FROM out ORDER BY id, tags").fetchall()
    assert rows == [(1, "a"), (1, "b"), (1, "c"), (2, "x")]


def test_compile_explode_geometry_dumps_multipoint(conn_spatial):
    conn_spatial.execute(
        "CREATE TABLE multi (id INTEGER, geometry GEOMETRY)"
    )
    conn_spatial.execute(
        "INSERT INTO multi VALUES (1, ST_GeomFromText('MULTIPOINT (0 0, 1 1, 2 2)'))"
    )
    sql = compile_transform_sql("transform.explodeGeometry", {}, input_view="multi")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn_spatial.execute(
        "SELECT id, ST_AsText(geometry) FROM out ORDER BY ST_AsText(geometry)"
    ).fetchall()
    assert rows == [
        (1, "POINT (0 0)"),
        (1, "POINT (1 1)"),
        (1, "POINT (2 2)"),
    ]


def test_compile_explode_geometry_on_single_part_geometry_is_a_noop_on_row_count(conn_spatial):
    sql = compile_transform_sql("transform.explodeGeometry", {}, input_view="base")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    count = conn_spatial.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count == 2  # falsification : un point simple ne se dédouble pas
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k explode -v`
Expected: FAIL — `ValueError: 'transform.explodeList' is not a transform op`

- [ ] **Step 3: Add the Pydantic param classes**

```python
class TransformExplodeListParams(BaseModel):
    """Explose une colonne LIST en plusieurs lignes (une par élément), autres colonnes
    dupliquées."""

    column: str


class TransformExplodeGeometryParams(BaseModel):
    """Explose une géométrie multi-partie (MULTIPOINT/MULTILINESTRING/MULTIPOLYGON/
    GEOMETRYCOLLECTION) en une ligne par sous-géométrie simple. Sans effet sur une géométrie
    déjà simple (le nombre de lignes ne change pas)."""
```

- [ ] **Step 4: Add the compiler functions**

Imports à ajouter dans `compiler.py` : `TransformExplodeGeometryParams`, `TransformExplodeListParams`.

```python
def _compile_explode_list(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExplodeListParams.model_validate(params)
    col = _qi(p.column)
    return (
        f"SELECT * EXCLUDE ({col}), UNNEST({col}) AS {col} FROM {_qi(input_view)}"
    )


def _compile_explode_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformExplodeGeometryParams.model_validate(params)  # forme seulement, aucun champ
    return (
        f"SELECT * EXCLUDE (geometry), unnest(ST_Dump(geometry)).geom AS geometry "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 5: Register the two new ops**

Imports à ajouter dans `contracts.py` : `TransformExplodeGeometryParams`, `TransformExplodeListParams`.

```python
    "transform.explodeList": OperationContract(
        op="transform.explodeList",
        kind="transform",
        params_schema=TransformExplodeListParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_explode_list,
    ),
    "transform.explodeGeometry": OperationContract(
        op="transform.explodeGeometry",
        kind="transform",
        params_schema=TransformExplodeGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_explode_geometry,
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k explode -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.explodeList et transform.explodeGeometry"
```

---

### Task 4: `transform.exposeAttributes`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: fixture `conn` (déjà existante).
- Produces: `TransformExposeAttributesParams` ; `_compile_expose_attributes` ; entrée
  `"transform.exposeAttributes"`.

- [ ] **Step 1: Write the failing test**

```python
def test_compile_expose_attributes_expands_struct_fields(conn):
    conn.execute("CREATE TABLE nested (id INTEGER, payload STRUCT(a INTEGER, b VARCHAR))")
    conn.execute("INSERT INTO nested VALUES (1, {'a': 10, 'b': 'x'})")
    sql = compile_transform_sql(
        "transform.exposeAttributes", {"column": "payload"}, input_view="nested"
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn.execute("SELECT id, a, b FROM out").fetchone()
    assert row == (1, 10, "x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k expose_attributes -v`
Expected: FAIL — `ValueError: 'transform.exposeAttributes' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

```python
class TransformExposeAttributesParams(BaseModel):
    """Expose les champs d'une colonne STRUCT (ou LIST-de-STRUCT) source comme colonnes
    top-level, sans connaître leurs noms à l'avance."""

    column: str
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformExposeAttributesParams`.

```python
def _compile_expose_attributes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformExposeAttributesParams.model_validate(params)
    col = _qi(p.column)
    return f"SELECT * EXCLUDE ({col}), {col}.* FROM {_qi(input_view)}"
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformExposeAttributesParams`.

```python
    "transform.exposeAttributes": OperationContract(
        op="transform.exposeAttributes",
        kind="transform",
        params_schema=TransformExposeAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_expose_attributes,
    ),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k expose_attributes -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.exposeAttributes"
```

---

### Task 5: `transform.validateAttributes`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: fixture `conn` (déjà existante).
- Produces: `TransformValidateAttributesParams` ; `_compile_validate_attributes` ; entrée
  `"transform.validateAttributes"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_compile_validate_attributes_checks_non_null_columns(conn):
    conn.execute("CREATE TABLE nullable (id INTEGER, region VARCHAR)")
    conn.execute("INSERT INTO nullable VALUES (1, 'Nord'), (2, NULL)")
    sql = compile_transform_sql(
        "transform.validateAttributes",
        {"nonNullColumns": ["region"], "nonNullResultColumn": "isValid"},
        input_view="nullable",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, isValid FROM out ORDER BY id").fetchall()
    assert rows == [(1, True), (2, False)]


def test_compile_validate_attributes_checks_uniqueness(conn):
    conn.execute("CREATE TABLE dupes (id INTEGER, region VARCHAR)")
    conn.execute("INSERT INTO dupes VALUES (1, 'Nord'), (2, 'Nord'), (3, 'Sud')")
    sql = compile_transform_sql(
        "transform.validateAttributes",
        {"uniqueColumns": ["region"], "uniqueResultColumn": "isUnique"},
        input_view="dupes",
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT id, isUnique FROM out ORDER BY id").fetchall()
    assert rows == [(1, False), (2, False), (3, True)]


def test_compile_validate_attributes_requires_at_least_one_check():
    with pytest.raises(Exception, match="at least one"):
        compile_transform_sql("transform.validateAttributes", {}, input_view="base")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k validate_attributes -v`
Expected: FAIL — `ValueError: 'transform.validateAttributes' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

```python
class TransformValidateAttributesParams(BaseModel):
    """Valide des attributs explicites (non-null et/ou unicité) et écrit le résultat booléen
    dans une colonne dédiée par vérification demandée. Colonnes explicites uniquement — pas de
    mode « toutes les colonnes automatiquement »."""

    nonNullColumns: list[str] = Field(default_factory=list)
    nonNullResultColumn: str | None = None
    uniqueColumns: list[str] = Field(default_factory=list)
    uniqueResultColumn: str | None = None

    @model_validator(mode="after")
    def _at_least_one_check(self) -> "TransformValidateAttributesParams":
        has_non_null = bool(self.nonNullColumns) and self.nonNullResultColumn is not None
        has_unique = bool(self.uniqueColumns) and self.uniqueResultColumn is not None
        if not has_non_null and not has_unique:
            raise ValueError(
                "transform.validateAttributes requires at least one check "
                "(nonNullColumns+nonNullResultColumn or uniqueColumns+uniqueResultColumn)"
            )
        return self
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformValidateAttributesParams`.

```python
def _compile_validate_attributes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformValidateAttributesParams.model_validate(params)
    extra_cols = []
    if p.nonNullColumns and p.nonNullResultColumn:
        checks = " AND ".join(f"{_qi(c)} IS NOT NULL" for c in p.nonNullColumns)
        extra_cols.append(f"({checks}) AS {_qi(p.nonNullResultColumn)}")
    if p.uniqueColumns and p.uniqueResultColumn:
        partition = ", ".join(_qi(c) for c in p.uniqueColumns)
        extra_cols.append(
            f"(COUNT(*) OVER (PARTITION BY {partition}) = 1) AS {_qi(p.uniqueResultColumn)}"
        )
    return f"SELECT *, {', '.join(extra_cols)} FROM {_qi(input_view)}"
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformValidateAttributesParams`.

```python
    "transform.validateAttributes": OperationContract(
        op="transform.validateAttributes",
        kind="transform",
        params_schema=TransformValidateAttributesParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_validate_attributes,
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k validate_attributes -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.validateAttributes"
```

---

### Task 6: `transform.sort` (+ falsification de l'ordre)

Décision assumée en design (§3.3) : aucune restriction structurelle sur ce qui suit un nœud `transform.sort`
— documenté comme best-effort au-delà d'un writer direct. Ce test de falsification doit tourner à une échelle
qui déclenche un vrai parallélisme DuckDB (pas une intuition, piège CLAUDE.md n°7).

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: fixture `conn`/`conn_spatial` (déjà existantes) ; `run_pipeline`/`preview_pipeline`
  (`app/pipelines/runtime.py`, déjà existants — vérifier leur signature exacte dans le fichier avant d'écrire
  le test d'intégration, ne pas la deviner).
- Produces: `TransformSortParams` (avec sous-modèle `SortKey`) ; `_compile_sort` ; entrée
  `"transform.sort"`.

- [ ] **Step 1: Write the failing unit tests**

```python
def test_compile_sort_by_single_column_ascending(conn):
    sql = compile_transform_sql(
        "transform.sort", {"by": [{"column": "pop", "direction": "asc"}]}, input_view="base"
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = conn.execute("SELECT pop FROM out").fetchall()
    assert rows == [(5,), (10,), (20,)]


def test_compile_sort_by_spatial_hilbert(conn_spatial):
    sql = compile_transform_sql(
        "transform.sort", {"bySpatialHilbert": True}, input_view="base"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    count = conn_spatial.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count == 2  # falsification de forme : la requête s'exécute et ne perd aucune ligne


def test_compile_sort_requires_at_least_one_sort_key():
    with pytest.raises(Exception, match="at least one"):
        compile_transform_sql("transform.sort", {}, input_view="base")
```

- [ ] **Step 2: Run unit tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "sort and not resort" -v`
Expected: FAIL — `ValueError: 'transform.sort' is not a transform op`

- [ ] **Step 3: Add the Pydantic param classes**

`ST_Hilbert` prend une géométrie et une boîte englobante de référence (`bounds`) — **vérifier la signature
exacte contre un DuckDB réel avant d'écrire l'implémentation** (piège CLAUDE.md n°3) :

```bash
cd core && uv run python3 -c "
import duckdb
c = duckdb.connect(':memory:')
c.execute('INSTALL spatial; LOAD spatial;')
print(c.execute(\"SELECT function_name, parameters FROM duckdb_functions() WHERE function_name = 'st_hilbert'\").fetchall())
"
```

Puis ajouter dans `schemas.py` :

```python
class SortKey(BaseModel):
    column: str
    direction: Literal["asc", "desc"] = "asc"


class TransformSortParams(BaseModel):
    """Trie les lignes par une liste de colonnes et/ou par proximité spatiale (courbe de
    Hilbert sur la géométrie). Ordre garanti uniquement pour un nœud writer directement
    connecté en aval — au-delà, best-effort (décision assumée, design §3.3)."""

    by: list[SortKey] = Field(default_factory=list)
    bySpatialHilbert: bool = False

    @model_validator(mode="after")
    def _at_least_one_sort_key(self) -> "TransformSortParams":
        if not self.by and not self.bySpatialHilbert:
            raise ValueError("transform.sort requires at least one sort key (by or bySpatialHilbert)")
        return self
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformSortParams`. Implémentation — **adapter l'appel
`ST_Hilbert` selon la signature confirmée à l'étape 3** (l'exemple ci-dessous suppose une signature
`ST_Hilbert(geometry, bounds BOX_2D)` avec un `ST_Extent_Agg` calculé sur la vue comme `bounds`, à ajuster si
la vraie signature diffère) :

```python
def _compile_sort(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformSortParams.model_validate(params)
    order_parts = []
    if p.bySpatialHilbert:
        order_parts.append(
            f"ST_Hilbert(geometry, (SELECT ST_Extent_Agg(geometry) FROM {_qi(input_view)}))"
        )
    order_parts += [f"{_qi(k.column)} {k.direction.upper()}" for k in p.by]
    return f"SELECT * FROM {_qi(input_view)} ORDER BY {', '.join(order_parts)}"
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformSortParams`.

```python
    "transform.sort": OperationContract(
        op="transform.sort",
        kind="transform",
        params_schema=TransformSortParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_sort,
    ),
```

- [ ] **Step 6: Run unit tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "sort and not resort" -v`
Expected: PASS (3 tests)

- [ ] **Step 7: Write the order-preservation falsification test**

Lire d'abord la signature réelle de `run_pipeline`/`preview_pipeline` et de `PipelinePayload`/`PipelineNode`
(`core/app/configs/schemas.py`, `core/app/pipelines/runtime.py`) pour construire un payload valide — ne pas
deviner les champs. Ajouter à `core/tests/test_pipeline_runtime.py` un test construisant un pipeline à 3
nœuds (`reader.collection` sur une collection à ~20 000 lignes non triées → `transform.sort` sur une colonne
entière → `writer.dataset` ou équivalent), l'exécutant réellement, et vérifiant que les lignes du writer
final sortent triées. Documenter le résultat dans le message de commit (Step 9) : « ordre préservé à cette
échelle » ou le contraire — jamais « le test passe » sans le chiffre réel.

- [ ] **Step 8: Run the falsification test**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k sort_order -v`
Expected: PASS, avec le volume de données réellement utilisé noté dans la sortie du test ou un commentaire.

- [ ] **Step 9: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py \
  core/tests/test_pipeline_runtime.py
git commit -m "feat(pipelines): ajoute transform.sort (ordre best-effort au-delà d'un writer direct)"
```

---

### Task 7: Mécanisme `needs_columns` + `transform.detectChanges`

Premier des 3 op nécessitant la liste réelle des colonnes d'entrée. Construit le mécanisme et son premier
consommateur ensemble (TDD sur le comportement observable, pas sur un mécanisme isolé sans consommateur).

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_compiler.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `OperationContract` dataclass (`app/pipelines/ops/contracts.py`, déjà existant) ;
  `_JOIN_PARAM_MODELS` (`app/pipelines/runtime.py:80`, déjà existant) ; `_execute_transform_chain`
  (`app/pipelines/runtime.py:663`, déjà existant).
- Produces: nouveau champ `needs_columns: bool = False` sur `OperationContract` ; `compile_transform_sql`
  accepte deux nouveaux kwargs optionnels `input_columns: list[str] | None = None`,
  `join_columns: list[str] | None = None`, ne les transmet à `contract.compile` que si
  `contract.needs_columns` est vrai ; `TransformDetectChangesParams` ; `_compile_detect_changes(params, *,
  input_view, join_view=None, input_srid=None, input_columns=None, join_columns=None) -> str` ; entrée
  `"transform.detectChanges"` (`accepts_secondary_input=True`, `needs_columns=True`).

- [ ] **Step 1: Write the failing compiler-level test**

```python
def test_compile_detect_changes_marks_inserted_deleted_updated_unchanged(conn):
    conn.execute("CREATE TABLE before_t (id INTEGER, region VARCHAR)")
    conn.execute(
        "INSERT INTO before_t VALUES (1, 'Nord'), (2, 'Sud'), (3, 'Est')"
    )
    conn.execute("CREATE TABLE after_t (id INTEGER, region VARCHAR)")
    conn.execute(
        "INSERT INTO after_t VALUES (1, 'Nord'), (2, 'Ouest'), (4, 'Sud')"
    )
    sql = compile_transform_sql(
        "transform.detectChanges",
        {"keyColumns": ["id"], "statusColumn": "status"},
        input_view="before_t",
        join_view="after_t",
        input_columns=["id", "region"],
        join_columns=["id", "region"],
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    rows = dict(
        (row[0], row[-1]) for row in conn.execute("SELECT * FROM out ORDER BY id NULLS LAST").fetchall()
    )
    # id=1 inchangé, id=2 modifié (region différente), id=3 supprimé, id=4 ajouté
    assert rows[1] == "unchanged"
    assert rows[2] == "updated"
    assert rows[3] == "deleted"
    assert rows[4] == "inserted"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k detect_changes -v`
Expected: FAIL — `TypeError: compile_transform_sql() got an unexpected keyword argument 'input_columns'`

- [ ] **Step 3: Add `needs_columns` to `OperationContract`**

Dans `core/app/pipelines/ops/contracts.py`, ajouter le champ juste après `execution_model` :

```python
    # Vague 2 (design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md
    # §3.1) : quand True, compile_transform_sql résout input_columns/join_columns via un
    # DESCRIBE (app.pipelines.runtime) avant d'appeler `compile` — extension chirurgicale,
    # jamais de connexion DuckDB dans ce module lui-même.
    needs_columns: bool = False
```

- [ ] **Step 4: Extend `compile_transform_sql` to conditionally pass columns**

Dans `core/app/pipelines/compiler.py`, remplacer la fonction `compile_transform_sql` existante par :

```python
def compile_transform_sql(
    op: str,
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    from app.pipelines.ops.contracts import OPERATIONS

    contract = OPERATIONS.get(op)
    if contract is None or contract.compile is None:
        raise ValueError(f"'{op}' is not a transform op")
    kwargs: dict = {"input_view": input_view, "join_view": join_view, "input_srid": input_srid}
    if contract.needs_columns:
        kwargs["input_columns"] = input_columns
        kwargs["join_columns"] = join_columns
    return contract.compile(params, **kwargs)
```

- [ ] **Step 5: Add the Pydantic param class**

```python
class TransformDetectChangesParams(BaseModel):
    """Compare l'entrée principale (état « avant ») à une collection ou un flux secondaire
    (état « après ») sur des colonnes clés, et écrit le statut de chaque ligne
    (inserted/deleted/updated/unchanged) — comparaison automatique de toutes les colonnes
    communes, résolues à l'exécution."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    keyColumns: list[str]
    statusColumn: str
```

- [ ] **Step 6: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformDetectChangesParams`.

```python
def _compile_detect_changes(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformDetectChangesParams.model_validate(params)
    assert join_view is not None, "transform.detectChanges requires join_view"
    assert input_columns is not None and join_columns is not None
    common_cols = [c for c in input_columns if c in join_columns and c not in p.keyColumns]
    key_join = " AND ".join(f"t.{_qi(k)} = o.{_qi(k)}" for k in p.keyColumns)
    key_select = ", ".join(f"COALESCE(t.{_qi(k)}, o.{_qi(k)}) AS {_qi(k)}" for k in p.keyColumns)
    if common_cols:
        diff_expr = " OR ".join(
            f"t.{_qi(c)} IS DISTINCT FROM o.{_qi(c)}" for c in common_cols
        )
    else:
        diff_expr = "FALSE"
    status_expr = (
        f"CASE "
        f"WHEN t.{_qi(p.keyColumns[0])} IS NULL THEN 'inserted' "
        f"WHEN o.{_qi(p.keyColumns[0])} IS NULL THEN 'deleted' "
        f"WHEN {diff_expr} THEN 'updated' "
        f"ELSE 'unchanged' END"
    )
    return (
        f"SELECT {key_select}, ({status_expr}) AS {_qi(p.statusColumn)} "
        f"FROM {_qi(input_view)} t FULL OUTER JOIN {_qi(join_view)} o ON {key_join}"
    )
```

- [ ] **Step 7: Register the op**

Import à ajouter dans `contracts.py` : `TransformDetectChangesParams`.

```python
    "transform.detectChanges": OperationContract(
        op="transform.detectChanges",
        kind="transform",
        params_schema=TransformDetectChangesParams,
        accepts_secondary_input=True,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_detect_changes,
    ),
```

- [ ] **Step 8: Run compiler-level test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k detect_changes -v`
Expected: PASS

- [ ] **Step 9: Wire column resolution into `runtime.py`**

Dans `core/app/pipelines/runtime.py` :
1. Ajouter `"transform.detectChanges": TransformDetectChangesParams` à `_JOIN_PARAM_MODELS` (ligne ~80),
   et l'import correspondant.
2. Dans `_execute_transform_chain`, juste avant l'appel à `compiler.compile_transform_sql` (ligne ~725),
   résoudre les colonnes uniquement quand nécessaire :

```python
        from app.pipelines.ops.contracts import OPERATIONS

        contract = OPERATIONS[node.op]
        input_columns = None
        join_columns = None
        if contract.needs_columns:
            input_columns = [
                d[0] for d in conn.execute(f"DESCRIBE {_qi(input_view)}").fetchall()
            ]
            if join_view is not None:
                join_columns = [
                    d[0] for d in conn.execute(f"DESCRIBE {_qi(join_view)}").fetchall()
                ]
        sql = compiler.compile_transform_sql(
            node.op,
            node.params,
            input_view=input_view,
            join_view=join_view,
            input_srid=input_srid,
            input_columns=input_columns,
            join_columns=join_columns,
        )
```

(`DESCRIBE` retourne `column_name` en première colonne — vérifier ce format contre `conn.execute("DESCRIBE
...").description` avant de fixer l'index `[0]`, ne pas le supposer sans lire la vraie sortie.)

- [ ] **Step 10: Write the end-to-end column-resolution test**

Lire d'abord la signature exacte de `run_pipeline`/`PipelinePayload`/`PipelineNode`/`PipelineEdge`
(`core/app/configs/schemas.py`, `core/app/pipelines/runtime.py`) avant d'écrire ce test — ne pas deviner les
champs. Ajouter à `core/tests/test_pipeline_runtime.py` un test exécutant un pipeline à 2 lecteurs +
1 `transform.detectChanges` de bout en bout (falsification explicite : renommer une colonne entre
l'écriture de la config et l'exécution, confirmer que le SQL généré s'adapte plutôt que de référencer une
colonne disparue — cf. design §4).

- [ ] **Step 11: Run the end-to-end test**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k detect_changes -v`
Expected: PASS

- [ ] **Step 12: Run the full compiler + runtime test suites**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py tests/test_pipeline_runtime.py -v`
Expected: PASS (aucune régression sur les 34 op existantes ni les op déjà ajoutées par ce plan)

- [ ] **Step 13: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/app/pipelines/runtime.py \
  core/tests/test_pipeline_compiler.py core/tests/test_pipeline_runtime.py
git commit -m "feat(pipelines): ajoute le mécanisme needs_columns et transform.detectChanges"
```

---

### Task 8: `transform.mergeChildren`

Réutilise le mécanisme `needs_columns` de la Task 7.

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mécanisme `needs_columns`/`input_columns`/`join_columns` (Task 7).
- Produces: `TransformMergeChildrenParams` ; `_compile_merge_children` ; entrée
  `"transform.mergeChildren"` (`accepts_secondary_input=True`, `needs_columns=True`).

- [ ] **Step 1: Write the failing test**

```python
def test_compile_merge_children_packs_matching_rows_into_a_struct_list(conn):
    conn.execute("CREATE TABLE parents (id INTEGER, name VARCHAR)")
    conn.execute("INSERT INTO parents VALUES (1, 'A'), (2, 'B')")
    conn.execute("CREATE TABLE children (parentId INTEGER, label VARCHAR)")
    conn.execute(
        "INSERT INTO children VALUES (1, 'c1'), (1, 'c2'), (2, 'c3')"
    )
    sql = compile_transform_sql(
        "transform.mergeChildren",
        {"on": "id", "childrenColumn": "children"},
        input_view="parents",
        join_view="children",
        input_columns=["id", "name"],
        join_columns=["parentId", "label"],
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn.execute("SELECT id, name, children FROM out WHERE id = 1").fetchone()
    assert row[0:2] == (1, "A")
    assert len(row[2]) == 2
```

(Le param `on` désigne ici la colonne clé côté parent — vérifier au moment d'implémenter si `children.on`
diffère de `parents.on` dans le cas général et ajuster le modèle de params en conséquence plutôt que de
supposer qu'ils partagent toujours le même nom de colonne.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k merge_children -v`
Expected: FAIL — `ValueError: 'transform.mergeChildren' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

```python
class TransformMergeChildrenParams(BaseModel):
    """Rattache à chaque ligne principale (parent) la liste des lignes correspondantes de
    l'entrée secondaire (enfants), regroupées en une colonne LIST de STRUCT — schéma des
    enfants résolu à l'exécution."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    on: str
    childrenColumn: str
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformMergeChildrenParams`.

```python
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
    child_cols = [c for c in join_columns if c != p.on]
    struct_fields = ", ".join(f"{_qi(c)} := o.{_qi(c)}" for c in child_cols)
    return (
        f"SELECT t.*, list(struct_pack({struct_fields})) AS {_qi(p.childrenColumn)} "
        f"FROM {_qi(input_view)} t LEFT JOIN {_qi(join_view)} o "
        f"ON t.{_qi(p.on)} = o.{_qi(p.on)} GROUP BY ALL"
    )
```

(`GROUP BY ALL` regroupe implicitement par toutes les colonnes non agrégées — vérifier contre un DuckDB réel
que `t.*` combiné à `GROUP BY ALL` fonctionne comme attendu avec plusieurs colonnes parent, pas seulement
`id`/`name` du test.)

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformMergeChildrenParams`.

```python
    "transform.mergeChildren": OperationContract(
        op="transform.mergeChildren",
        kind="transform",
        params_schema=TransformMergeChildrenParams,
        accepts_secondary_input=True,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_merge_children,
    ),
```

- [ ] **Step 6: Wire into `runtime.py`**

Ajouter `"transform.mergeChildren": TransformMergeChildrenParams` à `_JOIN_PARAM_MODELS`
(`core/app/pipelines/runtime.py`), avec l'import correspondant. Aucun autre changement à `runtime.py` — le
dispatch `needs_columns` générique de la Task 7 couvre déjà ce nouveau cas.

- [ ] **Step 7: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k merge_children -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/app/pipelines/runtime.py \
  core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.mergeChildren"
```

---

### Task 9: `transform.mapSchema`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: mécanisme `needs_columns`/`input_columns` (Task 7, pas de `join_columns` requis ici — pas
  d'entrée secondaire).
- Produces: `TransformMapSchemaParams` ; `_compile_map_schema` ; entrée `"transform.mapSchema"`
  (`needs_columns=True`, pas de `accepts_secondary_input`).

- [ ] **Step 1: Write the failing tests**

```python
def test_compile_map_schema_fills_missing_target_columns_with_null(conn):
    sql = compile_transform_sql(
        "transform.mapSchema",
        {"targetColumns": ["id", "region", "elevation"]},
        input_view="base",
        input_columns=["id", "region", "pop"],
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["id", "region", "elevation"]
    row = conn.execute("SELECT elevation FROM out LIMIT 1").fetchone()
    assert row == (None,)


def test_compile_map_schema_drops_source_columns_not_in_target_list(conn):
    sql = compile_transform_sql(
        "transform.mapSchema",
        {"targetColumns": ["id"]},
        input_view="base",
        input_columns=["id", "region", "pop"],
    )
    conn.execute(f"CREATE TEMP VIEW out AS {sql}")
    cols = [d[0] for d in conn.execute("SELECT * FROM out LIMIT 0").description]
    assert cols == ["id"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k map_schema -v`
Expected: FAIL — `ValueError: 'transform.mapSchema' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

```python
class TransformMapSchemaParams(BaseModel):
    """Reprojette le schéma de l'entrée sur une liste de colonnes cible statique, dans
    l'ordre : correspondance par nom de colonne identique, colonne cible absente de la
    source → NULL, colonne source hors de la liste cible → éliminée."""

    targetColumns: list[str]
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformMapSchemaParams`.

```python
def _compile_map_schema(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
    input_columns: list[str] | None = None,
    join_columns: list[str] | None = None,
) -> str:
    p = TransformMapSchemaParams.model_validate(params)
    assert input_columns is not None
    select_parts = [
        f"{_qi(c)}" if c in input_columns else f"NULL AS {_qi(c)}" for c in p.targetColumns
    ]
    return f"SELECT {', '.join(select_parts)} FROM {_qi(input_view)}"
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformMapSchemaParams`.

```python
    "transform.mapSchema": OperationContract(
        op="transform.mapSchema",
        kind="transform",
        params_schema=TransformMapSchemaParams,
        needs_columns=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_map_schema,
    ),
```

- [ ] **Step 6: Wire into `runtime.py`**

Aucun changement requis : `transform.mapSchema` n'a pas d'entrée secondaire, le dispatch générique de la
Task 7 (`if contract.needs_columns: input_columns = DESCRIBE(input_view)`) le couvre déjà — `join_columns`
reste `None` pour cet op, jamais lu par `_compile_map_schema`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k map_schema -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.mapSchema"
```

---

### Task 10: Filet de non-régression + clôture

**Files:**
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ou équivalent — vérifier le nom exact du fichier qui
  porte aujourd'hui l'assertion sur le compte total d'op)
- Modify: `core/tests/test_pipeline_routes.py`
- Modify: `docs/revue/matrice-couverture-fme.jsonl`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: `OPERATIONS` (`app/pipelines/ops/contracts.py`), `ops_catalog()`/`GET /pipelines/ops`.
- Produces: rien de nouveau — clôture du plan.

- [ ] **Step 1: Chercher le test existant qui compte les op**

Run: `cd core && grep -rn "len(OPERATIONS)\|thirty_four\|== 34" tests/`

- [ ] **Step 2: Mettre à jour ce test à 45**

Renommer la fonction si son nom encode le compte (ex. `test_get_pipelines_ops_returns_all_thirty_four` →
`test_get_pipelines_ops_returns_all_forty_five`), et ajouter les 11 nouvelles clés à l'ensemble attendu
(`test_pipeline_routes.py`, `set(body) == {...}`) :

```python
        "transform.bulkRemoveAttributes",
        "transform.bulkRenameAttributes",
        "transform.scanSchema",
        "transform.explodeList",
        "transform.explodeGeometry",
        "transform.exposeAttributes",
        "transform.validateAttributes",
        "transform.sort",
        "transform.detectChanges",
        "transform.mergeChildren",
        "transform.mapSchema",
```

Ajouter aussi `"transform.detectChanges"` et `"transform.mergeChildren"` à la liste des op vérifiées
`acceptsSecondaryInput is True` dans ce même test.

- [ ] **Step 3: Ajouter un test dédié `len(OPERATIONS)`**

Si aucun test de ce type n'existe déjà ailleurs (Step 1 fait foi), en ajouter un dans
`core/tests/test_pipeline_ops_contracts.py` :

```python
def test_operations_registry_has_forty_five_entries():
    from app.pipelines.ops.contracts import OPERATIONS

    assert len(OPERATIONS) == 45
```

- [ ] **Step 4: Run the full pipelines test suite**

Run: `cd core && uv run pytest tests/ -k pipeline -v`
Expected: PASS, aucune régression.

- [ ] **Step 5: Run the full core test suite + quality gates**

```bash
cd core
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
```
Expected: tout vert.

- [ ] **Step 6: Régénérer OpenAPI + types TS**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: diff non vide sur `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` (11 nouveaux
schémas de params).

- [ ] **Step 7: Mettre à jour la matrice de couverture FME**

Dans `docs/revue/matrice-couverture-fme.jsonl`, pour chacune des 12 lignes suivantes, passer
`coverage_status` de `planned_duckdb` à `implemented` et renseigner `geostudio_equivalent` :
`AttributeValidator`→`transform.validateAttributes`, `BulkAttributeRemover`→
`transform.bulkRemoveAttributes`, `BulkAttributeRenamer`→`transform.bulkRenameAttributes`,
`ChangeDetector`→`transform.detectChanges`, `Deaggregator`→`transform.explodeGeometry`,
`FeatureMerger`→`transform.mergeChildren`, `ListExploder`→`transform.explodeList`,
`SchemaMapper`→`transform.mapSchema`, `SchemaScanner`→`transform.scanSchema`,
`Sorter`→`transform.sort`, `SpatialSorter`→`transform.sort`,
`AttributeExposer`→`transform.exposeAttributes`. Puis :

```bash
python3 core/scripts/fme_coverage_cli.py --write
python3 core/scripts/fme_coverage_cli.py --check
```
Expected: `--check` sort en succès.

- [ ] **Step 8: Régénérer le bilan de fonctionnalités**

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
```
Expected: pas d'erreur (`GET /pipelines/ops` existe déjà, aucune nouvelle route).

- [ ] **Step 9: Mettre à jour `CLAUDE.md`**

Ajouter une ligne dans `### Livré` : « **Vague 2 transformers DuckDB (schéma/cardinalité)** — 11 nouvelles op
(bulkRemoveAttributes/bulkRenameAttributes/scanSchema/explodeList/explodeGeometry/exposeAttributes/
validateAttributes/sort/detectChanges/mergeChildren/mapSchema), catalogue à 45 op, mécanisme
`needs_columns` pour l'introspection de schéma à l'exécution. »

- [ ] **Step 10: Commit**

```bash
git add core/tests/ docs/revue/matrice-couverture-fme.jsonl docs/revue/bilan-fonctionnalites.* \
  core/openapi.json shell/src/api/generated/core-schema.d.ts CLAUDE.md
git commit -m "test(pipelines): filet de non-régression + clôture Vague 2 transform ops (45 op)"
```

---

### Task 11: Lire le patron existant (aucun changement de code)

**Files:**
- Read: `core/app/pipelines/connector_runtime.py:282-358` (`materialize_postgres_connector`,
  `materialize_snowflake_connector`)
- Read: `core/app/secrets/schemas.py` (classes `PostgresDsnPayload`, `SnowflakeDsnPayload`,
  `SecretPayload` union discriminée)
- Read: `core/app/pipelines/ops/schemas.py:189-232` (`ReaderConnectorPostgresParams`,
  `ReaderConnectorSnowflakeParams`)
- Read: `core/app/pipelines/ops/contracts.py` (entrées `reader.connector.postgres`/`snowflake` dans
  `OPERATIONS`)
- Read: `core/tests/test_pipeline_connector_runtime.py` (tests existants pour postgres/snowflake — patron à
  reproduire pour bigquery/mssql/oracle/blob)

- [ ] **Step 1: Lire les 5 fichiers listés ci-dessus**

Aucune modification. Objectif : confirmer que le patron décrit dans le design (§6.1) correspond exactement
au code réel avant de commencer à écrire les 4 nouvelles op — en particulier la forme exacte de
`_run_dlt_and_attach`, `_resolve_secret`, et la structure `@dlt.resource(name="records",
write_disposition="replace")` utilisée par les 2 connecteurs existants.

- [ ] **Step 2: Pas de commit** (tâche de lecture seule)

---

### Task 12: `reader.connector.bigquery`

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes: `SecretResolver` (`connector_runtime.py`, déjà existant), `_resolve_secret`,
  `_run_dlt_and_attach`, `validate_select_only`/`parse_ast` (`app.analytics.sql_sandbox`, déjà importés).
- Produces: `BigQueryDsnPayload` (`app/secrets/schemas.py`) ; `ReaderConnectorBigQueryParams`
  (`app/pipelines/ops/schemas.py`) ; `materialize_bigquery_connector(conn, *, secret_resolver, node_id,
  params, view_name) -> None` (`connector_runtime.py`) ; entrée `"reader.connector.bigquery"`.

- [ ] **Step 1: Vérifier la forme du DSN attendue par `sqlalchemy-bigquery`**

Rechercher le README réel du paquet `sqlalchemy-bigquery` (PyPI) pour confirmer la forme du DSN et comment
l'authentification par compte de service est fournie à `sa.create_engine()` — pas de credentials_path (un
chemin de fichier ne survivrait pas au trajet secret chiffré → chaîne opaque → DSN, cf. design §6.1). Si le
dialecte accepte un JSON de compte de service inline dans le DSN ou via un paramètre de requête encodé,
documenter la forme choisie dans la docstring de `BigQueryDsnPayload` (Step 2) — sinon, si aucune forme DSN
opaque ne fonctionne, écrire dans le message de commit final pourquoi (ex. nécessite un fichier credentials
sur disque, question à trancher séparément) plutôt que de forcer une implémentation qui ne marche pas.

- [ ] **Step 2: Write the failing test**

```python
def test_materialize_bigquery_connector_rejects_non_select_query(conn):
    class _FakeResolver:
        def get(self, name):
            from app.secrets.schemas import BigQueryDsnPayload

            return BigQueryDsnPayload(dsn="bigquery://project/dataset")

    with pytest.raises(ConnectorRuntimeError, match="rejected"):
        materialize_bigquery_connector(
            conn,
            secret_resolver=_FakeResolver(),
            node_id="n1",
            params=ReaderConnectorBigQueryParams(secretName="s1", query="DELETE FROM t"),
            view_name="out",
        )


def test_materialize_bigquery_connector_rejects_wrong_secret_kind(conn):
    class _FakeResolver:
        def get(self, name):
            from app.secrets.schemas import PostgresDsnPayload

            return PostgresDsnPayload(dsn="postgresql://x")

    with pytest.raises(ConnectorRuntimeError, match="bigquery_dsn"):
        materialize_bigquery_connector(
            conn,
            secret_resolver=_FakeResolver(),
            node_id="n1",
            params=ReaderConnectorBigQueryParams(secretName="s1", query="SELECT 1"),
            view_name="out",
        )
```

(Reproduire exactement la fixture `conn`/les imports en tête de fichier utilisés par les tests
postgres/snowflake existants de `test_pipeline_connector_runtime.py`, lus à la Task 11.)

- [ ] **Step 2bis: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k bigquery -v`
Expected: FAIL — `ImportError`/`NameError` (rien n'existe encore)

- [ ] **Step 3: Add `BigQueryDsnPayload`**

Dans `core/app/secrets/schemas.py`, ajouter (forme confirmée au Step 1) :

```python
class BigQueryDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers Google BigQuery, forme confirmée contre le README de
    sqlalchemy-bigquery (à documenter précisément ici une fois vérifié, Step 1 du plan). Comme
    postgres_dsn/snowflake_dsn : le cœur ne parse ni ne valide ce DSN, il le passe tel quel à
    sa.create_engine()."""

    kind: Literal["bigquery_dsn"] = "bigquery_dsn"
    dsn: str
```

Ajouter `BigQueryDsnPayload` à l'union `SecretPayload` (`Annotated[... | BigQueryDsnPayload, ...]`).

- [ ] **Step 4: Add `ReaderConnectorBigQueryParams`**

Dans `core/app/pipelines/ops/schemas.py`, après `ReaderConnectorSnowflakeParams` :

```python
class ReaderConnectorBigQueryParams(BaseModel):
    """Lecture d'une requête SQL libre (SELECT uniquement) sur Google BigQuery, via un secret
    de connexion dédié (bigquery_dsn)."""

    secretName: str
    query: str
```

- [ ] **Step 5: Add `materialize_bigquery_connector`**

Dans `core/app/pipelines/connector_runtime.py`, après `materialize_snowflake_connector`, copie du patron
exact avec `payload.kind != "bigquery_dsn"` :

```python
def materialize_bigquery_connector(
    conn,
    *,
    secret_resolver: SecretResolver | None,
    node_id: str,
    params: ReaderConnectorBigQueryParams,
    view_name: str,
) -> None:
    try:
        validate_select_only(parse_ast(conn, params.query))
    except SqlSandboxError as exc:
        raise ConnectorRuntimeError(f"reader.connector.bigquery query rejected: {exc}") from exc

    payload = _resolve_secret(secret_resolver, params.secretName)
    if payload.kind != "bigquery_dsn":
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable by reader.connector.bigquery "
            "(expected bigquery_dsn)"
        )

    @dlt.resource(name="records", write_disposition="replace")
    def _records():
        engine = sa.create_engine(payload.dsn)
        try:
            with engine.connect() as db_conn:
                rows = db_conn.execution_options(yield_per=1000).exec_driver_sql(params.query)
                yield from (dict(row._mapping) for row in rows)
        finally:
            engine.dispose()

    _run_dlt_and_attach(conn, _records, node_id=node_id, view_name=view_name)
```

Ajouter les imports nécessaires (`ReaderConnectorBigQueryParams` depuis `app.pipelines.ops.schemas`).

- [ ] **Step 6: Add the dependency**

Dans `core/pyproject.toml`, ajouter `sqlalchemy-bigquery` à `dependencies`. Run : `cd core && uv sync`.

- [ ] **Step 7: Register the op**

Dans `core/app/pipelines/ops/contracts.py`, ajouter l'import `ReaderConnectorBigQueryParams` et l'entrée
(à côté de `reader.connector.snowflake`) :

```python
    "reader.connector.bigquery": OperationContract(
        op="reader.connector.bigquery",
        kind="reader",
        params_schema=ReaderConnectorBigQueryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) + Apache-2.0 (dlt) + MIT (sqlalchemy-bigquery)",
    ),
```

(Pas de `compile=` — `reader.connector.*` est matérialisé par `runtime.py`, pas par `compiler.py`, vérifier
contre `reader.connector.postgres` déjà existant si un autre champ y est réellement câblé avant de le
copier.)

- [ ] **Step 8: Wire into `runtime.py`**

Vérifier comment `runtime.py` dispatche aujourd'hui vers `materialize_postgres_connector`/
`materialize_snowflake_connector` pour un nœud `reader.connector.postgres`/`snowflake` (grep `materialize_`
dans `runtime.py`) et ajouter la branche symétrique pour `reader.connector.bigquery` selon le même patron
exact.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k bigquery -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add core/app/secrets/schemas.py core/app/pipelines/ops/schemas.py \
  core/app/pipelines/connector_runtime.py core/app/pipelines/ops/contracts.py \
  core/app/pipelines/runtime.py core/pyproject.toml core/uv.lock \
  core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(pipelines): ajoute reader.connector.bigquery"
```

---

### Task 13: `reader.connector.mssql`

Même patron que la Task 12. Driver à vérifier au Step 1 : `pymssql` (pur Python, pas de dépendance ODBC
système) préféré à `pyodbc` (nécessite `unixodbc` + un driver ODBC système) sauf si le README de
`sqlalchemy`/`pymssql` indique une limitation bloquante — trancher au Step 1, pas supposé ici.

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Produces: `MssqlDsnPayload` ; `ReaderConnectorMssqlParams` ; `materialize_mssql_connector` ; entrée
  `"reader.connector.mssql"`.

- [ ] **Step 1: Vérifier le driver SQLAlchemy pour MSSQL**

Confirmer contre la doc réelle de SQLAlchemy (`docs.sqlalchemy.org/en/20/dialects/mssql.html`) le schéma de
DSN pour `pymssql` (`mssql+pymssql://user:pass@host:port/dbname`) et toute limitation connue (types de
données, requêtes non supportées) à documenter dans la docstring, même patron que la réserve déjà écrite pour
`ReaderConnectorSnowflakeParams` (SAMPLE/TOP/MINUS rejetés).

- [ ] **Step 2: Write the failing tests**

Même structure que Task 12 Step 2, adaptée à `MssqlDsnPayload`/`ReaderConnectorMssqlParams`/
`materialize_mssql_connector` (secret kind attendu : `mssql_dsn`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k mssql -v`
Expected: FAIL

- [ ] **Step 4: Add `MssqlDsnPayload`, `ReaderConnectorMssqlParams`, `materialize_mssql_connector`**

Même patron exact que Task 12 Steps 3-5, avec `kind: Literal["mssql_dsn"] = "mssql_dsn"` et le message
d'erreur `"expected mssql_dsn"`.

- [ ] **Step 5: Add the dependency**

Dans `core/pyproject.toml`, ajouter `pymssql` (ou `pyodbc`, selon Step 1). Run : `cd core && uv sync`.

- [ ] **Step 6: Register the op + wire into `runtime.py`**

Même patron que Task 12 Steps 7-8, avec `engine_license="MIT (DuckDB) + Apache-2.0 (dlt) + LGPL-2.1 (pymssql)"`
(licence pymssql à reconfirmer contre son PyPI réel avant de la figer — pas supposée ici).

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k mssql -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/secrets/schemas.py core/app/pipelines/ops/schemas.py \
  core/app/pipelines/connector_runtime.py core/app/pipelines/ops/contracts.py \
  core/app/pipelines/runtime.py core/pyproject.toml core/uv.lock \
  core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(pipelines): ajoute reader.connector.mssql"
```

---

### Task 14: `reader.connector.oracle`

Même patron. Driver déjà identifié en design (§6.1, matrice ligne « Oracle Spatial Relational ») :
`python-oracledb` en **mode thin** (pur Python, évite l'Instant Client propriétaire).

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Produces: `OracleDsnPayload` ; `ReaderConnectorOracleParams` ; `materialize_oracle_connector` ; entrée
  `"reader.connector.oracle"`.

- [ ] **Step 1: Vérifier que `python-oracledb` s'enregistre en mode thin sans configuration explicite**

Confirmer contre la doc réelle (`python-oracledb.readthedocs.io`) que `sa.create_engine("oracle+oracledb://...")`
utilise le mode thin par défaut (pas d'appel `oracledb.init_oracle_client()` requis) — sinon documenter
l'appel d'initialisation nécessaire dans `materialize_oracle_connector`.

- [ ] **Step 2: Write the failing tests**

Même structure que Task 12 Step 2, adaptée à `OracleDsnPayload`/`ReaderConnectorOracleParams`/
`materialize_oracle_connector` (secret kind attendu : `oracle_dsn`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k oracle -v`
Expected: FAIL

- [ ] **Step 4: Add `OracleDsnPayload`, `ReaderConnectorOracleParams`, `materialize_oracle_connector`**

Même patron exact que Task 12 Steps 3-5, avec `kind: Literal["oracle_dsn"] = "oracle_dsn"`.

- [ ] **Step 5: Add the dependency**

Dans `core/pyproject.toml`, ajouter `python-oracledb`. Run : `cd core && uv sync`.

- [ ] **Step 6: Register the op + wire into `runtime.py`**

Même patron que Task 12 Steps 7-8, avec `engine_license="MIT (DuckDB) + Apache-2.0 (dlt) + Apache-2.0
(python-oracledb)"`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k oracle -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/secrets/schemas.py core/app/pipelines/ops/schemas.py \
  core/app/pipelines/connector_runtime.py core/app/pipelines/ops/contracts.py \
  core/app/pipelines/runtime.py core/pyproject.toml core/uv.lock \
  core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(pipelines): ajoute reader.connector.oracle"
```

---

### Task 15: `reader.connector.blob` (S3, Azure Blob, GCS)

Diffère des 3 précédentes : source `filesystem` de dlt (fsspec), pas `sql_database`. Résout la question
« d'où vient le fichier » laissée ouverte par Vague 1 (design §6.2) : toujours un secret de connexion
pré-configuré vers un bucket, jamais un upload ni une URL arbitraire.

**Files:**
- Modify: `core/app/secrets/schemas.py`
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/connector_runtime.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/pyproject.toml`
- Test: `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Produces: `S3CredentialsPayload`, `AzureBlobCredentialsPayload`, `GcsCredentialsPayload`
  (`app/secrets/schemas.py`) ; `ReaderConnectorBlobParams` (`app/pipelines/ops/schemas.py`) ;
  `materialize_blob_connector(conn, *, secret_resolver, node_id, params, view_name) -> None`
  (`connector_runtime.py`) ; entrée `"reader.connector.blob"`.

- [ ] **Step 1: Vérifier la source `filesystem` de dlt et les champs de credentials fsspec**

Confirmer contre `dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem` : comment configurer la source
`filesystem` avec `bucket_url` + credentials par provider, et comment lui indiquer le format de fichier
(`file_format="csv"|"json"|"parquet"` ou détection automatique par extension). Confirmer aussi les champs de
credentials attendus par `s3fs`/`adlfs`/`gcsfs` (ex. S3 : `aws_access_key_id`/`aws_secret_access_key`/
`endpoint_url` ; Azure Blob : `account_name`/`account_key` ; GCS : `service_account_info` JSON) contre leur
documentation respective — ne pas deviner les noms de champs.

- [ ] **Step 2: Write the failing tests**

```python
def test_materialize_blob_connector_rejects_wrong_secret_kind(conn):
    class _FakeResolver:
        def get(self, name):
            from app.secrets.schemas import PostgresDsnPayload

            return PostgresDsnPayload(dsn="postgresql://x")

    with pytest.raises(ConnectorRuntimeError, match="s3_credentials"):
        materialize_blob_connector(
            conn,
            secret_resolver=_FakeResolver(),
            node_id="n1",
            params=ReaderConnectorBlobParams(
                secretName="s1", path="s3://bucket/data.csv", format="csv"
            ),
            view_name="out",
        )
```

(Compléter avec un test d'intégration par format une fois les credentials/champs confirmés au Step 1 — par
exemple contre un serveur S3 compatible local si l'environnement de test en fournit un, sinon documenter
explicitement dans le rapport de tâche que seul le test de forme/rejet a pu être écrit sans infrastructure
S3 réelle disponible en CI.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k blob -v`
Expected: FAIL

- [ ] **Step 4: Add the 3 credential payload classes**

Dans `core/app/secrets/schemas.py`, formes confirmées au Step 1 :

```python
class S3CredentialsPayload(BaseModel):
    """Identifiants d'accès à un bucket S3 (ou compatible S3), utilisés par la source
    filesystem de dlt (s3fs) pour reader.connector.blob."""

    kind: Literal["s3_credentials"] = "s3_credentials"
    awsAccessKeyId: str
    awsSecretAccessKey: str
    endpointUrl: str | None = None


class AzureBlobCredentialsPayload(BaseModel):
    """Identifiants d'accès à un compte Azure Blob Storage (adlfs) pour
    reader.connector.blob."""

    kind: Literal["azure_blob_credentials"] = "azure_blob_credentials"
    accountName: str
    accountKey: str


class GcsCredentialsPayload(BaseModel):
    """Compte de service Google Cloud Storage (gcsfs, JSON de service account) pour
    reader.connector.blob."""

    kind: Literal["gcs_credentials"] = "gcs_credentials"
    serviceAccountInfo: dict
```

Ajouter les 3 classes à l'union `SecretPayload`. **Ajuster les noms de champs si le Step 1 a trouvé une forme
différente** — cette forme est un point de départ, pas une vérité acquise.

- [ ] **Step 5: Add `ReaderConnectorBlobParams`**

Dans `core/app/pipelines/ops/schemas.py` :

```python
class ReaderConnectorBlobParams(BaseModel):
    """Lecture d'un fichier tabulaire (CSV/JSON/Parquet) depuis un objet de stockage cloud
    (S3, Azure Blob, GCS), résolu par un secret de connexion pré-configuré au bucket — jamais
    un upload ni une URL arbitraire. Le fournisseur est résolu depuis le préfixe de `path`
    (s3://, az://, gs://)."""

    secretName: str
    path: str
    format: Literal["csv", "json", "parquet"]
```

- [ ] **Step 6: Add `materialize_blob_connector`**

Dans `core/app/pipelines/connector_runtime.py`, utilisant la source `filesystem` de dlt confirmée au Step 1 —
squelette à ajuster selon la forme réelle de l'API dlt :

```python
def materialize_blob_connector(
    conn,
    *,
    secret_resolver: SecretResolver | None,
    node_id: str,
    params: ReaderConnectorBlobParams,
    view_name: str,
) -> None:
    payload = _resolve_secret(secret_resolver, params.secretName)
    expected_kind = {
        "s3://": "s3_credentials",
        "az://": "azure_blob_credentials",
        "gs://": "gcs_credentials",
    }
    prefix = next((p for p in expected_kind if params.path.startswith(p)), None)
    if prefix is None:
        raise ConnectorRuntimeError(
            f"reader.connector.blob: unsupported path scheme in '{params.path}' "
            "(expected s3://, az:// or gs://)"
        )
    if payload.kind != expected_kind[prefix]:
        raise ConnectorRuntimeError(
            f"secret has kind '{payload.kind}', not usable for this path scheme "
            f"(expected {expected_kind[prefix]})"
        )

    from dlt.sources.filesystem import filesystem, read_csv, read_json, read_parquet

    readers = {"csv": read_csv, "json": read_json, "parquet": read_parquet}
    credentials = payload.model_dump(exclude={"kind"})
    resource = (
        filesystem(bucket_url=params.path, credentials=credentials)
        | readers[params.format]()
    )
    resource.apply_hints(name="records", write_disposition="replace")
    _run_dlt_and_attach(conn, resource, node_id=node_id, view_name=view_name)
```

(La forme exacte de `filesystem(...)`/`read_csv`/`credentials=` **doit être confirmée au Step 1** contre la
doc réelle de dlt — ce squelette est un point de départ, ajuster avant de lancer le test.)

- [ ] **Step 7: Add the dependencies**

Dans `core/pyproject.toml`, ajouter les extras dlt nécessaires (`dlt[filesystem]` ou équivalent selon la
forme confirmée au Step 1) + `s3fs`/`adlfs`/`gcsfs`. Run : `cd core && uv sync`.

- [ ] **Step 8: Register the op + wire into `runtime.py`**

Même patron que Task 12 Steps 7-8, `engine_license="MIT (DuckDB) + Apache-2.0 (dlt, source filesystem via
fsspec/s3fs/adlfs/gcsfs)"`.

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k blob -v`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add core/app/secrets/schemas.py core/app/pipelines/ops/schemas.py \
  core/app/pipelines/connector_runtime.py core/app/pipelines/ops/contracts.py \
  core/app/pipelines/runtime.py core/pyproject.toml core/uv.lock \
  core/tests/test_pipeline_connector_runtime.py
git commit -m "feat(pipelines): ajoute reader.connector.blob (S3/Azure Blob/GCS)"
```

---

### Task 16: Formulaire shell de création de secret

Le design (§6, piège CLAUDE.md n°12) signale explicitement que ce point n'a pas été vérifié : ne pas
présumer qu'aucun changement shell n'est nécessaire ici comme pour le reste du plan.

**Files:**
- Read: composant shell de gestion des secrets (chercher `SecretsAdminPage`/équivalent sous `shell/src/`)
- Modify: ce composant, si besoin

**Interfaces:**
- Consumes: `GET /v1/secrets`/`POST /v1/secrets` (déjà existants), types générés depuis l'OpenAPI régénéré à
  la Task 17 Step 3 ci-dessous (donc cette tâche s'exécute après la Task 17, pas avant).

- [ ] **Step 1: Localiser le composant**

Run: `cd shell && grep -rln "postgres_dsn\|snowflake_dsn\|SecretPayload" src/`

- [ ] **Step 2: Déterminer si le formulaire liste les `kind` en dur ou les dérive du schéma généré**

Lire le fichier trouvé. S'il énumère les `kind` littéralement (ex. un `<select>` avec des `<option>`
codées en dur), ajouter les 6 nouveaux kinds (`bigquery_dsn`, `mssql_dsn`, `oracle_dsn`, `s3_credentials`,
`azure_blob_credentials`, `gcs_credentials`) suivant le même patron que les kinds existants. S'il dérive
déjà dynamiquement la liste depuis le schéma OpenAPI généré (comme `PipelinePalette.tsx` le fait pour le
catalogue d'op), aucun changement n'est nécessaire — documenter cette conclusion dans le message de commit
plutôt que de le supposer sans l'avoir lu.

- [ ] **Step 3: Si modifié, écrire un test shell**

Suivre le patron de test existant du même fichier (Vitest + Testing Library) pour vérifier qu'un des 6
nouveaux kinds est sélectionnable dans le formulaire.

- [ ] **Step 4: Run shell tests**

Run: `cd shell && npm run test -- <fichier concerné>`
Expected: PASS

- [ ] **Step 5: Commit (si modifié)**

```bash
git add shell/src/<fichier> shell/src/<fichier de test>
git commit -m "feat(shell): ajoute les nouveaux kinds de secret des connecteurs lecteurs Vague 2"
```

---

### Task 17: Filet de non-régression + clôture

**Files:**
- Modify: `core/tests/test_pipeline_routes.py`
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ou équivalent, selon ce que la Task 20 du plan
  « transform-ops » y a laissé)
- Modify: `docs/revue/matrice-couverture-fme.jsonl`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Mettre à jour le test de comptage d'op**

Ajouter `"reader.connector.bigquery"`, `"reader.connector.mssql"`, `"reader.connector.oracle"`,
`"reader.connector.blob"` à l'ensemble attendu dans `test_pipeline_routes.py` (`set(body) == {...}`), et
mettre à jour le test dédié `len(OPERATIONS)` à **49**.

- [ ] **Step 2: Run the full pipelines test suite**

Run: `cd core && uv run pytest tests/ -k pipeline -v`
Expected: PASS

- [ ] **Step 3: Run the full core test suite + quality gates**

```bash
cd core
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
```
Expected: tout vert.

- [ ] **Step 4: Régénérer OpenAPI + types TS**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: diff non vide (4 nouveaux schémas de params + 6 nouveaux kinds de secret).

- [ ] **Step 5: Mettre à jour la matrice de couverture FME**

Dans `docs/revue/matrice-couverture-fme.jsonl`, pour les 9 lignes suivantes, `planned_duckdb` →
`implemented` : « Google BigQuery »→`reader.connector.bigquery`, « Microsoft SQL Server Spatial (JDBC) »→
`reader.connector.mssql`, « Oracle Spatial Relational »→`reader.connector.oracle`, « Apache Parquet »/
« CSV (Comma-Separated Value) »/« JSON (JavaScript Object Notation) »→`reader.connector.blob`,
`S3Connector`/`AzureBlobStorageConnector`/`GoogleCloudStorageConnector`→`reader.connector.blob`. Puis :

```bash
python3 core/scripts/fme_coverage_cli.py --write
python3 core/scripts/fme_coverage_cli.py --check
```

- [ ] **Step 6: Régénérer le bilan de fonctionnalités**

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
```

- [ ] **Step 7: Mettre à jour `CLAUDE.md`**

Ajouter une ligne dans `### Livré` : « **Vague 2 lecteurs DuckDB (SQL + objet/stockage)** — 4 nouvelles op
(reader.connector.bigquery/mssql/oracle/blob), catalogue à 49 op ; `reader.connector.blob` résout la
question « d'où vient le fichier » (Vague 1) par un secret de connexion pré-configuré au bucket, jamais un
upload ni une URL arbitraire. »

- [ ] **Step 8: Commit**

```bash
git add core/tests/ docs/revue/matrice-couverture-fme.jsonl docs/revue/bilan-fonctionnalites.* \
  core/openapi.json shell/src/api/generated/core-schema.d.ts CLAUDE.md
git commit -m "test(pipelines): filet de non-régression + clôture Vague 2 lecteurs (49 op)"
```

---

### Task 18: `transform.centroid` + `transform.convexHull`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Consumes: fixture `conn_spatial` (`tests/test_pipeline_compiler.py`, déjà existante).
- Produces: `TransformCentroidParams`, `TransformConvexHullParams` ; `_compile_centroid`,
  `_compile_convex_hull` ; entrées `"transform.centroid"`/`"transform.convexHull"`.

- [ ] **Step 1: Write the failing tests**

```python
def test_compile_centroid(conn_spatial):
    conn_spatial.execute(
        "CREATE TABLE poly (id INTEGER, geometry GEOMETRY)"
    )
    conn_spatial.execute(
        "INSERT INTO poly VALUES (1, ST_GeomFromText('POLYGON ((0 0, 4 0, 4 4, 0 4, 0 0))'))"
    )
    sql = compile_transform_sql("transform.centroid", {}, input_view="poly")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_AsText(geometry) FROM out").fetchone()
    assert row == ("POINT (2 2)",)


def test_compile_convex_hull(conn_spatial):
    conn_spatial.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO pts VALUES "
        "(1, ST_GeomFromText('MULTIPOINT (0 0, 4 0, 4 4, 0 4, 2 2)'))"
    )
    sql = compile_transform_sql("transform.convexHull", {}, input_view="pts")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_NPoints(geometry) FROM out").fetchone()
    assert row == (5,)  # 4 coins du carré + retour au premier point (anneau fermé)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "centroid or convex_hull" -v`
Expected: FAIL — `ValueError: 'transform.centroid' is not a transform op`

- [ ] **Step 3: Add the Pydantic param classes**

```python
class TransformCentroidParams(BaseModel):
    """Remplace la géométrie par son centre de gravité (barycentre)."""


class TransformConvexHullParams(BaseModel):
    """Remplace la géométrie par son enveloppe convexe."""
```

- [ ] **Step 4: Add the compiler functions**

Imports à ajouter dans `compiler.py` : `TransformCentroidParams`, `TransformConvexHullParams`.

```python
def _compile_centroid(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformCentroidParams.model_validate(params)  # forme seulement, aucun champ
    return (
        f"SELECT * EXCLUDE (geometry), ST_Centroid(geometry) AS geometry "
        f"FROM {_qi(input_view)}"
    )


def _compile_convex_hull(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformConvexHullParams.model_validate(params)  # forme seulement, aucun champ
    return (
        f"SELECT * EXCLUDE (geometry), ST_ConvexHull(geometry) AS geometry "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 5: Register the two new ops**

Imports à ajouter dans `contracts.py` : `TransformCentroidParams`, `TransformConvexHullParams`.

```python
    "transform.centroid": OperationContract(
        op="transform.centroid",
        kind="transform",
        params_schema=TransformCentroidParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_centroid,
    ),
    "transform.convexHull": OperationContract(
        op="transform.convexHull",
        kind="transform",
        params_schema=TransformConvexHullParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_convex_hull,
    ),
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k "centroid or convex_hull" -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.centroid et transform.convexHull (retrait QGIS 1/9)"
```

---

### Task 19: `transform.simplify`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Produces: `TransformSimplifyParams` ; `_compile_simplify` ; entrée `"transform.simplify"`.

- [ ] **Step 1: Vérifier `ST_SimplifyPreserveTopology` contre un DuckDB réel**

```bash
cd core && uv run python3 -c "
import duckdb
c = duckdb.connect(':memory:')
c.execute('INSTALL spatial; LOAD spatial;')
print(c.execute(\"SELECT function_name, parameters FROM duckdb_functions() WHERE function_name IN ('st_simplify','st_simplifypreservetopology')\").fetchall())
"
```

- [ ] **Step 2: Write the failing tests**

```python
def test_compile_simplify_reduces_vertex_count(conn_spatial):
    conn_spatial.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO line VALUES "
        "(1, ST_GeomFromText('LINESTRING (0 0, 1 0.01, 2 0, 3 0.01, 4 0)'))"
    )
    sql = compile_transform_sql(
        "transform.simplify", {"tolerance": 0.1}, input_view="line"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_NPoints(geometry) FROM out").fetchone()
    assert row[0] < 5


def test_compile_simplify_preserve_topology_true_by_default(conn_spatial):
    sql = compile_transform_sql("transform.simplify", {"tolerance": 0.1}, input_view="base")
    assert "ST_SimplifyPreserveTopology" in sql
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k simplify -v`
Expected: FAIL — `ValueError: 'transform.simplify' is not a transform op`

- [ ] **Step 4: Add the Pydantic param class**

```python
class TransformSimplifyParams(BaseModel):
    """Réduit le nombre de sommets de la géométrie selon une tolérance spatiale.
    preserveTopology=True (défaut) évite l'auto-intersection de polygones simplifiés."""

    tolerance: float
    preserveTopology: bool = True
```

- [ ] **Step 5: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformSimplifyParams`.

```python
def _compile_simplify(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformSimplifyParams.model_validate(params)
    fn = "ST_SimplifyPreserveTopology" if p.preserveTopology else "ST_Simplify"
    return (
        f"SELECT * EXCLUDE (geometry), {fn}(geometry, {p.tolerance}) AS geometry "
        f"FROM {_qi(input_view)}"
    )
```

- [ ] **Step 6: Register the op**

Import à ajouter dans `contracts.py` : `TransformSimplifyParams`.

```python
    "transform.simplify": OperationContract(
        op="transform.simplify",
        kind="transform",
        params_schema=TransformSimplifyParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_simplify,
    ),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k simplify -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.simplify (retrait QGIS 2/9)"
```

---

### Task 20: `transform.boundingGeometry`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Produces: `TransformBoundingGeometryParams` ; `_compile_bounding_geometry` ; entrée
  `"transform.boundingGeometry"`.

- [ ] **Step 1: Vérifier `ST_MinimumRotatedRectangle` contre un DuckDB réel**

```bash
cd core && uv run python3 -c "
import duckdb
c = duckdb.connect(':memory:')
c.execute('INSTALL spatial; LOAD spatial;')
c.execute(\"CREATE TABLE t AS SELECT ST_GeomFromText('MULTIPOINT (0 0, 4 0, 4 4, 0 4)') AS g\")
print(c.execute('SELECT ST_AsText(ST_Envelope(g)), ST_AsText(ST_MinimumRotatedRectangle(g)) FROM t').fetchall())
"
```

- [ ] **Step 2: Write the failing tests**

```python
def test_compile_bounding_geometry_envelope(conn_spatial):
    conn_spatial.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO pts VALUES (1, ST_GeomFromText('MULTIPOINT (0 0, 4 0, 4 4, 0 4)'))"
    )
    sql = compile_transform_sql(
        "transform.boundingGeometry", {"mode": "envelope"}, input_view="pts"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute("SELECT ST_Area(geometry) FROM out").fetchone()
    assert row == (16.0,)


def test_compile_bounding_geometry_oriented_rectangle(conn_spatial):
    sql = compile_transform_sql(
        "transform.boundingGeometry", {"mode": "orientedRectangle"}, input_view="base"
    )
    assert "ST_MinimumRotatedRectangle" in sql
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k bounding_geometry -v`
Expected: FAIL — `ValueError: 'transform.boundingGeometry' is not a transform op`

- [ ] **Step 4: Add the Pydantic param class**

```python
class TransformBoundingGeometryParams(BaseModel):
    """Remplace la géométrie par sa boîte englobante : rectangle aligné aux axes
    ("envelope") ou rectangle orienté minimal ("orientedRectangle")."""

    mode: Literal["envelope", "orientedRectangle"] = "envelope"
```

- [ ] **Step 5: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformBoundingGeometryParams`.

```python
def _compile_bounding_geometry(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformBoundingGeometryParams.model_validate(params)
    fn = "ST_Envelope" if p.mode == "envelope" else "ST_MinimumRotatedRectangle"
    return (
        f"SELECT * EXCLUDE (geometry), {fn}(geometry) AS geometry FROM {_qi(input_view)}"
    )
```

- [ ] **Step 6: Register the op**

Import à ajouter dans `contracts.py` : `TransformBoundingGeometryParams`.

```python
    "transform.boundingGeometry": OperationContract(
        op="transform.boundingGeometry",
        kind="transform",
        params_schema=TransformBoundingGeometryParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_bounding_geometry,
    ),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k bounding_geometry -v`
Expected: PASS (2 tests)

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.boundingGeometry (retrait QGIS 3/9)"
```

---

### Task 21: `transform.snapToLayer`

Op binaire (entrée secondaire) — même patron que `transform.join`/`transform.intersection`.

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Produces: `TransformSnapToLayerParams` ; `_compile_snap_to_layer` ; entrée `"transform.snapToLayer"`
  (`accepts_secondary_input=True`).

- [ ] **Step 1: Vérifier `ST_Snap` contre un DuckDB réel**

```bash
cd core && uv run python3 -c "
import duckdb
c = duckdb.connect(':memory:')
c.execute('INSTALL spatial; LOAD spatial;')
print(c.execute(\"SELECT function_name, parameters FROM duckdb_functions() WHERE function_name = 'st_snap'\").fetchall())
"
```

Si `ST_Snap` accepte une géométrie de référence unique (pas une agrégation), documenter dans la docstring
que l'entrée secondaire doit être réduite à une seule géométrie de référence en amont (ex. via
`transform.aggregate` + `ST_Union_Agg`) — sinon la requête ci-dessous échouera à l'exécution avec plusieurs
lignes côté `join_view`, comportement à confirmer par le test du Step 2 plutôt que supposé.

- [ ] **Step 2: Write the failing test**

```python
def test_compile_snap_to_layer(conn_spatial):
    conn_spatial.execute("CREATE TABLE ref (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO ref VALUES (1, ST_GeomFromText('POINT (3.0005 45.0005)'))"
    )
    sql = compile_transform_sql(
        "transform.snapToLayer",
        {"tolerance": 0.01},
        input_view="base",
        join_view="ref",
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    row = conn_spatial.execute(
        "SELECT ST_AsText(geometry) FROM out WHERE id = 1"
    ).fetchone()
    assert row == ("POINT (3.0005 45.0005)",)
```

(Si le Step 1 révèle que `ST_Snap` exige une géométrie de référence agrégée, adapter ce test — `ref` doit
alors contenir une seule ligne, ce qui est déjà le cas ici, mais documenter cette contrainte plutôt que la
découvrir silencieusement en prod.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k snap_to_layer -v`
Expected: FAIL — `ValueError: 'transform.snapToLayer' is not a transform op`

- [ ] **Step 4: Add the Pydantic param class**

```python
class TransformSnapToLayerParams(BaseModel):
    """Ajuste (« snap ») la géométrie sur la géométrie de référence de l'entrée secondaire
    dans une tolérance donnée."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    tolerance: float
```

- [ ] **Step 5: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformSnapToLayerParams`.

```python
def _compile_snap_to_layer(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    p = TransformSnapToLayerParams.model_validate(params)
    assert join_view is not None, "transform.snapToLayer requires join_view"
    return (
        f"SELECT t.* EXCLUDE (geometry), "
        f"ST_Snap(t.geometry, o.geometry, {p.tolerance}) AS geometry "
        f"FROM {_qi(input_view)} t, {_qi(join_view)} o"
    )
```

- [ ] **Step 6: Register the op**

Import à ajouter dans `contracts.py` : `TransformSnapToLayerParams`.

```python
    "transform.snapToLayer": OperationContract(
        op="transform.snapToLayer",
        kind="transform",
        params_schema=TransformSnapToLayerParams,
        accepts_secondary_input=True,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_snap_to_layer,
    ),
```

- [ ] **Step 7: Wire into `runtime.py`**

Ajouter `"transform.snapToLayer": TransformSnapToLayerParams` à `_JOIN_PARAM_MODELS`
(`core/app/pipelines/runtime.py:80`), avec l'import correspondant.

- [ ] **Step 8: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k snap_to_layer -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/app/pipelines/runtime.py \
  core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.snapToLayer (retrait QGIS 4/9)"
```

---

### Task 22: `transform.resolveOverlaps`

Requête à 3 étapes vérifiée empiriquement pendant le brainstorming (design §7.1.1).

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/compiler.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_compiler.py`

**Interfaces:**
- Produces: `TransformResolveOverlapsParams` ; `_compile_resolve_overlaps` ; entrée
  `"transform.resolveOverlaps"`.

- [ ] **Step 1: Write the failing test**

```python
def test_compile_resolve_overlaps_splits_into_disjoint_and_shared_parts(conn_spatial):
    conn_spatial.execute("CREATE TABLE overlapping (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO overlapping VALUES "
        "(1, ST_GeomFromText('POLYGON ((0 0, 2 0, 2 2, 0 2, 0 0))')), "
        "(2, ST_GeomFromText('POLYGON ((1 1, 3 1, 3 3, 1 3, 1 1))'))"
    )
    sql = compile_transform_sql("transform.resolveOverlaps", {}, input_view="overlapping")
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    count = conn_spatial.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count == 3  # 2 parties disjointes + 1 partie commune
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k resolve_overlaps -v`
Expected: FAIL — `ValueError: 'transform.resolveOverlaps' is not a transform op`

- [ ] **Step 3: Add the Pydantic param class**

```python
class TransformResolveOverlapsParams(BaseModel):
    """Décompose un ensemble de géométries qui se chevauchent en features géométriques
    disjointes (parties non chevauchantes + parties communes). Géométrie uniquement —
    n'associe pas les attributs des features d'origine à chaque morceau de sortie."""
```

- [ ] **Step 4: Add the compiler function**

Import à ajouter dans `compiler.py` : `TransformResolveOverlapsParams`.

```python
def _compile_resolve_overlaps(
    params: dict,
    *,
    input_view: str,
    join_view: str | None = None,
    input_srid: int | None = None,
) -> str:
    TransformResolveOverlapsParams.model_validate(params)  # forme seulement, aucun champ
    return (
        f"WITH agg AS (SELECT list(geometry) AS geoms FROM {_qi(input_view)}), "
        f"noded AS (SELECT ST_Node(ST_Collect(geoms)) AS n FROM agg), "
        f"edges AS (SELECT UNNEST(ST_Dump(n)).geom AS g FROM noded), "
        f"edge_list AS (SELECT list(g) AS glist FROM edges) "
        f"SELECT UNNEST(ST_Dump(ST_Polygonize(glist))).geom AS geometry FROM edge_list"
    )
```

- [ ] **Step 5: Register the op**

Import à ajouter dans `contracts.py` : `TransformResolveOverlapsParams`.

```python
    "transform.resolveOverlaps": OperationContract(
        op="transform.resolveOverlaps",
        kind="transform",
        params_schema=TransformResolveOverlapsParams,
        engine="duckdb",
        engine_license="MIT (DuckDB)",
        compile=_compiler._compile_resolve_overlaps,
    ),
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k resolve_overlaps -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/compiler.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_compiler.py
git commit -m "feat(pipelines): ajoute transform.resolveOverlaps (retrait QGIS 5/9)"
```

---

### Task 23: Mécanisme `execute` générique (nouveau fichier `ops/execute.py`)

Construit l'infrastructure Python-en-process, testée directement sans passer par `runtime.py` — la
Task 24 la branchera dans `_execute_transform_chain`. Le patron WKB↔Shapely ci-dessous est vérifié
empiriquement (round-trip confirmé pendant le brainstorming).

**Files:**
- Create: `core/app/pipelines/ops/execute.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_ops_execute.py` (nouveau fichier)

**Interfaces:**
- Consumes: `duckdb.DuckDBPyConnection` (déjà utilisé partout dans ce module), `shapely` (déjà une
  dépendance de `core/pyproject.toml`).
- Produces: nouveau champ `execute: Callable[..., None] | None = None` sur `OperationContract`
  (`app/pipelines/ops/contracts.py`) ; `_qi` dupliqué localement dans `execute.py` (même patron que
  `compiler.py`/`runtime.py`, jamais d'import inter-module d'un nom `_`-préfixé, cf. commentaire déjà
  présent dans `runtime.py`).

- [ ] **Step 1: Write the failing test for the round-trip helper**

Créer `core/tests/test_pipeline_ops_execute.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.pipelines.ops.execute import _read_geometry_rows, _write_geometry_rows


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE base (id INTEGER, geometry GEOMETRY)")
    c.execute(
        "INSERT INTO base VALUES (1, ST_Point(3.0, 45.0)), (2, ST_Point(3.001, 45.0))"
    )
    return c


def test_read_write_geometry_rows_round_trips(conn):
    df = _read_geometry_rows(conn, "base")
    assert list(df.columns) == ["id", "geometry"]
    import shapely.wkb

    geom = shapely.wkb.loads(bytes(df["geometry"][0]))
    assert geom.wkt == "POINT (3 45)"

    _write_geometry_rows(conn, df, view_name="roundtrip")
    row = conn.execute("SELECT id, ST_AsText(geometry) FROM roundtrip WHERE id = 1").fetchone()
    assert row == (1, "POINT (3 45)")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.ops.execute'`

- [ ] **Step 3: Create `core/app/pipelines/ops/execute.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Op de pipeline dont le résultat est calculé en Python (Shapely), pas en SQL — mécanisme
générique introduit pour retirer le sidecar QGIS (design docs/superpowers/specs/
2026-09-20-vague2-transformers-duckdb-design.md §7.2). Chaque fonction `_execute_xxx` a la
signature `(conn, *, input_view, view_name, params) -> None` : elle lit `input_view`, calcule
en process, matérialise `view_name` — même contrat de sortie qu'un nœud `compile` (une TEMP
TABLE/VIEW nommée `view_name`, lisible par le nœud suivant), `runtime.py` ne voit aucune
différence."""

import pandas as pd
import shapely.wkb


def _qi(name: str) -> str:
    # Duplication délibérée (patron déjà établi par compiler.py/runtime.py) — helper de 2
    # lignes, pas un import inter-module d'un nom `_`-préfixé.
    return '"' + name.replace('"', '""') + '"'


def _read_geometry_rows(conn, input_view: str) -> pd.DataFrame:
    """Lit toutes les colonnes de `input_view`, la géométrie sérialisée en WKB (bytearray,
    consommable par shapely.wkb.loads)."""
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    select_list = ", ".join(
        f"ST_AsWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    return conn.execute(f"SELECT {select_list} FROM {_qi(input_view)}").fetchdf()


def _write_geometry_rows(conn, df: pd.DataFrame, *, view_name: str) -> None:
    """Matérialise `df` (colonne `geometry` en WKB shapely.wkb.dumps) en TEMP TABLE
    `view_name`."""
    conn.register("_execute_tmp_df", df)
    cols = list(df.columns)
    select_list = ", ".join(
        f"ST_GeomFromWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    conn.execute(
        f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {select_list} FROM _execute_tmp_df"
    )
    conn.unregister("_execute_tmp_df")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -v`
Expected: PASS

- [ ] **Step 5: Add the `execute` field to `OperationContract`**

Dans `core/app/pipelines/ops/contracts.py`, ajouter le champ juste après `needs_columns` :

```python
    # Design docs/superpowers/specs/2026-09-20-vague2-transformers-duckdb-design.md §7.2 :
    # mutuellement exclusif avec `compile` — un op "transform" a l'un ou l'autre, jamais les
    # deux, jamais aucun des deux. Signature : (conn, *, input_view, view_name, params) -> None,
    # matérialise `view_name` lui-même (contrairement à `compile`, qui retourne une simple
    # chaîne SQL exécutée par l'appelant).
    execute: Callable[..., None] | None = None
```

- [ ] **Step 6: Run the full pipelines test suite**

Run: `cd core && uv run pytest tests/ -k pipeline -v`
Expected: PASS, aucune régression (`execute` reste `None` sur toutes les entrées `OPERATIONS` existantes).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/ops/execute.py core/app/pipelines/ops/contracts.py \
  core/tests/test_pipeline_ops_execute.py
git commit -m "feat(pipelines): ajoute le mécanisme execute générique (compile/execute mutuellement exclusifs)"
```

---

### Task 24: Brancher `execute` dans `runtime.py` + `transform.triangulate`

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/ops/execute.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: `_execute_transform_chain` (`app/pipelines/runtime.py:663`, déjà existant),
  `_read_geometry_rows`/`_write_geometry_rows` (Task 23).
- Produces: `TransformTriangulateParams` ; `_execute_triangulate(conn, *, input_view, view_name, params)
  -> None` ; entrée `"transform.triangulate"` ; dispatch générique `compile`/`execute` dans
  `_execute_transform_chain` (le branchement `if node.op == "transform.qgis":` reste **inchangé** à ce
  stade, cf. Global Constraints — retiré seulement à la Task 28).

- [ ] **Step 1: Vérifier `shapely.ops.triangulate` contre l'installation réelle**

```bash
cd core && uv run python3 -c "
import shapely.ops
from shapely.geometry import MultiPoint
print(shapely.ops.triangulate(MultiPoint([(0,0),(4,0),(2,4),(1,1)])))
"
```
Expected : une liste de `Polygon` triangles (vérifié pendant le brainstorming).

- [ ] **Step 2: Write the failing unit test (execute.py directement, sans runtime.py)**

Ajouter à `core/tests/test_pipeline_ops_execute.py` :

```python
def test_execute_triangulate_produces_one_row_per_triangle(conn):
    conn.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts VALUES "
        "(1, ST_Point(0, 0)), (2, ST_Point(4, 0)), (3, ST_Point(2, 4)), (4, ST_Point(1, 1))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts", view_name="out", params={})
    count = conn.execute("SELECT count(*) FROM out").fetchone()[0]
    assert count >= 2  # au moins 2 triangles pour 4 points non colinéaires
    geom_types = conn.execute("SELECT DISTINCT ST_GeometryType(geometry) FROM out").fetchall()
    assert geom_types == [("POLYGON",)]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k triangulate -v`
Expected: FAIL — `ImportError: cannot import name '_execute_triangulate'`

- [ ] **Step 4: Add `TransformTriangulateParams`**

Dans `core/app/pipelines/ops/schemas.py` :

```python
class TransformTriangulateParams(BaseModel):
    """Triangulation de Delaunay de la géométrie (points) en entrée — une ligne de sortie par
    triangle. Calculée en process via Shapely (BSD-3-Clause), pas en SQL."""
```

- [ ] **Step 5: Add `_execute_triangulate`**

Dans `core/app/pipelines/ops/execute.py`, ajouter en tête `import shapely.ops` et
`from shapely.geometry import MultiPoint`, puis :

```python
def _execute_triangulate(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformTriangulateParams

    TransformTriangulateParams.model_validate(params)  # forme seulement, aucun champ
    df = _read_geometry_rows(conn, input_view)
    points = [shapely.wkb.loads(bytes(wkb)) for wkb in df["geometry"]]
    triangles = shapely.ops.triangulate(MultiPoint([p.coords[0] for p in points]))
    other_cols = [c for c in df.columns if c != "geometry"]
    out = pd.DataFrame(
        {
            **{c: [df[c].iloc[0]] * len(triangles) for c in other_cols},
            "geometry": [shapely.wkb.dumps(t) for t in triangles],
        }
    )
    _write_geometry_rows(conn, out, view_name=view_name)
```

(La duplication des colonnes non-géométriques via `df[c].iloc[0]` suppose une seule ligne parente par appel
— **à vérifier/ajuster** contre le vrai cas d'usage no-code : si `input_view` porte plusieurs groupes de
points à trianguler séparément, cette implémentation les traite aujourd'hui comme un seul nuage global,
comportement à confirmer explicitement par un test dédié plutôt que supposé correct.)

- [ ] **Step 6: Register the op**

Dans `core/app/pipelines/ops/contracts.py`, import `TransformTriangulateParams` +
`from app.pipelines.ops import execute as _execute` (nouveau, à côté de l'import `compiler as _compiler`
déjà existant) :

```python
    "transform.triangulate": OperationContract(
        op="transform.triangulate",
        kind="transform",
        params_schema=TransformTriangulateParams,
        engine="duckdb",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_triangulate,
    ),
```

- [ ] **Step 7: Run the execute.py-level test**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k triangulate -v`
Expected: PASS

- [ ] **Step 8: Generalize the dispatch in `runtime.py`**

Dans `core/app/pipelines/runtime.py::_execute_transform_chain`, la branche actuelle (ligne ~714) :

```python
        if node.op == "transform.qgis":
            _execute_qgis_transform(...)
        else:
            sql = compiler.compile_transform_sql(...)
            conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
```

devient (garder la branche `transform.qgis` **inchangée**, insérer le nouveau cas entre elle et le `else`
générique — retirée seulement à la Task 28) :

```python
        from app.pipelines.ops.contracts import OPERATIONS

        contract = OPERATIONS[node.op]
        if node.op == "transform.qgis":
            _execute_qgis_transform(
                conn,
                node,
                input_view=input_view,
                input_srid=input_srid,
                qgis_worker_url=qgis_worker_url,
                qgis_worker_timeout_seconds=qgis_worker_timeout_seconds,
                scratch_run_id=scratch_run_id,
            )
        elif contract.execute is not None:
            contract.execute(
                conn, input_view=input_view, view_name=view_name, params=node.params
            )
        else:
            sql = compiler.compile_transform_sql(
                node.op,
                node.params,
                input_view=input_view,
                join_view=join_view,
                input_srid=input_srid,
                input_columns=input_columns,
                join_columns=join_columns,
            )
            conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
```

(Garder la résolution `input_columns`/`join_columns` déjà ajoutée par le plan `vague2-transform-ops.md`
Task 24 juste au-dessus de ce bloc, inchangée.)

- [ ] **Step 9: Write the end-to-end runtime test**

Lire d'abord la signature exacte de `run_pipeline`/`PipelinePayload`/`PipelineNode` (déjà fait par les plans
frères — réutiliser le même patron de construction de payload). Ajouter à
`core/tests/test_pipeline_runtime.py` un test exécutant un pipeline à 2 nœuds (`reader.collection` sur une
collection de points → `transform.triangulate` → un writer) de bout en bout, vérifiant que la sortie
contient bien des géométries `POLYGON`.

- [ ] **Step 10: Run the end-to-end test + full suite**

```bash
cd core
uv run pytest tests/test_pipeline_runtime.py -k triangulate -v
uv run pytest tests/ -k pipeline -v
```
Expected: PASS partout — le nœud `transform.qgis` continue de fonctionner exactement comme avant (branche
inchangée), aucune régression.

- [ ] **Step 11: Commit**

```bash
git add core/app/pipelines/runtime.py core/app/pipelines/ops/schemas.py \
  core/app/pipelines/ops/execute.py core/app/pipelines/ops/contracts.py \
  core/tests/test_pipeline_ops_execute.py core/tests/test_pipeline_runtime.py
git commit -m "feat(pipelines): branche le dispatch execute générique, ajoute transform.triangulate (retrait QGIS 6/9)"
```

---

### Task 25: `transform.densify`

Réutilise le mécanisme `execute` de la Task 23/24.

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/ops/execute.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_ops_execute.py`

**Interfaces:**
- Produces: `TransformDensifyParams` ; `_execute_densify` ; entrée `"transform.densify"`.

- [ ] **Step 1: Vérifier `shapely.segmentize` contre l'installation réelle**

```bash
cd core && uv run python3 -c "
import shapely
from shapely.geometry import LineString
print(shapely.segmentize(LineString([(0,0),(10,0)]), max_segment_length=2))
"
```
Expected : `LINESTRING (0 0, 2 0, 4 0, 6 0, 8 0, 10 0)` (vérifié pendant le brainstorming).

- [ ] **Step 2: Write the failing test**

```python
def test_execute_densify_adds_vertices_every_max_segment_length(conn):
    conn.execute("CREATE TABLE line (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO line VALUES (1, ST_GeomFromText('LINESTRING (0 0, 10 0)'))"
    )
    from app.pipelines.ops.execute import _execute_densify

    _execute_densify(
        conn, input_view="line", view_name="out", params={"maxSegmentLength": 2}
    )
    row = conn.execute("SELECT ST_NPoints(geometry) FROM out WHERE id = 1").fetchone()
    assert row == (6,)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k densify -v`
Expected: FAIL — `ImportError: cannot import name '_execute_densify'`

- [ ] **Step 4: Add `TransformDensifyParams`**

Dans `core/app/pipelines/ops/schemas.py` :

```python
class TransformDensifyParams(BaseModel):
    """Ajoute des sommets le long de chaque segment de la géométrie pour qu'aucun ne dépasse
    la longueur donnée. Calculé en process via Shapely."""

    maxSegmentLength: float
```

- [ ] **Step 5: Add `_execute_densify`**

Dans `core/app/pipelines/ops/execute.py` :

```python
def _execute_densify(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformDensifyParams

    p = TransformDensifyParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    df = df.assign(
        geometry=[
            shapely.wkb.dumps(shapely.segmentize(shapely.wkb.loads(bytes(g)), p.maxSegmentLength))
            for g in df["geometry"]
        ]
    )
    _write_geometry_rows(conn, df, view_name=view_name)
```

- [ ] **Step 6: Register the op**

```python
    "transform.densify": OperationContract(
        op="transform.densify",
        kind="transform",
        params_schema=TransformDensifyParams,
        engine="duckdb",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_densify,
    ),
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k densify -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/ops/execute.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_ops_execute.py
git commit -m "feat(pipelines): ajoute transform.densify (retrait QGIS 7/9)"
```

---

### Task 26: `transform.minimumBoundingCircle`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Modify: `core/app/pipelines/ops/execute.py`
- Modify: `core/app/pipelines/ops/contracts.py`
- Test: `core/tests/test_pipeline_ops_execute.py`

**Interfaces:**
- Produces: `TransformMinimumBoundingCircleParams` ; `_execute_minimum_bounding_circle` ; entrée
  `"transform.minimumBoundingCircle"`.

- [ ] **Step 1: Vérifier `shapely.minimum_bounding_circle` contre l'installation réelle**

```bash
cd core && uv run python3 -c "
import shapely
from shapely.geometry import MultiPoint
print(shapely.minimum_bounding_circle(MultiPoint([(0,0),(4,0),(2,3)])))
"
```
Expected : un `Polygon` circulaire (vérifié pendant le brainstorming, shapely>=2.0).

- [ ] **Step 2: Write the failing test**

```python
def test_execute_minimum_bounding_circle(conn):
    conn.execute("CREATE TABLE pts (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts VALUES "
        "(1, ST_Point(0, 0)), (2, ST_Point(4, 0)), (3, ST_Point(2, 3))"
    )
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    _execute_minimum_bounding_circle(conn, input_view="pts", view_name="out", params={})
    row = conn.execute("SELECT ST_GeometryType(geometry) FROM out").fetchone()
    assert row == ("POLYGON",)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k bounding_circle -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Add `TransformMinimumBoundingCircleParams`**

Dans `core/app/pipelines/ops/schemas.py` :

```python
class TransformMinimumBoundingCircleParams(BaseModel):
    """Remplace la géométrie par le plus petit cercle qui la contient entièrement. Calculé
    en process via Shapely (agrège toutes les lignes de l'entrée en un seul cercle)."""
```

- [ ] **Step 5: Add `_execute_minimum_bounding_circle`**

Dans `core/app/pipelines/ops/execute.py` :

```python
def _execute_minimum_bounding_circle(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformMinimumBoundingCircleParams

    TransformMinimumBoundingCircleParams.model_validate(params)  # forme seulement
    df = _read_geometry_rows(conn, input_view)
    geoms = [shapely.wkb.loads(bytes(g)) for g in df["geometry"]]
    circle = shapely.minimum_bounding_circle(shapely.geometry.GeometryCollection(geoms))
    out = pd.DataFrame({"geometry": [shapely.wkb.dumps(circle)]})
    _write_geometry_rows(conn, out, view_name=view_name)
```

- [ ] **Step 6: Register the op**

```python
    "transform.minimumBoundingCircle": OperationContract(
        op="transform.minimumBoundingCircle",
        kind="transform",
        params_schema=TransformMinimumBoundingCircleParams,
        engine="duckdb",
        engine_license="BSD-3-Clause (Shapely)",
        execute=_execute._execute_minimum_bounding_circle,
    ),
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -k bounding_circle -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/ops/execute.py \
  core/app/pipelines/ops/contracts.py core/tests/test_pipeline_ops_execute.py
git commit -m "feat(pipelines): ajoute transform.minimumBoundingCircle (retrait QGIS 8/9 + composition Clipper/Dissolver = 9/9)"
```

---

### Task 27: Reclassification de la matrice — 12 lignes vectorielles

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`
- Modify: `core/tests/test_pipeline_routes.py`
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ou équivalent)

- [ ] **Step 1: Mettre à jour le test de comptage d'op**

Ajouter les 9 nouvelles clés à l'ensemble attendu dans `test_pipeline_routes.py`
(`test_get_pipelines_ops_returns_all_*`) : `"transform.centroid"`, `"transform.convexHull"`,
`"transform.simplify"`, `"transform.boundingGeometry"`, `"transform.snapToLayer"`,
`"transform.resolveOverlaps"`, `"transform.triangulate"`, `"transform.densify"`,
`"transform.minimumBoundingCircle"`. Ajouter `"transform.snapToLayer"` à la liste des op vérifiées
`acceptsSecondaryInput is True`. Mettre à jour le test dédié `len(OPERATIONS)` — **vérifier au préalable
(Global Constraints) si `transform.qgis` était comptée dans le total de départ avant de fixer ce nombre.**

- [ ] **Step 2: Reclassifier les 9 lignes couvertes par de nouvelles op**

Dans `docs/revue/matrice-couverture-fme.jsonl`, `planned_duckdb` → `implemented`,
`geostudio_equivalent` renseigné : `CenterPointReplacer`→`transform.centroid`,
`HullReplacer`→`transform.convexHull`, `Generalizer`→`transform.simplify`,
`BoundingBoxReplacer`→`transform.boundingGeometry`, `Snapper`→`transform.snapToLayer`,
`AreaOnAreaOverlayer`→`transform.resolveOverlaps`, `TINGenerator`→`transform.triangulate`,
`SurfaceModeller`→`transform.triangulate`, `Densifier`→`transform.densify`,
`MinimumSpanningCircleReplacer`→`transform.minimumBoundingCircle`. Moteur : `duckdb` pour les 6 premières,
`rust:` ou une nouvelle valeur reflétant Shapely (vérifier la taxonomie `engine` dans
`docs/superpowers/specs/2026-09-15-matrice-couverture-fme-design.md` avant de forcer une valeur non prévue
— la valeur existante `rust:encoding_rs` montre que le champ accepte déjà des moteurs non-duckdb, `shapely`
ou `python:shapely` sont plausibles, à confirmer contre la vraie taxonomie plutôt que deviné ici).

- [ ] **Step 3: Reclassifier Clipper et Dissolver (composition, sans nouvel op)**

Pour `Clipper` et `Dissolver`, `qgis_frozen` → `implemented`. `geostudio_equivalent` : la taxonomie actuelle
exige une clé unique de `ops_catalog()` (vérifié en design §7, même limite que Vague 1 §3.2) — si
`fme_coverage_cli.py --check` rejette une valeur composée (ex. `"transform.intersection +
transform.aggregate"`), soit étendre le vérificateur pour accepter une liste d'op existantes plutôt qu'une
seule clé (changement dans `core/scripts/fme_coverage_cli.py`), soit laisser ces 2 lignes en `qgis_frozen`
avec une note explicite dans `notes` documentant qu'elles sont couvertes par composition — **décider au
Step 4 selon ce que `--check` accepte réellement, pas ici**.

- [ ] **Step 4: Régénérer et vérifier la matrice**

```bash
python3 core/scripts/fme_coverage_cli.py --write
python3 core/scripts/fme_coverage_cli.py --check
```
Expected: succès. Si `--check` échoue sur Clipper/Dissolver (Step 3), appliquer la décision retenue et
relancer.

- [ ] **Step 5: Run the full pipelines test suite**

Run: `cd core && uv run pytest tests/ -k pipeline -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl docs/revue/matrice-couverture-fme.md \
  core/tests/test_pipeline_routes.py core/tests/test_pipeline_ops_contracts.py \
  core/scripts/fme_coverage_cli.py
git commit -m "docs(revue): reclassifie 12 lignes qgis_frozen vectorielles vers implemented"
```

---

### Task 28: Retrait du code `transform.qgis`

**Ne pas exécuter avant que les Tasks 18-27 soient vertes** (Global Constraints).

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py` (retirer `TransformQgisParams`)
- Modify: `core/app/pipelines/ops/contracts.py` (retirer l'entrée `transform.qgis`)
- Modify: `core/app/pipelines/compiler.py` (retirer `_output_srid_qgis`)
- Modify: `core/app/pipelines/runtime.py` (retirer `_execute_qgis_transform`, `_materialize_qgis_output`,
  la branche `if node.op == "transform.qgis":`, `SCRATCH_ROOT`, `qgis_worker_url`/
  `qgis_worker_timeout_seconds` de toutes les signatures qui les threadent)
- Modify: `core/app/pipelines/service.py`/`jobs.py` (retirer les appelants de `qgis_worker_url`/timeout)
- Modify: `core/app/pipelines/routes.py` (retirer la route `GET /pipelines/ops/qgis-algorithms`)
- Delete: `core/app/pipelines/ops/qgis_algorithms.json`
- Delete: `core/tests/test_pipeline_qgis_algorithms.py`
- Modify: `core/tests/test_pipeline_runtime.py` (retirer tous les tests `@pytest.mark.qgis`)
- Modify: `core/tests/test_pipeline_routes.py` (retirer `test_get_qgis_algorithms_returns_full_allowlist`,
  `test_get_qgis_algorithms_absent_when_etl_disabled`, retirer `"transform.qgis"` de l'ensemble attendu par
  `test_get_pipelines_ops_returns_all_*`)
- Modify: `core/pyproject.toml` (retirer la déclaration du marqueur pytest `qgis`)
- Delete: `scripts/run-qgis-tests.sh`

- [ ] **Step 1: Localiser toutes les références**

```bash
cd core && grep -rln "qgis" app/ tests/ --include="*.py" -i
grep -rln "qgis" ../scripts ../*.md -i
```

Dresser la liste exhaustive avant de commencer à supprimer — ne pas se fier uniquement à la liste ci-dessus,
qui peut avoir raté un appelant.

- [ ] **Step 2: Retirer le code de `schemas.py`/`contracts.py`/`compiler.py`**

Retirer `TransformQgisParams` de `schemas.py`. Retirer l'entrée `"transform.qgis"` de `OPERATIONS` et
l'import `TransformQgisParams` dans `contracts.py`. Retirer `_output_srid_qgis` de `compiler.py` et son
import dans `contracts.py` (`output_srid=_compiler._output_srid_qgis`).

- [ ] **Step 3: Retirer le code de `runtime.py`**

Retirer `_execute_qgis_transform`, `_materialize_qgis_output`, la constante module-level `SCRATCH_ROOT` (si
elle n'est utilisée que par ces deux fonctions — vérifier qu'aucun autre appelant n'en dépend avant de la
supprimer). Dans `_execute_transform_chain`, la branche construite à la Task 24 Step 8 devient :

```python
        contract = OPERATIONS[node.op]
        if contract.execute is not None:
            contract.execute(
                conn, input_view=input_view, view_name=view_name, params=node.params
            )
        else:
            sql = compiler.compile_transform_sql(
                node.op,
                node.params,
                input_view=input_view,
                join_view=join_view,
                input_srid=input_srid,
                input_columns=input_columns,
                join_columns=join_columns,
            )
            conn.execute(f"CREATE TEMP VIEW {_qi(view_name)} AS {sql}")
```

Retirer `qgis_worker_url`/`qgis_worker_timeout_seconds` de la signature de `_execute_transform_chain`,
`preview_pipeline`, `run_pipeline`, et de chaque appel interne qui les passe.

- [ ] **Step 4: Retirer les appelants dans `service.py`/`jobs.py`**

Retirer toute lecture de `QGIS_WORKER_URL`/timeout de configuration et tout passage de ces valeurs vers
`run_pipeline`/`preview_pipeline`.

- [ ] **Step 5: Retirer la route et le fichier d'allowlist**

Dans `core/app/pipelines/routes.py`, retirer l'import `QGIS_ALGORITHMS` et la route
`@router.get("/pipelines/ops/qgis-algorithms")`. Supprimer `core/app/pipelines/ops/qgis_algorithms.json`.

- [ ] **Step 6: Retirer les tests**

Supprimer `core/tests/test_pipeline_qgis_algorithms.py`. Dans `core/tests/test_pipeline_runtime.py`,
retirer tous les tests marqués `@pytest.mark.qgis`. Dans `core/tests/test_pipeline_routes.py`, retirer
`test_get_qgis_algorithms_returns_full_allowlist`/`test_get_qgis_algorithms_absent_when_etl_disabled`, et
retirer `"transform.qgis"` de l'ensemble `set(body) == {...}` (déjà mis à jour à la Task 27 Step 1 avec les
9 ajouts — retirer maintenant cette 10e entrée).

- [ ] **Step 7: Retirer le marqueur pytest**

Dans `core/pyproject.toml`, retirer la ligne `"qgis: nécessite un sidecar qgis-worker réel
(CORE_TEST_QGIS_WORKER_URL) ; skippé sinon",`.

- [ ] **Step 8: Supprimer `scripts/run-qgis-tests.sh`**

```bash
rm scripts/run-qgis-tests.sh
```

- [ ] **Step 9: Run the full pipelines test suite**

Run: `cd core && uv run pytest tests/ -k pipeline -v`
Expected: PASS, aucune référence résiduelle à `transform.qgis`.

- [ ] **Step 10: Run the full core test suite + quality gates**

```bash
cd core
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run lint-imports
grep -rn "qgis" app/ tests/ --include="*.py" -i
```
Expected: tout vert, dernier `grep` sans résultat.

- [ ] **Step 11: Commit**

```bash
git add -A core/app/pipelines core/tests core/pyproject.toml
git rm scripts/run-qgis-tests.sh
git commit -m "feat(pipelines): retire complètement transform.qgis et l'allowlist d'algorithmes"
```

---

### Task 29: Retrait du sidecar `deploy/qgis-worker/` et `docker-compose.yml`

**Files:**
- Delete: `deploy/qgis-worker/` (répertoire complet)
- Modify: `docker-compose.yml`

- [ ] **Step 1: Vérifier les autres usages du volume `etl-scratch`**

```bash
grep -n "etl-scratch\|CORE_PIPELINE_FILE_IO_ENABLED" docker-compose.yml core/app/pipelines/*.py
```

Lire le code de `reader.file`/`writer.file` (`core/app/pipelines/runtime.py`, capacité gardée par
`CORE_PIPELINE_FILE_IO_ENABLED`) pour déterminer s'il utilise le même volume nommé `etl-scratch` monté sur
`worker`, ou son propre mécanisme scratch indépendant (piège CLAUDE.md n°11 : ne pas conclure par analogie
sans avoir lu l'appelant réel).

- [ ] **Step 2: Retirer le service `qgis-worker` de `docker-compose.yml`**

Supprimer le bloc `qgis-worker:` (profil `etl`) en entier. Retirer `QGIS_WORKER_URL` de l'environnement du
service `core`/`worker`. Selon la conclusion du Step 1 :
- si `worker` n'a plus aucun besoin de `/scratch` une fois `qgis-worker` retiré : retirer aussi le montage
  `etl-scratch:/scratch` sur `worker` et la déclaration du volume nommé `etl-scratch` en tête de fichier.
- sinon : garder le montage sur `worker` (toujours nécessaire pour `reader.file`/`writer.file`), retirer
  uniquement le service `qgis-worker` et son propre montage.

- [ ] **Step 3: Supprimer le répertoire du sidecar**

```bash
rm -rf deploy/qgis-worker
```

- [ ] **Step 4: Vérifier la configuration résultante**

```bash
docker compose config --profiles
docker compose --profile etl config | grep -i qgis
```
Expected: aucune trace de `qgis-worker` dans la configuration résolue, y compris avec le profil `etl` actif.

- [ ] **Step 5: Commit**

```bash
git add -A docker-compose.yml
git rm -r deploy/qgis-worker
git commit -m "chore(deploy): retire le sidecar qgis-worker de docker-compose.yml"
```

---

### Task 30: Retrait CI/CD (job `core-qgis`, matrice d'images, publication)

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/_build-and-push.yml`
- Modify: `scripts/check_published_images.py`

- [ ] **Step 1: Retirer le job `core-qgis`**

Dans `.github/workflows/ci.yml`, supprimer le job `core-qgis` en entier (lignes ~71-137, confirmées pendant
le brainstorming — relire le fichier réel avant de couper, les numéros de ligne peuvent avoir bougé depuis).
Vérifier qu'aucun autre job n'a de `needs: core-qgis`.

- [ ] **Step 2: Retirer `geostudio-qgis-worker` de la matrice de build**

Dans `.github/workflows/_build-and-push.yml`, retirer l'entrée `- image: geostudio-qgis-worker` (et son
`context: ./deploy/qgis-worker`) de la matrice — la matrice passe de 9 à 8 images.

- [ ] **Step 3: Mettre à jour `check_published_images.py`**

```bash
grep -n "qgis" scripts/check_published_images.py
```
Retirer `geostudio-qgis-worker` de la liste d'images attendues si présente.

- [ ] **Step 4: Vérifier `release.yml`/`publish-edge.yml`**

```bash
grep -rln "qgis" .github/workflows/
```
Traiter toute référence résiduelle trouvée par ce grep, pas seulement les 3 fichiers ci-dessus.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/_build-and-push.yml \
  scripts/check_published_images.py
git commit -m "ci: retire le job core-qgis et l'image geostudio-qgis-worker de la matrice de publication"
```

---

### Task 31: Documentation, inventaire, matrice raster, clôture

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl`
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl`
- Modify: `CLAUDE.md`
- Modify: `core/openapi.json` / `shell/src/api/generated/core-schema.d.ts` (régénérés)

- [ ] **Step 1: Étendre la taxonomie `coverage_status` pour les 7 lignes raster abandonnées**

Lire `docs/superpowers/specs/2026-09-15-matrice-couverture-fme-design.md` § Taxonomie. Ajouter une valeur
qui distingue « une solution existait (QGIS) et a été retirée pour raison de licence » d'un simple
`unknown` (aucune recherche n'a jamais abouti) — ex. `capability_removed`. Documenter ce choix dans ce même
fichier design (une ligne, pas un roman) puisqu'il étend une taxonomie déjà spécifiée ailleurs.

- [ ] **Step 2: Reclassifier les 7 lignes raster**

Dans `docs/revue/matrice-couverture-fme.jsonl`, pour `ContourGenerator`, `DEMGenerator`,
`RasterAspectCalculator`, `RasterHillshader`, `RasterResampler`, `RasterToPolygonCoercer`,
`RasterSlopeCalculator` : `qgis_frozen` → la nouvelle valeur du Step 1, `geostudio_equivalent` vidé,
`notes` mise à jour expliquant l'abandon (capacité techniquement atteignable via `rasterio`/GDAL embarqué —
vérifié en design §7.5 — mais bloquée par l'absence totale de support raster dans le moteur de pipeline).

- [ ] **Step 3: Régénérer et vérifier la matrice**

```bash
python3 core/scripts/fme_coverage_cli.py --write
python3 core/scripts/fme_coverage_cli.py --check
```

- [ ] **Step 4: Nettoyer `docs/revue/inventaire-fonctionnalites.jsonl`**

Retirer la ligne dédiée à QGIS (`automatisation-transformer-spatialement-des-donnees-via-qgis-processing-…`)
— la capacité n'existe plus. Dans les autres lignes qui référencent `GET /v1/pipelines/ops/qgis-algorithms`
dans leurs `surfaces.rest`/`publiques` (recherchées via `grep -n qgis
docs/revue/inventaire-fonctionnalites.jsonl` — au moins 4 lignes trouvées pendant le brainstorming), retirer
cette route de la liste. Mettre à jour la ligne « Publier une release taguée » (8 images → **7** images,
liste explicite sans `qgis-worker`). Mettre à jour la ligne « Exécuter les conteneurs applicatifs en
utilisateur non-root » (retirer la mention `qgis-worker`/la justification de convergence d'uid avec lui,
garder le reste si `core`/`worker`/`backup`/`appexport-runtime-builder` ont encore leur propre raison de
fixer un uid explicite). Pour la ligne « Distribuer les notices de licences tierces (GPL/AGPL) » : retirer
la référence à `deploy/qgis-worker/Dockerfile`, garder la ligne si `deploy/backup/Dockerfile` (notice AGPL
du client `mc`) est toujours d'actualité.

- [ ] **Step 5: Régénérer le bilan de fonctionnalités**

```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
```
Expected: `--write` réussit ; lancer aussi `--check` pour confirmer qu'aucune surface n'est orpheline après
le nettoyage du Step 4.

- [ ] **Step 6: Régénérer OpenAPI + types TS**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: diff non vide — 9 nouveaux schémas de params, retrait de `TransformQgisParams` et de la route
`qgis-algorithms`.

- [ ] **Step 7: Mettre à jour `CLAUDE.md` § Commandes**

Retirer toute mention de `run-qgis-tests.sh`/`core-qgis`/`CORE_TEST_QGIS_WORKER_URL` dans la section
Commandes (bloc `uv run pytest`, description des skips). Mettre à jour le compte de services
docker-compose (actuellement « 11 services par défaut… + 5 derrière un profil : etl (qgis-worker)… » —
`qgis-worker` disparaît de la liste des profils, ajuster le compte selon ce que la Task 29 a laissé pour
`etl-scratch`/le profil `etl` lui-même, qui peut survivre pour `reader.file`/`writer.file` même sans
`qgis-worker`).

- [ ] **Step 8: Ajouter une ligne dans `CLAUDE.md ### Livré`**

« **Retrait complet du sidecar QGIS (GPL-2.0-or-later)** — 12 des 19 lignes `qgis_frozen` migrées vers
DuckDB pur (6 op) ou Python en process via Shapely (3 op), + 2 par composition d'op existantes (Clipper,
Dissolver) ; 7 lignes raster abandonnées (aucun support raster dans le moteur de pipeline, blocage
architectural pas technique) ; sidecar, allowlist de 50 algorithmes, job CI, image de publication retirés
en entier — 0 trace de QGIS dans le dépôt. Catalogue à 58 op. **Rupture pour tout déploiement existant
utilisant un nœud `transform.qgis`** (aucune migration automatique, cf. design §8.6). »

- [ ] **Step 9: Documenter la rupture dans les notes de version**

Chercher où GeoStudio documente déjà ses changements cassants (`CHANGELOG`, notes de release GitHub, ou
équivalent — grep `CHANGELOG` à la racine du dépôt) et y ajouter une entrée explicite pour le retrait de
`transform.qgis`, avec la liste des 19 anciens `algorithmId` et leur op de remplacement quand il y en a un
(Task 27 Step 2) — pour qu'un opérateur qui migre puisse mapper manuellement ses pipelines existants.

- [ ] **Step 10: Run the full test suite one last time**

```bash
cd core && uv run pytest
cd ../shell && npm run test && npm run build
```
Expected: tout vert.

- [ ] **Step 11: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl docs/revue/matrice-couverture-fme.md \
  docs/revue/inventaire-fonctionnalites.jsonl docs/revue/bilan-fonctionnalites.* \
  docs/superpowers/specs/2026-09-15-matrice-couverture-fme-design.md \
  core/openapi.json shell/src/api/generated/core-schema.d.ts CLAUDE.md
git commit -m "docs: clôture le retrait du sidecar QGIS (matrice, inventaire, CLAUDE.md, catalogue à 58 op)"
```

## Self-Review

**Volet 1 — transform ops (Tasks 1-10) :**
- **Couverture de la spec** : §2.1 (11 op) → Tasks 1-9. §3.1/3.2 (needs_columns, fichiers touchés) → Task 7.
  §3.3 (transform.sort, best-effort) → Task 6. §4 (tests, falsification) → intégré à chaque tâche + Task 10.
  §5 (portes de qualité, régénération) → Task 10.
- **Placeholders** : aucun — chaque étape contient le code Python/SQL réel, les commandes exactes attendues.
- **Cohérence des types** : `compile_transform_sql` garde la même signature de retour (`str`) partout ;
  `_compile_xxx` des 8 op simples ignorent `input_columns`/`join_columns` par construction (jamais dans leur
  signature) ; les 3 `needs_columns=True` les déclarent explicitement — cohérent avec le Step 4 de la Task 7.

**Volet 2 — lecteurs (Tasks 11-17) :**
- **Couverture de la spec** : §6.1 (bigquery/mssql/oracle) → Tasks 12-14. §6.2 (blob) → Task 15. §6.3 (fichiers
  touchés, formulaire shell) → Tasks 12-16.
- **Placeholders** : les DSN/champs de credentials exacts (BigQuery, S3/Azure/GCS) sont explicitement
  marqués « à vérifier au Step 1 de chaque tâche » plutôt que fixés en dur sans preuve — conforme au piège
  CLAUDE.md n°3, pas un TBD non qualifié : chaque tâche a une étape de vérification concrète avant
  l'implémentation.
- **Cohérence des types** : les 4 `materialize_xxx_connector` partagent la même signature
  `(conn, *, secret_resolver, node_id, params, view_name) -> None`, cohérente avec les 2 connecteurs
  existants (Task 11).

**Volet 3 — retrait QGIS (Tasks 18-31) :**
- **Couverture de la spec** : §7.1 (6 op compile pur) → Tasks 18-22. §7.2 (mécanisme execute + 3 op) →
  Tasks 23-26. §7.4/§7.5 (tests, reclassification vecteur/raster) → Tasks 27, 31. §8.1-§8.6 (retrait mécanique
  complet, rupture documentée) → Tasks 28-31.
- **Placeholders** : les points explicitement marqués « à vérifier avant d'implémenter » (signature
  `ST_Snap`, cardinalité de `transform.triangulate` sur plusieurs groupes, forme de la taxonomie
  `coverage_status` étendue) sont des étapes de vérification concrètes avec commande à lancer, pas des TBD
  vagues.
- **Cohérence des types** : les 3 fonctions `_execute_xxx` partagent la signature
  `(conn, *, input_view, view_name, params) -> None` fixée à la Task 23 et jamais déviée dans les Tasks 24-26 ;
  `_read_geometry_rows`/`_write_geometry_rows` sont consommées telles quelles par les 3, jamais réimplémentées.
- **Ordre critique explicite** : Global Constraints + rappel en tête de Task 28 — les 9 nouvelles op doivent
  être vertes avant tout retrait mécanique, cohérence vérifiée à chaque tâche par le lancement de la suite
  complète (Tasks 24, 26, 27, 28, 31).

**Cohérence transversale (relue une fois les 3 volets fusionnés) :**
- Les comptes d'op intermédiaires (45 → 49 → 58) sont cohérents entre les Global Constraints et les Steps de
  clôture de chaque volet (Tasks 10, 17, 31).
- Aucune collision de nom entre les 24 nouvelles op des 3 volets (11 + 4 + 9), vérifié par lecture croisée
  des 3 tableaux de mapping FME→GeoStudio.
- Le mécanisme `needs_columns` (Task 7) et le mécanisme `execute` (Task 23) sont indépendants et
  n'interagissent pas — aucune des 3 op `needs_columns` n'a besoin d'`execute`, aucune des 3 op `execute`
  n'a besoin d'`needs_columns` — pas de risque de conflit d'implémentation entre les deux extensions du
  contrat.

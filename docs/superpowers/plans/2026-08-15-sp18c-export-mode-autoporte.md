# SP-18c — Export d'apps : mode Autoporté Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author export a published app as a self-contained Docker
artifact — a generic, prebuilt mini-server image serving a frozen GeoParquet
snapshot (OGC API Features Part 1 subset + `/aggregate`) alongside the same
prebuilt static shell runtime already used by Statique/Connecté — SP-18's
third and final export mode, closing jalon M15.

**Architecture:** `check_export_guard` gains `mode="standalone"` (same
`is_public` leniency as `connected` for `features`/`statistics` sources,
same builtin-widget-only allowlist as `static`). A new
`app.appexport.snapshot.write_snapshot` walks a config's DataSources exactly
like `freeze.py` does (in-process `introspect_table`+`select_features` under
`rls_scope`), but instead of embedding JSON records, writes each collection
as a local GeoParquet partition in the exact layout
`app.analytics.aggregate.run_collection_aggregate` already expects
(`tenant_id=X/collection_id=Y/dt=*/*.parquet`, `_lsn`/`_op` columns via
`app.cdc.parquet_writer.write_geoparquet`/`ChangeRow`, one synthetic
`op="insert"` row per feature) — so the mini-server's `/aggregate` endpoint
reuses `run_collection_aggregate` completely unmodified, just pointed at a
local path instead of `s3://`. A new `app.appexport.manifest` module is the
shared (de)serialization contract between the export job (full core,
Postgres-backed) and the mini-server (slim image, no Postgres) — it reuses
`TableInfo`/`ColumnInfo` (`app.collections.introspection`) verbatim rather
than duplicating their shape. The mini-server itself
(`app.appexport.miniserver`) is a small FastAPI app that serves the same
anonymous-capable path allowlist SP-18b's CORS middleware already
enumerated, plus the baked-in static shell bundle at the same origin — since
both are served by the same process, **the shell's existing Connecté
bootstrap code needs zero changes**: the mini-server just answers
`/geostudio-connection.json` dynamically with its own request origin, and
`entry.tsx` already knows how to build a live `ItemClient` from that file's
presence. A new Dockerfile builds this mini-server image, generically and
once (never per export — same philosophy as
`deploy/appexport-runtime-builder`), published to ghcr.io via a 4th entry in
`release.yml`'s existing matrix; each individual export only produces a
small data bundle (config JSON + manifest + snapshot Parquet files) plus a
generated `docker-compose.yml` referencing that published image.

**Tech Stack:** FastAPI/SQLAlchemy/DuckDB (core, existing patterns),
Vite/React/TypeScript (shell, existing patterns), Docker multi-stage build —
no new runtime dependency in `core`'s own pyproject (the mini-server image
has its own, separate, minimal dependency list installed directly via pip,
not `uv sync`).

## Global Constraints

- Capability gate is the **existing** `CORE_APPEXPORT_ENABLED` (no new
  flag) — `_SUPPORTED_MODES` in `core/app/appexport/routes.py` widens from
  `{"static", "connected"}` to `{"static", "connected", "standalone"}`.
- Same `max_records_per_source=50_000` cap as SP-18a's `freeze_config` —
  reused verbatim, not reconsidered here.
- **The generated `docker-compose.yml` always references
  `image: ghcr.io/tlenenao/geostudio-appexport-standalone:latest`** — not a
  version-pinned tag. This repo has never actually pushed a `v*.*.*` git
  tag, so `release.yml`'s existing matrix (which tags images with
  `${{ github.ref_name }}`) has never really published anything yet; there
  is also no existing mechanism anywhere in this codebase for a running
  `core` container to know which git tag it was built from. Inventing a
  pyproject-version-as-image-tag scheme that doesn't correspond to anything
  real would be worse than just being honest with `:latest`. **Known,
  documented gap** (same nature as the SP-15d/qgis precedent): a real
  `docker pull` against this image is unverified until a tag is actually
  cut — this plan's own E2E test (Task 12) works around it by building the
  image **locally**, the same trick `test-gate` already uses for the
  Postgis CI image.
- **No third-party SP-8 widget support in Autoporté** — `mode="standalone"`
  reuses the exact same builtin-only widget allowlist as `mode="static"`
  (decided in session 2026-08-15, spec §3.3/§6). Do not attempt to bundle
  arbitrary third-party ES modules for offline use.
- **The mini-server image is generic and app-agnostic, built once.** It
  bakes in the prebuilt static shell runtime (same `dist-export/` artifact
  Statique/Connecté already build via `npm run build:export-runtime`) and
  the mini-server Python code — but **never** any app-specific data. Each
  export only supplies a `/data` volume (config JSON + manifest + snapshot
  Parquet). Do not design a per-export Docker build/push — that would
  reintroduce exactly the kind of per-export cost the existing
  `appexport-runtime-builder`/`build_bundle_zip` split was designed to
  avoid.
- **The mini-server's own Dockerfile installs a deliberately minimal pip
  dependency set** (`fastapi`, `uvicorn[standard]`, `pydantic`, `duckdb`,
  `sqlalchemy`) directly via `pip install`, **not** `uv sync`/the full
  `core/pyproject.toml` — no `psycopg`/`psycopg2-binary` (no real Postgres
  driver ships in this image at all), no Keycloak-adjacent packages, no
  `dlt`/Playwright. `sqlalchemy` itself is required only because
  `app.collections.introspection`'s `TableInfo`/`ColumnInfo` (reused
  verbatim by `app.appexport.manifest` rather than duplicated) import
  `sqlalchemy.orm.Session` for an unrelated, unused-here type alias — this
  costs an install, never a real database connection (no driver is
  present). The Dockerfile `COPY`s the **whole** `core/app` directory
  (matching every other Dockerfile in this repo — `core/Dockerfile`,
  `deploy/export-worker/Dockerfile` — rather than a fragile selective
  `COPY` of two files): Python only needs installed dependencies for
  modules it actually imports, so the rest of `app/` sitting unused on disk
  is harmless.
- The mini-server is **strictly read-only** — no write route exists in
  `app.appexport.miniserver` at all (not merely disabled).
- **`app.appexport.snapshot.write_snapshot` writes no Parquet file for a
  collection with zero rows** — an empty `GeoDataFrame.to_parquet()` call
  would have its schema poorly inferred from zero rows. This is safe
  because both `run_collection_aggregate` (existing `_has_any_file` check)
  and this plan's own `app.appexport.miniserver.items` (Task 5, same
  pattern) already tolerate a missing glob match by returning an empty
  result — no special-casing needed on the read side.
- Every code step in this plan follows TDD (failing test → minimal
  implementation → passing test → commit), per this repo's CLAUDE.md.

---

## File structure

**Core (`core/`)**
- Modify `core/app/appexport/guard.py`, `core/tests/test_appexport_guard.py`
- Modify `core/app/analytics/duckdb_conn.py`, `core/tests/test_analytics_duckdb_conn.py`
- Create `core/app/appexport/manifest.py`, `core/tests/test_appexport_manifest.py`
- Create `core/app/appexport/snapshot.py`, `core/tests/test_appexport_snapshot.py`
- Create `core/app/appexport/miniserver/__init__.py`
- Create `core/app/appexport/miniserver/items.py`, `core/tests/test_appexport_miniserver_items.py`
- Create `core/app/appexport/miniserver/main.py`, `core/tests/test_appexport_miniserver_main.py`
- Modify `core/app/appexport/bundler.py`, `core/tests/test_appexport_bundler.py`
- Modify `core/app/appexport/jobs.py`, `core/tests/test_appexport_jobs.py`
- Modify `core/app/appexport/routes.py`, `core/tests/test_appexport_routes.py`
- Modify `core/pyproject.toml` (pytest marker registration)
- Create `core/tests/test_appexport_standalone_e2e.py`

**Deploy / CI**
- Create `deploy/appexport-standalone/Dockerfile`
- Modify `.github/workflows/release.yml`

**Shell (`shell/`)**
- Modify `shell/src/api/types.ts`
- Modify `shell/src/builder/appexport/AppExportPanel.tsx`, `shell/src/builder/appexport/AppExportPanel.test.tsx`

---

### Task 1: `check_export_guard` gains `mode="standalone"`

**Files:**
- Modify: `core/app/appexport/guard.py`
- Modify: `core/tests/test_appexport_guard.py`

**Interfaces:**
- Consumes: unchanged (`app.collections.repository`, `app.configs.schemas.BuilderConfig`).
- Produces: `check_export_guard(session, *, tenant_id, config, mode)` — `mode="standalone"` behaves like `mode="connected"` for the `is_public` check on `features`/`statistics` sources (statistics fully supported), but like `mode="static"` for the widget-type allowlist (builtin-only, no third-party widgets).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_appexport_guard.py` (every existing test/helper stays as-is above this):

```python


# --- Autoporté (SP-18c) : leniency d'is_public de "connected", allowlist de widgets de "static" ---


def test_statistics_source_on_public_collection_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _public_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is True


def test_statistics_source_on_non_public_collection_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="statistics", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False
    assert any(col.id in r and "publique" in r for r in result.reasons)


def test_features_source_on_non_public_collection_is_still_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        tenant_id, col = _private_collection(s)
        config = _app_config(data_sources=[
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ])
        result = check_export_guard(s, tenant_id=tenant_id, config=config, mode="standalone")
    assert result.allowed is False


def test_unsupported_widget_type_is_blocked_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "acme-widget"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is False
    assert any("acme-widget" in r for r in result.reasons)


def test_builtin_widgets_only_is_allowed_in_standalone_mode():
    Session = _session()
    with Session() as s:
        config = _app_config(data_sources=[], widget_types=("text", "table", "map"))
        result = check_export_guard(s, tenant_id="t1", config=config, mode="standalone")
    assert result.allowed is True
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: the five new `*_standalone_mode` tests FAIL — `mode="standalone"`
currently falls through `check_export_guard`'s `if mode == "static":` branch
as false (so the widget allowlist is never applied, `test_unsupported_widget_type_is_blocked_in_standalone_mode`
fails) and the `statistics` early-rejection is also skipped as false-for-static
only (so those pass by accident already) — actually verify empirically, the
important one to see fail is the widget-allowlist test.

- [ ] **Step 3: Update `guard.py`**

Replace the full contents of `core/app/appexport/guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Garde d'export (SP-18a/b/c) : refuse tout export dont une DataSource
référence une collection non publique. Le mode Statique (SP-18a) refuse en
plus les sources "statistics" (rien à figer côté serveur) et tout widget
hors de l'allowlist builtin (rien n'est bundlé au runtime, un widget tiers
serait introuvable). Le mode Connecté (SP-18b) n'a besoin d'aucune des deux
restrictions : "statistics" appelle /collections/{id}/aggregate en direct
au runtime (déjà anonyme-capable côté serveur pour une collection publique,
cf. app/features/routes.py's get_current_user_optional), et un widget tiers
charge son JS depuis son URL d'origine exactement comme dans le shell
normal — rien n'est bundlé, donc rien à interdire. Le mode Autoporté
(SP-18c) combine les deux axes indépendamment : is_public lenient comme
Connecté ("statistics" pleinement supporté, figé dans l'instantané et
interrogé via /aggregate par le mini-serveur), MAIS allowlist de widgets
stricte comme Statique (rien n'est bundlé ici non plus — décision prise en
session 2026-08-15, cf. design SP-18c §3.3 : aucune tentative de bundling
offline de widgets tiers)."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.schemas import BuilderConfig

# Miroir de shell/src/builder/widgets/{index,data,chart,pivot,navigation,
# form,hero,richSection,gallery,datasetCard,dateRangeFilter,selectFilter,
# sliderFilter,tabs,modal,drawer,filter,mapWidget,indicator}.tsx — à tenir
# en phase manuellement (pas de génération partagée TS/Python), même
# discipline que l'allowlist QGIS (SP-15d) ou les champs AggregateRequestBody.
# Pertinent pour mode="static" ET mode="standalone" — cf. docstring.
_SUPPORTED_WIDGET_TYPES = frozenset({
    "text", "image", "button", "table", "list", "map", "indicator", "chart",
    "pivot", "nav", "form", "hero", "richSection", "gallery", "datasetCard",
    "dateRangeFilter", "selectFilter", "sliderFilter", "tabs", "modal",
    "drawer", "filter",
})

_STRICT_WIDGET_MODES = frozenset({"static", "standalone"})


@dataclass
class ExportGuardResult:
    allowed: bool
    reasons: list[str] = field(default_factory=list)


def _collect_widget_types(config: BuilderConfig) -> set[str]:
    types: set[str] = set()
    # A config always has at least one page. If `pages` is empty (legacy /
    # implicit single-page shape, cf. shell/src/builder/pages.ts:6-7,23),
    # the widgets actually live in the top-level `layout` — scan both so a
    # single-page app (the common case) doesn't sail through unchecked.
    if config.layout is not None:
        for item in config.layout.items:
            types.add(item.widget)
    for page in config.pages:
        for item in page.layout.items:
            types.add(item.widget)
    return types


def check_export_guard(
    session: Session, *, tenant_id: str, config: BuilderConfig, mode: str,
) -> ExportGuardResult:
    reasons: list[str] = []

    for source in config.dataSources:
        if source.type == "static":
            continue
        if source.type == "statistics" and mode == "static":
            reasons.append(
                f"source '{source.id}' : l'export statique ne supporte pas encore "
                "les sources de type agrégat (statistics)"
            )
            continue
        if source.type not in ("features", "statistics"):
            reasons.append(f"source '{source.id}' : type '{source.type}' non supporté")
            continue
        # "features" (tous modes) et "statistics" en mode connecté/autoporté :
        # même garde is_public — connecté appelle /collections/{id}/aggregate
        # en direct au runtime, autoporté le fige dans l'instantané et le
        # sert depuis le mini-serveur ; aucun des deux n'a besoin de figer
        # un résultat au moment de l'export lui-même.
        collection_id = source.layer
        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
        if col is None:
            reasons.append(f"source '{source.id}' : collection '{collection_id}' introuvable")
            continue
        facts = collections_repo.get_access_facts(col)
        if not facts.is_public:
            reasons.append(
                f"source '{source.id}' : collection '{collection_id}' n'est pas partagée publiquement"
            )

    if mode in _STRICT_WIDGET_MODES:
        unsupported = _collect_widget_types(config) - _SUPPORTED_WIDGET_TYPES
        for widget_type in sorted(unsupported):
            reasons.append(
                f"widget '{widget_type}' non supporté par ce mode d'export "
                "(extension tierce, non prise en charge)"
            )

    return ExportGuardResult(allowed=not reasons, reasons=reasons)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_guard.py -v`
Expected: PASS (18 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/guard.py core/tests/test_appexport_guard.py
git commit -m "feat(core): export guard gains mode=standalone — connected leniency, static widget allowlist (SP-18c)"
```

---

### Task 2: `duckdb_conn.open_local_connection()`

**Files:**
- Modify: `core/app/analytics/duckdb_conn.py`
- Modify: `core/tests/test_analytics_duckdb_conn.py`

**Interfaces:**
- Produces: `open_local_connection() -> duckdb.DuckDBPyConnection` — loads
  only the `spatial` extension (no `httpfs`, no `h3`, no S3 `SET`
  statements). Used exclusively by the mini-server (Tasks 5/6), which only
  ever reads local files.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_analytics_duckdb_conn.py` (existing content and
`_RecordingConnection` stay as-is above this):

```python


def test_open_local_connection_installs_and_loads_spatial_only(monkeypatch):
    import duckdb

    from app.analytics.duckdb_conn import open_local_connection

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_local_connection()

    joined = "\n".join(recording.statements)
    assert "INSTALL spatial" in joined and "LOAD spatial" in joined
    assert "httpfs" not in joined
    assert "s3_" not in joined
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v`
Expected: FAIL with `ImportError: cannot import name 'open_local_connection'`

- [ ] **Step 3: Add `open_local_connection` to `duckdb_conn.py`**

In `core/app/analytics/duckdb_conn.py`, append after `open_spatial_connection`:

```python


def open_local_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour le mini-serveur autoporté (SP-18c) :
    lit un instantané GeoParquet local (jamais S3/MinIO) — seule l'extension
    spatial est nécessaire (ST_Intersects/ST_MakeEnvelope/ST_AsGeoJSON/
    ST_GeomFromGeoJSON), aucune configuration s3_* requise."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/duckdb_conn.py core/tests/test_analytics_duckdb_conn.py
git commit -m "feat(core): open_local_connection for the standalone mini-server (SP-18c)"
```

---

### Task 3: `app.appexport.manifest` — shared snapshot manifest shape

**Files:**
- Create: `core/app/appexport/manifest.py`
- Create: `core/tests/test_appexport_manifest.py`

**Interfaces:**
- Consumes: `TableInfo`/`ColumnInfo` (`app.collections.introspection`, unchanged).
- Produces: `CollectionSnapshotEntry` dataclass (`id: str`, `tenant_id: str`,
  `collection_json: dict`, `schema_json: dict`, `table_info: TableInfo`),
  `write_manifest(entries: list[CollectionSnapshotEntry], path: str) -> None`,
  `read_manifest(path: str) -> list[CollectionSnapshotEntry]`. This is the
  contract Task 4 (writer, full core) and Task 6 (reader, slim mini-server
  image) both depend on — the JSON on disk is the only thing that ever
  crosses between them, never a Python import across the image boundary.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_appexport_manifest.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.manifest import CollectionSnapshotEntry, read_manifest, write_manifest
from app.collections.introspection import ColumnInfo, TableInfo


def _entry() -> CollectionSnapshotEntry:
    table_info = TableInfo(
        table_name="t_x", pk_column="id", geometry_column="geom",
        geometry_type="point", srid=4326,
        columns=[ColumnInfo(name="name", type="string", required=False)],
    )
    return CollectionSnapshotEntry(
        id="col1", tenant_id="t1",
        collection_json={"id": "col1", "title": "X"},
        schema_json={"collection": "t_x", "pk": "id", "geometry": None, "fields": []},
        table_info=table_info,
    )


def test_write_then_read_manifest_round_trips(tmp_path):
    path = str(tmp_path / "manifest.json")
    write_manifest([_entry()], path)

    entries = read_manifest(path)

    assert len(entries) == 1
    e = entries[0]
    assert e.id == "col1"
    assert e.tenant_id == "t1"
    assert e.collection_json == {"id": "col1", "title": "X"}
    assert e.schema_json == {"collection": "t_x", "pk": "id", "geometry": None, "fields": []}
    assert e.table_info.table_name == "t_x"
    assert e.table_info.pk_column == "id"
    assert e.table_info.geometry_column == "geom"
    assert e.table_info.srid == 4326
    assert e.table_info.columns[0].name == "name"
    assert e.table_info.columns[0].type == "string"


def test_write_manifest_with_no_entries(tmp_path):
    path = str(tmp_path / "manifest.json")
    write_manifest([], path)
    assert read_manifest(path) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.manifest'`

- [ ] **Step 3: Create `manifest.py`**

Create `core/app/appexport/manifest.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Manifeste d'instantané autoporté (SP-18c) : forme partagée entre le job
d'export (app.appexport.snapshot, tourne dans le worker complet, tous les
paquets core disponibles) et le mini-serveur (app.appexport.miniserver,
tourne dans une image Docker séparée et volontairement minimale) — les deux
processus lisent/écrivent le même fichier manifest.json sur disque, jamais
d'appel réseau ni d'import Python entre eux à l'exécution.

Réutilise TableInfo/ColumnInfo tels quels (app.collections.introspection)
plutôt qu'une forme dupliquée : ces deux dataclasses n'ont aucune dépendance
d'exécution réelle à Postgres (Session n'y sert que de type non exécuté
dans un alias inutilisé ici) — seul le paquet sqlalchemy doit être installé
pour l'import, jamais un driver ni une connexion réelle (cf.
deploy/appexport-standalone/Dockerfile, qui n'installe ni psycopg ni
psycopg2-binary)."""
import json
from dataclasses import asdict, dataclass

from app.collections.introspection import ColumnInfo, TableInfo


@dataclass(frozen=True)
class CollectionSnapshotEntry:
    id: str
    tenant_id: str
    collection_json: dict
    schema_json: dict
    table_info: TableInfo


def write_manifest(entries: list[CollectionSnapshotEntry], path: str) -> None:
    payload = {
        "collections": [
            {
                "id": e.id,
                "tenantId": e.tenant_id,
                "collectionJson": e.collection_json,
                "schemaJson": e.schema_json,
                "tableInfo": {
                    "tableName": e.table_info.table_name,
                    "pkColumn": e.table_info.pk_column,
                    "geometryColumn": e.table_info.geometry_column,
                    "geometryType": e.table_info.geometry_type,
                    "srid": e.table_info.srid,
                    "columns": [asdict(c) for c in e.table_info.columns],
                },
            }
            for e in entries
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def read_manifest(path: str) -> list[CollectionSnapshotEntry]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    entries: list[CollectionSnapshotEntry] = []
    for raw in payload["collections"]:
        ti = raw["tableInfo"]
        table_info = TableInfo(
            table_name=ti["tableName"], pk_column=ti["pkColumn"],
            geometry_column=ti["geometryColumn"], geometry_type=ti["geometryType"],
            srid=ti["srid"], columns=[ColumnInfo(**c) for c in ti["columns"]],
        )
        entries.append(CollectionSnapshotEntry(
            id=raw["id"], tenant_id=raw["tenantId"],
            collection_json=raw["collectionJson"], schema_json=raw["schemaJson"],
            table_info=table_info,
        ))
    return entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_manifest.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/manifest.py core/tests/test_appexport_manifest.py
git commit -m "feat(core): app.appexport.manifest — shared snapshot manifest shape (SP-18c)"
```

---

### Task 4: `app.appexport.snapshot.write_snapshot`

**Files:**
- Create: `core/app/appexport/snapshot.py`
- Create: `core/tests/test_appexport_snapshot.py`

**Interfaces:**
- Consumes: `CollectionSnapshotEntry`/`write_manifest` (Task 3),
  `app.cdc.parquet_writer.ChangeRow`/`write_geoparquet` (unchanged),
  `app.collections.schema_json.table_info_to_schema` (unchanged),
  `app.features.repository.select_features`/`app.features.rls.rls_scope`
  (unchanged, same as `freeze.py`).
- Produces: `write_snapshot(session, *, tenant_id: str, config: BuilderConfig,
  snapshot_dir: str, max_records_per_source: int = 50_000) ->
  list[CollectionSnapshotEntry]` — for every distinct collection referenced
  by a `"features"`/`"statistics"` DataSource, writes a GeoParquet partition
  under `{snapshot_dir}/snapshot/tenant_id=.../collection_id=.../dt=snapshot/data.parquet`
  (skipped if the collection has zero rows) and a
  `{snapshot_dir}/manifest.json` listing every entry. Consumed by Task 7's
  bundler and Task 8's job.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_appexport_snapshot.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""write_snapshot (SP-18c) — mêmes contraintes PostGIS-réelles que
test_appexport_freeze.py : introspect_table/insert_feature/select_features
touchent pg_class/pg_namespace/geometry_columns et RLS Postgres réelle, ni
portable SQLite ni simulable sans une vraie base."""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — import-only, registers every model on
# Base.metadata before create_all() — même piège que test_appexport_freeze.py.
from app.appexport.manifest import read_manifest
from app.appexport.snapshot import write_snapshot
from app.collections.ddl import apply_collection_ddl
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import Base, make_session_factory
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from duckdb import connect as duckdb_connect

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_snapshot_x"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, items, "
            "users, tenants CASCADE"
        ))


def _app_config(data_sources) -> BuilderConfig:
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
        ))],
    )


def test_no_data_sources_writes_empty_manifest(pg_session, tmp_path):
    entries = write_snapshot(
        pg_session, tenant_id="t1", config=_app_config([]), snapshot_dir=str(tmp_path),
    )
    assert entries == []
    assert read_manifest(str(tmp_path / "manifest.json")) == []


def test_features_source_is_written_as_geoparquet(pg_session, tmp_path):
    s = pg_session
    s.execute(text(
        "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
    ))
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_snapshot_x",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    s.commit()

    info = introspect_table(s, col.table_name)
    with rls_scope(s, tenant.id):
        insert_feature(s, info, properties={"name": "Alpha"}, geometry=None)
        insert_feature(s, info, properties={"name": "Beta"}, geometry=None)
    s.commit()

    config = _app_config([
        DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
    ])
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.id == col.id
    assert entry.collection_json["featureCount"] == 2
    assert entry.collection_json["isPublic"] is True
    assert entry.collection_json["canWrite"] is False
    assert entry.schema_json["pk"] == "id"

    parquet_path = (
        tmp_path / "snapshot" / f"tenant_id={tenant.id}" / f"collection_id={col.id}"
        / "dt=snapshot" / "data.parquet"
    )
    assert parquet_path.is_file()
    conn = duckdb_connect(":memory:")
    rows = conn.execute(f"SELECT name FROM read_parquet('{parquet_path}') ORDER BY name").fetchall()
    conn.close()
    assert rows == [("Alpha",), ("Beta",)]

    on_disk = read_manifest(str(tmp_path / "manifest.json"))
    assert len(on_disk) == 1
    assert on_disk[0].id == col.id


def test_collection_with_no_rows_writes_no_parquet_file(pg_session, tmp_path):
    s = pg_session
    s.execute(text(
        "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
    ))
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_snapshot_x",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    s.commit()

    config = _app_config([
        DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
    ])
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert entries[0].collection_json["featureCount"] == 0
    parquet_dir = tmp_path / "snapshot" / f"tenant_id={tenant.id}" / f"collection_id={col.id}"
    assert not parquet_dir.exists()


def test_same_collection_referenced_twice_is_written_once(pg_session, tmp_path):
    s = pg_session
    s.execute(text(
        "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
    ))
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_snapshot_x",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    s.commit()

    config = _app_config([
        DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        DataSource(id="s2", type="statistics", service="core", layer=col.id, query={}),
    ])
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert len(entries) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.snapshot'`
(all four tests skip anyway if `CORE_TEST_DATABASE_URL` is unset — set it
before running, per this repo's usual postgis test setup, e.g. via the same
docker Postgres CI already spins up in `test-gate`).

- [ ] **Step 3: Create `snapshot.py`**

Create `core/app/appexport/snapshot.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Écrit un instantané GeoParquet local par collection référencée par une
config (SP-18c) — même patron in-process que app.appexport.freeze
(introspect_table + select_features sous rls_scope), mais au lieu
d'embarquer des enregistrements JSON dans la config, écrit une partition
GeoParquet au format CDC (app.cdc.parquet_writer.write_geoparquet/ChangeRow)
avec un seul _lsn=0/_op="insert" par ligne — un instantané est exactement
« un lot CDC de rien que des insertions ». app.analytics.aggregate.
run_collection_aggregate (réutilisé tel quel par le mini-serveur, Task 6)
attend cette disposition hive-partitionnée
(tenant_id=X/collection_id=Y/dt=*/*.parquet) avec colonnes _lsn/_op — c'est
pour ça, pas par choix arbitraire.

Une collection sans aucune ligne ne produit aucun fichier parquet (au lieu
d'un GeoDataFrame vide dont le schéma serait mal inféré) — le mini-serveur
(items.py/run_collection_aggregate) tolère déjà un glob sans fichier
(retourne une page vide), donc rien à modifier côté lecture.

Une même collection référencée par plusieurs DataSources (ex. une carte et
un widget d'agrégat sur la même collection) n'est écrite qu'une fois —
dédoublonnage par collection_id."""
import os

from shapely.geometry import shape as shapely_shape

from app.appexport.manifest import CollectionSnapshotEntry, write_manifest
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs.schemas import BuilderConfig
from app.features.repository import select_features
from app.features.rls import rls_scope

_PAGE_SIZE = 1000


def _collection_json(col, *, feature_count: int) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": False,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
        "canWrite": False, "featureCount": feature_count, "owner": None,
    }


def _fetch_rows(session, *, tenant_id: str, info, max_records: int) -> list[ChangeRow]:
    rows: list[ChangeRow] = []
    offset = 0
    with rls_scope(session, tenant_id):
        while len(rows) < max_records:
            page = select_features(
                session, info, limit=_PAGE_SIZE, offset=offset,
                bbox=None, geom_intersects=None, filters=None,
            )
            for feature in page.features:
                geometry = feature["geometry"]
                wkb_hex = shapely_shape(geometry).wkb_hex if geometry else None
                rows.append(ChangeRow(
                    op="insert", lsn=0, ts=0.0, pk_column=info.pk_column,
                    pk_value=feature["id"], columns=feature["properties"],
                    geometry_column=info.geometry_column, geometry_wkb_hex=wkb_hex,
                ))
            if len(page.features) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    return rows[:max_records]


def write_snapshot(
    session, *, tenant_id: str, config: BuilderConfig, snapshot_dir: str,
    max_records_per_source: int = 50_000,
) -> list[CollectionSnapshotEntry]:
    entries: list[CollectionSnapshotEntry] = []
    seen: set[str] = set()

    for source in config.dataSources:
        if source.type not in ("features", "statistics"):
            continue
        collection_id = source.layer
        if collection_id in seen:
            continue
        seen.add(collection_id)

        col = collections_repo.get_collection(session, tenant_id=tenant_id, collection_id=collection_id)
        info = introspect_table(session, col.table_name)
        rows = _fetch_rows(session, tenant_id=tenant_id, info=info, max_records=max_records_per_source)

        if rows:
            parquet_dir = os.path.join(
                snapshot_dir, "snapshot", f"tenant_id={tenant_id}",
                f"collection_id={collection_id}", "dt=snapshot",
            )
            os.makedirs(parquet_dir, exist_ok=True)
            write_geoparquet(rows, srid=info.srid or 4326, path=os.path.join(parquet_dir, "data.parquet"))

        entries.append(CollectionSnapshotEntry(
            id=col.id, tenant_id=tenant_id,
            collection_json=_collection_json(col, feature_count=len(rows)),
            schema_json=table_info_to_schema(info),
            table_info=info,
        ))

    os.makedirs(snapshot_dir, exist_ok=True)
    write_manifest(entries, os.path.join(snapshot_dir, "manifest.json"))
    return entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_snapshot.py -v`
Expected: PASS (4 tests) against a real `CORE_TEST_DATABASE_URL` Postgres;
SKIPPED (all 4) if that env var is unset.

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/snapshot.py core/tests/test_appexport_snapshot.py
git commit -m "feat(core): write_snapshot — GeoParquet snapshot per collection (SP-18c)"
```

---

### Task 5: `app.appexport.miniserver.items` — DuckDB-backed features listing

**Files:**
- Create: `core/app/appexport/miniserver/__init__.py`
- Create: `core/app/appexport/miniserver/items.py`
- Create: `core/tests/test_appexport_miniserver_items.py`

**Interfaces:**
- Consumes: `open_local_connection` (Task 2), `TableInfo`/`ColumnInfo`
  (`app.collections.introspection`, unchanged), `ChangeRow`/`write_geoparquet`
  (`app.cdc.parquet_writer`, used only by the test fixture here, mirroring
  what Task 4's writer produces).
- Produces: `FeaturePage` dataclass (`features: list[dict]`,
  `number_matched: int`, `number_returned: int`),
  `select_features(conn, *, base_uri, tenant_id, collection_id, table_info,
  limit, offset, bbox=None, geom_intersects=None) -> FeaturePage`,
  `get_feature(conn, *, base_uri, tenant_id, collection_id, table_info,
  fid: str) -> dict | None`. Mirrors `app.features.repository`'s function
  names/shapes (same `FeatureCollection`-ready output), reading via DuckDB
  SQL against a local GeoParquet snapshot instead of Postgres. Consumed by
  Task 6's `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `core/app/appexport/miniserver/__init__.py` (empty file):

```python
```

Create `core/tests/test_appexport_miniserver_items.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.miniserver.items import get_feature, select_features
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _write_fixture(tmp_path, *, tenant_id="t1", collection_id="col1"):
    rows = [
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=1,
                  columns={"name": "Alpha"}, geometry_column=None, geometry_wkb_hex=None),
        ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=2,
                  columns={"name": "Beta"}, geometry_column=None, geometry_wkb_hex=None),
    ]
    parquet_dir = tmp_path / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(rows, srid=4326, path=str(parquet_dir / "data.parquet"))
    return TableInfo(
        table_name="t_x", pk_column="id", geometry_column=None, geometry_type=None, srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )


def test_select_features_reads_snapshot(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=10, offset=0,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert sorted(f["properties"]["name"] for f in page.features) == ["Alpha", "Beta"]
    assert all(f["type"] == "Feature" for f in page.features)


def test_select_features_paginates(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, limit=1, offset=1,
        )
    finally:
        conn.close()
    assert page.number_matched == 2
    assert page.number_returned == 1


def test_select_features_missing_collection_returns_empty_page(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="ghost",
            table_info=table_info, limit=10, offset=0,
        )
    finally:
        conn.close()
    assert page.features == []
    assert page.number_matched == 0


def test_get_feature_returns_single_row(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="2",
        )
    finally:
        conn.close()
    assert feature["properties"]["name"] == "Beta"


def test_get_feature_missing_returns_none(tmp_path):
    table_info = _write_fixture(tmp_path)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="col1",
            table_info=table_info, fid="999",
        )
    finally:
        conn.close()
    assert feature is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_items.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.miniserver.items'`

- [ ] **Step 3: Create `items.py`**

Create `core/app/appexport/miniserver/items.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Lecture des features via DuckDB contre un instantané GeoParquet local
(SP-18c) — mirroir de app.features.repository (mêmes noms de fonctions, même
forme de sortie FeatureCollection-ready), mais via SQL DuckDB au lieu de
SQL Postgres paramétré : app.features.repository est Postgres-only,
inutilisable dans le mini-serveur (pas de driver Postgres dans cette
image). Même glob hive-partitionné que app.analytics.aggregate (tenant_id=/
collection_id=/dt=*/*.parquet) — Task 4's write_snapshot écrit exactement
cette disposition."""
import json
from dataclasses import dataclass

from app.collections.introspection import TableInfo


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int
    number_returned: int


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _glob(base_uri: str, tenant_id: str, collection_id: str) -> str:
    return f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"


def _has_any_file(conn, base_uri: str, tenant_id: str, collection_id: str) -> bool:
    glob = _glob(base_uri, tenant_id, collection_id)
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _property_columns(info: TableInfo) -> list:
    return [c for c in info.columns if c.name not in (info.pk_column, "tenant_id", info.geometry_column)]


def _select_list(info: TableInfo) -> str:
    cols = [_qi(info.pk_column)]
    cols += [_qi(c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"ST_AsGeoJSON({_qi(info.geometry_column)}) AS __geo")
    return ", ".join(cols)


def _row_to_feature(info: TableInfo, row: dict) -> dict:
    props = {c.name: row[c.name] for c in _property_columns(info)}
    geometry = None
    if info.geometry_column and row.get("__geo"):
        geometry = json.loads(row["__geo"])
    return {"type": "Feature", "id": row[info.pk_column], "geometry": geometry, "properties": props}


def _fetch_rows(conn, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in result]


def _build_where(table_info: TableInfo, bbox, geom_intersects) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_MakeEnvelope(?, ?, ?, ?))")
        params.extend([minx, miny, maxx, maxy])
    if geom_intersects is not None:
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_GeomFromGeoJSON(?))")
        params.append(json.dumps(geom_intersects))
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _coerce_fid(table_info: TableInfo, fid: str):
    pk = next((c for c in table_info.columns if c.name == table_info.pk_column), None)
    if pk is not None and pk.type == "integer":
        try:
            return int(fid)
        except ValueError:
            return None
    return fid


def select_features(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo,
    limit: int, offset: int, bbox=None, geom_intersects=None,
) -> FeaturePage:
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return FeaturePage(features=[], number_matched=0, number_returned=0)
    glob = _glob(base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(table_info, bbox, geom_intersects)
    count_sql = f"SELECT COUNT(*) FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) {where_sql}"
    matched = conn.execute(count_sql, where_params).fetchone()[0]
    sql = (
        f"SELECT {_select_list(table_info)} FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"{where_sql} ORDER BY {_qi(table_info.pk_column)} LIMIT ? OFFSET ?"
    )
    rows = _fetch_rows(conn, sql, [*where_params, limit, offset])
    features = [_row_to_feature(table_info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched, number_returned=len(features))


def get_feature(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo, fid: str,
) -> dict | None:
    value = _coerce_fid(table_info, fid)
    if value is None or not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return None
    glob = _glob(base_uri, tenant_id, collection_id)
    sql = (
        f"SELECT {_select_list(table_info)} FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"WHERE {_qi(table_info.pk_column)} = ?"
    )
    rows = _fetch_rows(conn, sql, [value])
    return _row_to_feature(table_info, rows[0]) if rows else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_items.py -v`
Expected: PASS (5 tests) — no `CORE_TEST_DATABASE_URL` needed, pure DuckDB/local files.

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/miniserver/__init__.py core/app/appexport/miniserver/items.py core/tests/test_appexport_miniserver_items.py
git commit -m "feat(core): mini-server DuckDB-backed features listing (SP-18c)"
```

---

### Task 6: `app.appexport.miniserver.main` — the FastAPI mini-server

**Files:**
- Create: `core/app/appexport/miniserver/main.py`
- Create: `core/tests/test_appexport_miniserver_main.py`

**Interfaces:**
- Consumes: `read_manifest` (Task 3), `select_features`/`get_feature`
  (Task 5), `open_local_connection` (Task 2),
  `AggregateRequestBody`/`UnknownAggregateField`/`run_collection_aggregate`
  (`app.analytics.aggregate`, unchanged).
- Produces: `app` — a FastAPI instance. Routes:
  `GET /geostudio-connection.json` (dynamic, echoes `request.base_url`),
  `GET /geostudio-app-config.json` (serves the mounted config file),
  `GET /collections`, `GET /collections/{id}`, `GET /collections/{id}/schema`,
  `GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`,
  `POST /collections/{id}/aggregate`, plus a catch-all static mount at `/`
  serving the baked-in shell runtime. Reads `APPEXPORT_STANDALONE_DATA_DIR`
  (default `/data`) and `APPEXPORT_STANDALONE_RUNTIME_DIR` (default
  `/runtime`) at **import time** — deliberately not per-request (the static
  mount itself can only be configured once at startup in Starlette), so
  tests must set both env vars via `monkeypatch` **before** importing/
  reloading this module.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_appexport_miniserver_main.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import importlib
import json

from fastapi.testclient import TestClient

from app.appexport.manifest import CollectionSnapshotEntry, write_manifest
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _build_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "geostudio-app-config.json").write_text(json.dumps({"kind": "app"}))

    table_info = TableInfo(
        table_name="t_x", pk_column="id", geometry_column=None, geometry_type=None, srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )
    entry = CollectionSnapshotEntry(
        id="col1", tenant_id="t1",
        collection_json={
            "id": "col1", "title": "X", "description": "", "tableName": "t_x",
            "isPublic": True, "editable": False, "geometryType": None, "srid": 4326,
            "pkColumn": "id", "canWrite": False, "featureCount": 1, "owner": None,
        },
        schema_json={
            "collection": "t_x", "pk": "id", "geometry": None,
            "fields": [{"name": "name", "type": "string", "required": False}],
        },
        table_info=table_info,
    )
    write_manifest([entry], str(data_dir / "manifest.json"))

    parquet_dir = data_dir / "snapshot" / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(
        [ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=1,
                   columns={"name": "Alpha"}, geometry_column=None, geometry_wkb_hex=None)],
        srid=4326, path=str(parquet_dir / "data.parquet"),
    )
    return data_dir


def _client(tmp_path, monkeypatch):
    data_dir = _build_data_dir(tmp_path)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.html").write_text("<html><body>runtime</body></html>")
    monkeypatch.setenv("APPEXPORT_STANDALONE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("APPEXPORT_STANDALONE_RUNTIME_DIR", str(runtime_dir))

    import app.appexport.miniserver.main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_geostudio_app_config_is_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-app-config.json")
    assert response.status_code == 200
    assert response.json() == {"kind": "app"}


def test_geostudio_connection_echoes_request_origin(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-connection.json")
    assert response.status_code == 200
    assert response.json()["coreUrl"].startswith("http")


def test_list_collections_returns_manifest_entries(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections")
    assert response.status_code == 200
    assert [c["id"] for c in response.json()["collections"]] == ["col1"]


def test_get_collection_includes_links(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1")
    assert response.status_code == 200
    body = response.json()
    assert body["itemType"] == "feature"
    assert any(link["rel"] == "items" for link in body["links"])


def test_get_collection_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/ghost").status_code == 404


def test_get_schema_returns_manifest_schema(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/schema")
    assert response.status_code == 200
    assert response.json()["pk"] == "id"


def test_list_items_reads_snapshot(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["name"] == "Alpha"


def test_get_single_item(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items/1")
    assert response.status_code == 200
    assert response.json()["properties"]["name"] == "Alpha"


def test_get_single_item_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/col1/items/999").status_code == 404


def test_aggregate_counts_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/col1/aggregate", json={"agg": "count"})
    assert response.status_code == 200
    assert response.json()["rows"][0]["value"] == 1


def test_aggregate_unknown_collection_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/ghost/aggregate", json={"agg": "count"})
    assert response.status_code == 404


def test_static_runtime_is_served_at_root(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "runtime" in response.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.miniserver.main'`

- [ ] **Step 3: Create `main.py`**

Create `core/app/appexport/miniserver/main.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Mini-serveur read-only du mode Autoporté (SP-18c) : sert le même
sous-ensemble anonyme-capable qu'énumérait déjà l'allowlist CORS de SP-18b
(GET /collections[...], POST .../aggregate), plus le bundle statique du
shell prébâti — un seul processus, une seule origine, donc AUCUN CORS requis
(contrairement au mode Connecté, qui appelle un cœur GeoStudio distant
depuis un domaine tiers). /geostudio-connection.json répond dynamiquement
avec sa propre origine : entry.tsx (déjà livré en SP-18b) n'a besoin
d'aucun changement, il construit déjà un ItemClient "connecté" dès qu'il
voit ce fichier — ici "connecté" signifie simplement "à soi-même".

DATA_DIR/RUNTIME_DIR sont lus une fois à l'import (le mount StaticFiles ne
peut être configuré qu'au démarrage dans Starlette) — les tests rechargent
ce module après avoir positionné les variables d'environnement
(importlib.reload), jamais une lecture par requête ici."""
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from app.analytics.aggregate import AggregateRequestBody, UnknownAggregateField, run_collection_aggregate
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.manifest import read_manifest
from app.appexport.miniserver.items import get_feature, select_features

DATA_DIR = Path(os.environ.get("APPEXPORT_STANDALONE_DATA_DIR", "/data"))
RUNTIME_DIR = Path(os.environ.get("APPEXPORT_STANDALONE_RUNTIME_DIR", "/runtime"))

_MANIFEST_BY_ID = {e.id: e for e in read_manifest(str(DATA_DIR / "manifest.json"))}

app = FastAPI()


def _snapshot_base_uri() -> str:
    return str(DATA_DIR / "snapshot")


def _get_entry(collection_id: str):
    entry = _MANIFEST_BY_ID.get(collection_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return entry


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    return tuple(float(p) for p in parts) if len(parts) == 4 else None


@app.get("/geostudio-connection.json")
def geostudio_connection(request: Request):
    return {"coreUrl": str(request.base_url).rstrip("/")}


@app.get("/geostudio-app-config.json")
def geostudio_app_config():
    path = DATA_DIR / "geostudio-app-config.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="geostudio-app-config.json not found")
    return Response(content=path.read_bytes(), media_type="application/json")


@app.get("/collections")
def list_collections():
    return {"collections": [e.collection_json for e in _MANIFEST_BY_ID.values()]}


@app.get("/collections/{collection_id}")
def get_collection(collection_id: str, request: Request):
    entry = _get_entry(collection_id)
    base = str(request.base_url).rstrip("/")
    body = dict(entry.collection_json)
    body["itemType"] = "feature"
    body["extent"] = None
    body["links"] = [
        {"rel": "self", "type": "application/json", "href": f"{base}/collections/{entry.id}"},
        {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{entry.id}/items"},
    ]
    return body


@app.get("/collections/{collection_id}/schema")
def get_schema(collection_id: str):
    return _get_entry(collection_id).schema_json


@app.get("/collections/{collection_id}/items")
def list_items(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None,
):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
            collection_id=collection_id, table_info=entry.table_info,
            limit=min(limit, 1000), offset=offset, bbox=_parse_bbox(bbox),
        )
    finally:
        conn.close()
    return {
        "type": "FeatureCollection", "features": page.features,
        "numberMatched": page.number_matched, "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}],
    }


@app.get("/collections/{collection_id}/items/{fid}")
def get_single_item(collection_id: str, fid: str):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
            collection_id=collection_id, table_info=entry.table_info, fid=fid,
        )
    finally:
        conn.close()
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return feature


@app.post("/collections/{collection_id}/aggregate")
def aggregate(collection_id: str, body: AggregateRequestBody):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        try:
            category_key, rows = run_collection_aggregate(
                conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
                collection_id=collection_id, table_info=entry.table_info, request=body,
            )
        except UnknownAggregateField as exc:
            raise HTTPException(
                status_code=400,
                detail={"errors": [{"field": exc.field, "code": "unknown_field", "message": exc.message}]},
            )
    finally:
        conn.close()
    return {"categoryKey": category_key, "rows": rows}


# Doit rester la DERNIÈRE route enregistrée : Starlette matche dans l'ordre
# d'ajout, un mount à "/" déclaré plus tôt masquerait toutes les routes
# ci-dessus. html=True sert index.html pour "/" et pour toute route
# client-side (fallback SPA).
app.mount("/", StaticFiles(directory=str(RUNTIME_DIR), html=True), name="static")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_main.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/miniserver/main.py core/tests/test_appexport_miniserver_main.py
git commit -m "feat(core): standalone mini-server FastAPI app (SP-18c)"
```

---

### Task 7: `build_standalone_bundle_zip`

**Files:**
- Modify: `core/app/appexport/bundler.py`
- Modify: `core/tests/test_appexport_bundler.py`

**Interfaces:**
- Produces: `build_standalone_bundle_zip(config: BuilderConfig, *,
  snapshot_dir: str) -> bytes` — zips `config` as `data/geostudio-app-config.json`,
  every file under `snapshot_dir` (manifest.json + snapshot/...) as
  `data/...`, plus a generated `docker-compose.yml` and `README.md` at the
  zip root. Consumed by Task 8's job.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_bundler.py` (existing content stays as-is above this):

```python


def _write_snapshot_fixture(tmp_path):
    snapshot_src = tmp_path / "snapshot-src"
    parquet_dir = snapshot_src / "snapshot" / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    (parquet_dir / "data.parquet").write_bytes(b"fake-parquet-bytes")
    (snapshot_src / "manifest.json").write_text('{"collections": []}')
    return snapshot_src


def test_standalone_bundle_contains_data_manifest_and_compose(tmp_path):
    snapshot_src = _write_snapshot_fixture(tmp_path)

    zip_bytes = build_standalone_bundle_zip(_config(), snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "data/geostudio-app-config.json" in names
        assert "data/manifest.json" in names
        assert "data/snapshot/tenant_id=t1/collection_id=col1/dt=snapshot/data.parquet" in names
        assert "docker-compose.yml" in names
        assert "README.md" in names

        config_payload = zf.read("data/geostudio-app-config.json").decode("utf-8")
        assert '"kind"' in config_payload and '"app"' in config_payload

        compose = zf.read("docker-compose.yml").decode("utf-8")
        assert "ghcr.io/tlenenao/geostudio-appexport-standalone:latest" in compose
        assert "./data:/data:ro" in compose


def test_standalone_bundle_with_empty_snapshot_dir(tmp_path):
    snapshot_src = tmp_path / "empty-snapshot"
    snapshot_src.mkdir()
    (snapshot_src / "manifest.json").write_text('{"collections": []}')

    zip_bytes = build_standalone_bundle_zip(_config(), snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        assert "data/manifest.json" in names
        assert "data/geostudio-app-config.json" in names
```

Add the import at the top of the file:

```python
from app.appexport.bundler import build_bundle_zip, build_standalone_bundle_zip
```

(replacing the existing `from app.appexport.bundler import build_bundle_zip` line)

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_standalone_bundle_zip'`

- [ ] **Step 3: Add `build_standalone_bundle_zip` to `bundler.py`**

In `core/app/appexport/bundler.py`, append after `build_bundle_zip`:

```python


_STANDALONE_COMPOSE = """\
services:
  app:
    image: ghcr.io/tlenenao/geostudio-appexport-standalone:latest
    ports:
      - "8090:8000"
    volumes:
      - ./data:/data:ro
    restart: unless-stopped
"""

_STANDALONE_README = """\
# App GeoStudio exportée (mode Autoporté)

## Démarrer

    docker compose up -d

Puis ouvrir http://localhost:8090

## Contenu

- `data/geostudio-app-config.json` : configuration de l'app (figée à l'export).
- `data/manifest.json` : métadonnées des collections figées.
- `data/snapshot/` : instantané des données au format GeoParquet.

Le conteneur est strictement en lecture seule : aucune donnée n'est jamais
écrite. Un ré-export manuel depuis GeoStudio est nécessaire pour rafraîchir
l'instantané.
"""


def build_standalone_bundle_zip(config: BuilderConfig, *, snapshot_dir: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("data/geostudio-app-config.json", config.model_dump_json(by_alias=True))
        for root, _dirs, files in os.walk(snapshot_dir):
            for name in files:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, snapshot_dir)
                zf.write(full, arcname=f"data/{rel}")
        zf.writestr("docker-compose.yml", _STANDALONE_COMPOSE)
        zf.writestr("README.md", _STANDALONE_README)
    return buf.getvalue()
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_bundler.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/bundler.py core/tests/test_appexport_bundler.py
git commit -m "feat(core): build_standalone_bundle_zip — data+compose bundle (SP-18c)"
```

---

### Task 8: `build_app_export_task` branches on `mode="standalone"`

**Files:**
- Modify: `core/app/appexport/jobs.py`
- Modify: `core/tests/test_appexport_jobs.py`

**Interfaces:**
- Consumes: `write_snapshot` (Task 4), `build_standalone_bundle_zip` (Task 7).
- Produces: unchanged public signature `build_app_export_task(job_id: str,
  tenant_id: str) -> None`. For `mode="standalone"`: writes a snapshot to a
  temporary directory, builds the standalone zip from it, uploads exactly
  like the other two modes.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_appexport_jobs.py` (existing content stays as-is above this):

```python


def test_standalone_job_with_no_data_sources_succeeds(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, mode="standalone")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "done"
    assert job.result_key == f"appexports/{job_id}.zip"


def test_standalone_job_with_private_source_marks_error(monkeypatch, tmp_path):
    Session, tenant_id, job_id = _setup(monkeypatch, tmp_path, with_private_source=True, mode="standalone")
    monkeypatch.setattr("app.appexport.jobs._session_factory", lambda: Session)
    monkeypatch.setattr("app.appexport.jobs.s3_client_from_env", _fake_s3)
    build_app_export_task(job_id=job_id, tenant_id=tenant_id)
    with Session() as s:
        job = appexport_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
    assert job.status == "error"
    assert "publique" in job.error
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: `test_standalone_job_with_no_data_sources_succeeds` FAILS — the job
ends in `error` because `_prepare_bundle_inputs` currently falls through to
the `static`/`freeze_config` branch for any unrecognized mode string, but
`APPEXPORT_RUNTIME_DIR`'s fixture `index.export.html` is present so it would
actually succeed as a (wrong) static export instead — verify empirically
which failure mode you see; either way `test_standalone_job_with_private_source_marks_error`
passes already by accident (the guard rejection happens before mode
branching). The important assertion to watch is Step 4 below.

- [ ] **Step 3: Update `jobs.py`**

Replace the full contents of `core/app/appexport/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate (SP-18a/b/c) : guard → (statique : gèle les
DataSources ; connecté : garde la config telle quelle + embarque l'URL du
cœur ; autoporté : écrit un instantané GeoParquet local + zippe avec un
docker-compose.yml généré) → upload S3. Tourne sur le worker partagé (queue
`appexport`, pas de Chromium/Node/Docker ici — écrire un instantané local
avant de zipper n'a besoin ni de Docker ni de réseau). Toute erreur marque
le job "error", jamais un job bloqué en "running" (même critère que
app.export.jobs/app.pipelines.jobs)."""
import logging
import os
import tempfile

from app.appexport import repository as appexport_repo
from app.appexport.bundler import build_bundle_zip, build_standalone_bundle_zip
from app.appexport.freeze import freeze_config
from app.appexport.guard import check_export_guard
from app.appexport.snapshot import write_snapshot
from app.auth.dependency import is_appexport_enabled
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import ensure_uploads_bucket, make_s3_client
from app.jobs import app

logger = logging.getLogger(__name__)


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _prepare_bundle_inputs(
    session, *, tenant_id: str, mode: str, config: BuilderConfig,
) -> tuple[BuilderConfig, dict | None]:
    if mode == "connected":
        core_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
        return config, {"coreUrl": core_url}
    return freeze_config(session, tenant_id=tenant_id, config=config), None


def _build_zip_bytes(session, *, tenant_id: str, mode: str, config: BuilderConfig) -> bytes:
    if mode == "standalone":
        with tempfile.TemporaryDirectory() as snapshot_dir:
            write_snapshot(session, tenant_id=tenant_id, config=config, snapshot_dir=snapshot_dir)
            return build_standalone_bundle_zip(config, snapshot_dir=snapshot_dir)
    bundle_config, connection = _prepare_bundle_inputs(session, tenant_id=tenant_id, mode=mode, config=config)
    runtime_dir = os.environ["APPEXPORT_RUNTIME_DIR"]
    return build_bundle_zip(bundle_config, runtime_dir=runtime_dir, connection=connection)


@app.task(queue="appexport")
def build_app_export_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    if not is_appexport_enabled():
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error="app export capability disabled")
        return

    with request_scoped_session(session_factory) as session:
        job = appexport_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("app export job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        appexport_repo.mark_running(session, job_id=job_id)
        item_id = job.item_id
        mode = job.mode

    try:
        with request_scoped_session(session_factory) as session:
            config_read = configs_repo.get_config_by_item(session, item_id)
            if config_read is None:
                raise ValueError(f"app export item '{item_id}' not found")
            guard_result = check_export_guard(session, tenant_id=tenant_id, config=config_read.config, mode=mode)
            if not guard_result.allowed:
                raise ValueError("; ".join(guard_result.reasons))
            zip_bytes = _build_zip_bytes(session, tenant_id=tenant_id, mode=mode, config=config_read.config)

        result_key = f"appexports/{job_id}.zip"
        bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        s3_client = s3_client_from_env()
        ensure_uploads_bucket(s3_client, bucket)
        s3_client.put_object(Bucket=bucket, Key=result_key, Body=zip_bytes, ContentType="application/zip")

        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_done(session, job_id=job_id, result_key=result_key)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("app export job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            appexport_repo.mark_error(session, job_id=job_id, error=str(exc))
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_jobs.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/jobs.py core/tests/test_appexport_jobs.py
git commit -m "feat(core): app export job branches on mode=standalone (SP-18c)"
```

---

### Task 9: widen `_SUPPORTED_MODES` on the routes

**Files:**
- Modify: `core/app/appexport/routes.py`
- Modify: `core/tests/test_appexport_routes.py`

**Interfaces:**
- Produces: `POST /app-exports` now accepts `mode: "static" | "connected" |
  "standalone"`.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_appexport_routes.py`:

```python


def test_post_app_export_accepts_standalone_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/app-exports", json={"itemId": item_id, "mode": "standalone"})
    assert response.status_code == 202
    assert len(calls) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: `test_post_app_export_accepts_standalone_mode` FAILS with `422`.

- [ ] **Step 3: Widen `_SUPPORTED_MODES` in `routes.py`**

In `core/app/appexport/routes.py`, change:

```python
_SUPPORTED_MODES = {"static", "connected"}  # "standalone" arrive en SP-18c
```

to:

```python
_SUPPORTED_MODES = {"static", "connected", "standalone"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_routes.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/routes.py core/tests/test_appexport_routes.py
git commit -m "feat(core): POST /app-exports accepts mode=standalone (SP-18c)"
```

---

### Task 10: `deploy/appexport-standalone/Dockerfile`

**Files:**
- Create: `deploy/appexport-standalone/Dockerfile`

**Interfaces:**
- Produces: a Docker image serving `app.appexport.miniserver.main:app` on
  port 8000, with the baked-in static shell runtime at `/runtime` and an
  empty `/data` mount point (populated at `docker run`/`docker compose up`
  time by whatever the exported zip's `docker-compose.yml` mounts there).

- [ ] **Step 1: Create the Dockerfile**

Create `deploy/appexport-standalone/Dockerfile`:

```dockerfile
# deploy/appexport-standalone/Dockerfile
# Image générique de l'export d'app "Autoporté" (SP-18c) : bâtie UNE FOIS
# (CI/release, jamais par export — même philosophie que
# deploy/appexport-runtime-builder), publiée sur ghcr.io. Contexte = racine
# du dépôt (comme appexport-runtime-builder) : la première étape a besoin de
# shell/, la seconde de core/app/. Les données propres à un export (config
# de l'app, instantané GeoParquet) ne sont JAMAIS dans l'image — montées au
# runtime via le volume /data (cf. docker-compose.yml généré par
# build_standalone_bundle_zip, core/app/appexport/bundler.py).
FROM node:20-slim AS shell-runtime
WORKDIR /build
COPY shell/package.json shell/package-lock.json ./
RUN npm ci
COPY shell/ .
RUN npm run build:export-runtime
# StaticFiles(html=True) (core/app/appexport/miniserver/main.py) sert
# index.html pour "/" — le build Vite produit index.export.html
# (vite.export.config.ts's rollupOptions.input), jamais index.html.
RUN mv dist-export/index.export.html dist-export/index.html

FROM python:3.12-slim
WORKDIR /app
# Dépendances volontairement minimales — PAS `uv sync`/pyproject.toml
# complet (psycopg/psycopg2-binary/Keycloak/dlt/Playwright...) : le
# mini-serveur ne parle jamais à Postgres/Keycloak/MinIO, seulement à
# DuckDB + des fichiers locaux montés en lecture seule. sqlalchemy reste
# nécessaire : app.collections.introspection (TableInfo/ColumnInfo,
# réutilisés tels quels par app.appexport.manifest) importe
# sqlalchemy.orm.Session pour un alias de type non utilisé ici — coûte
# l'installation du paquet, jamais une connexion réelle (aucun driver
# psycopg présent dans cette image).
RUN pip install --no-cache-dir fastapi 'uvicorn[standard]' pydantic duckdb sqlalchemy
RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL spatial')"
# Copie l'arbre app/ complet (même convention que core/Dockerfile et
# deploy/export-worker/Dockerfile) plutôt qu'un COPY sélectif fragile :
# Python n'a besoin de paquets installés que pour les modules réellement
# importés par app.appexport.miniserver.main — le reste, présent sur disque
# mais jamais importé, est inoffensif.
COPY core/app ./app
COPY --from=shell-runtime /build/dist-export /runtime
ENV APPEXPORT_STANDALONE_DATA_DIR=/data
ENV APPEXPORT_STANDALONE_RUNTIME_DIR=/runtime
EXPOSE 8000
CMD ["uvicorn", "app.appexport.miniserver.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Build it locally to verify**

Run (from repo root): `docker build -f deploy/appexport-standalone/Dockerfile -t geostudio-appexport-standalone:local .`
Expected: build succeeds (two stages, no errors). This is a real build
verification step, not a placeholder — do not skip it.

- [ ] **Step 3: Commit**

```bash
git add deploy/appexport-standalone/Dockerfile
git commit -m "feat(deploy): standalone mini-server Docker image (SP-18c)"
```

---

### Task 11: publish `geostudio-appexport-standalone` to ghcr.io

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Produces: on a `v*.*.*` tag push, `release.yml`'s `build-and-push` job
  also builds and pushes `ghcr.io/tlenenao/geostudio-appexport-standalone`.

- [ ] **Step 1: Add `dockerfile` to every matrix entry and add the 4th image**

In `.github/workflows/release.yml`, replace:

```yaml
      matrix:
        include:
          - image: geostudio-core
            context: ./core
          - image: geostudio-shell
            context: ./shell
          - image: geostudio-postgis
            context: ./deploy/postgis
```

with:

```yaml
      matrix:
        include:
          - image: geostudio-core
            context: ./core
            dockerfile: Dockerfile
          - image: geostudio-shell
            context: ./shell
            dockerfile: Dockerfile
          - image: geostudio-postgis
            context: ./deploy/postgis
            dockerfile: Dockerfile
          - image: geostudio-appexport-standalone
            context: .
            dockerfile: deploy/appexport-standalone/Dockerfile
```

- [ ] **Step 2: Pass the resolved Dockerfile path to `docker/build-push-action`**

In the same file, replace:

```yaml
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

with:

```yaml
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.context }}/${{ matrix.dockerfile }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

(For `geostudio-core`: `context=./core` + `dockerfile=Dockerfile` →
`file=./core/Dockerfile`, identical to today's implicit default. For the
new image: `context=.` + `dockerfile=deploy/appexport-standalone/Dockerfile`
→ `file=./deploy/appexport-standalone/Dockerfile`.)

- [ ] **Step 3: Validate the workflow YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: no exception. (This repo has no tag to push and trigger a real
run — parsing is the only automated check available here; the actual
build-and-push path is exercised for real the next time Tanguy cuts a
release, same gap already documented for `geostudio-core`/`shell`/`postgis`.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): publish geostudio-appexport-standalone to ghcr.io (SP-18c)"
```

---

### Task 12: real E2E — cold-started container serves the app from a snapshot

**Files:**
- Modify: `core/pyproject.toml` (register the `docker` marker)
- Create: `core/tests/test_appexport_standalone_e2e.py`

**Interfaces:**
- Consumes: `write_snapshot` (Task 4), `build_standalone_bundle_zip`
  (Task 7), the Docker image built by Task 10's Dockerfile.
- Produces: a real, unmocked proof — matches this SP's own design doc §5:
  build the image locally (never `docker pull` — no tag has ever been
  published, cf. Global Constraints), start a cold container (fresh image,
  fresh bind-mounted data, no prior state), hit it over real HTTP, tear it
  down.

- [ ] **Step 1: Register the `docker` pytest marker**

In `core/pyproject.toml`, change:

```toml
markers = [
    "postgis: nécessite un PostGIS réel (CORE_TEST_DATABASE_URL) ; skippé sinon",
    "qgis: nécessite un sidecar qgis-worker réel (CORE_TEST_QGIS_WORKER_URL) ; skippé sinon",
    "playwright: nécessite le binaire Chromium (playwright install --with-deps chromium) ; skippé sinon",
]
```

to:

```toml
markers = [
    "postgis: nécessite un PostGIS réel (CORE_TEST_DATABASE_URL) ; skippé sinon",
    "qgis: nécessite un sidecar qgis-worker réel (CORE_TEST_QGIS_WORKER_URL) ; skippé sinon",
    "playwright: nécessite le binaire Chromium (playwright install --with-deps chromium) ; skippé sinon",
    "docker: nécessite un démon Docker réel (build local de l'image, jamais un pull) ; skippé sinon",
]
```

- [ ] **Step 2: Write the test**

Create `core/tests/test_appexport_standalone_e2e.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Preuve en conditions réelles (pas assérée), SP-18c design §5 : construit
l'image du mini-serveur localement (jamais un docker pull — aucun tag n'a
jamais été publié sur ce dépôt, cf. plan §Global Constraints), démarre un
conteneur à froid (image + volume de données vierges), vérifie qu'il sert
l'app et l'instantané sans qu'aucun Postgres/Keycloak/MinIO n'apparaisse
dans son compose. @pytest.mark.postgis (write_snapshot a besoin d'une
collection réelle) ET @pytest.mark.docker (besoin d'un démon Docker) —
skippé si l'un des deux manque."""
import io
import shutil
import socket
import subprocess
import time
import zipfile
from pathlib import Path

import pytest
import requests
from sqlalchemy import text

import app.main  # noqa: F401 — import-only, registers every model on
# Base.metadata before create_all() — même piège que test_appexport_freeze.py.
from app.appexport.bundler import build_standalone_bundle_zip
from app.appexport.snapshot import write_snapshot
from app.collections.ddl import apply_collection_ddl
from app.collections.introspection_pg import introspect_table
from app.collections.repository import create_collection
from app.configs.schemas import BuilderConfig, DataSource, Layout, LayoutItem, Page
from app.db import Base, make_session_factory
from app.features.repository import insert_feature
from app.features.rls import rls_scope
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = [pytest.mark.postgis, pytest.mark.docker]

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "geostudio-appexport-standalone:e2e-test"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(["docker", "info"], capture_output=True, timeout=10, check=True)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def standalone_image():
    if not _docker_available():
        pytest.skip("docker non disponible — test standalone E2E skippé")
    subprocess.run(
        ["docker", "build", "-f", "deploy/appexport-standalone/Dockerfile", "-t", IMAGE_TAG, "."],
        cwd=str(REPO_ROOT), check=True, capture_output=True, timeout=900,
    )
    return IMAGE_TAG


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_standalone_e2e"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, items, "
            "users, tenants CASCADE"
        ))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_cold_started_container_serves_app_and_snapshot(pg_session, standalone_image, tmp_path):
    s = pg_session
    s.execute(text(
        "CREATE TABLE t_standalone_e2e (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
    ))
    s.commit()
    apply_collection_ddl(s, "t_standalone_e2e")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_standalone_e2e",
        title="X", description="", is_public=True,
        pk_column="id", geometry_column=None, geometry_type=None, srid=None,
    )
    s.commit()
    info = introspect_table(s, col.table_name)
    with rls_scope(s, tenant.id):
        insert_feature(s, info, properties={"name": "Alpha"}, geometry=None)
    s.commit()

    config = BuilderConfig(
        kind="app", dataSources=[DataSource(id="s1", type="features", service="core", layer=col.id, query={})],
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="P1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="table", x=0, y=0, w=4, h=2, props={"dataSourceId": "s1"})],
        ))],
    )

    snapshot_src = tmp_path / "snapshot-src"
    snapshot_src.mkdir()
    write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(snapshot_src))
    zip_bytes = build_standalone_bundle_zip(config, snapshot_dir=str(snapshot_src))

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        compose_text = zf.read("docker-compose.yml").decode("utf-8")
        for forbidden in ("postgis", "keycloak", "minio"):
            assert forbidden not in compose_text.lower()
        for name in zf.namelist():
            if name.startswith("data/"):
                target = tmp_path / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(name))
    data_dir = tmp_path / "data"

    port = _free_port()
    run = subprocess.run(
        ["docker", "run", "-d", "-p", f"{port}:8000", "-v", f"{data_dir}:/data:ro", standalone_image],
        capture_output=True, check=True, text=True,
    )
    container_id = run.stdout.strip()
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                if requests.get(f"{base}/geostudio-app-config.json", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(1)
        else:
            pytest.fail("le mini-serveur autoporté n'a jamais répondu")

        config_resp = requests.get(f"{base}/geostudio-app-config.json", timeout=5)
        assert config_resp.status_code == 200
        assert config_resp.json()["kind"] == "app"

        items_resp = requests.get(f"{base}/collections/{col.id}/items", timeout=5)
        assert items_resp.status_code == 200
        names = [f["properties"]["name"] for f in items_resp.json()["features"]]
        assert names == ["Alpha"]

        agg_resp = requests.post(f"{base}/collections/{col.id}/aggregate", json={"agg": "count"}, timeout=5)
        assert agg_resp.status_code == 200
        assert agg_resp.json()["rows"][0]["value"] == 1

        index_resp = requests.get(f"{base}/", timeout=5)
        assert index_resp.status_code == 200
        assert "text/html" in index_resp.headers["content-type"]
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True)
```

- [ ] **Step 3: Run it (Docker + `CORE_TEST_DATABASE_URL` required)**

Run: `cd core && uv run pytest tests/test_appexport_standalone_e2e.py -v -s`
Expected: PASS with a real Docker daemon and `CORE_TEST_DATABASE_URL` set;
SKIPPED with a clear reason if either is unavailable — verify **both**
directions actually occur (run once with Docker available, and once with
`docker` temporarily renamed off `PATH` or `CORE_TEST_DATABASE_URL` unset,
to confirm the skip path — not just documented as best-effort, per this
repo's stated bar for this class of test, cf. SP-17a Task 6 precedent).

- [ ] **Step 4: Run the full core suite to confirm nothing broke**

Run: `cd core && uv run pytest -q && uv run lint-imports`
Expected: PASS, no import-linter violations (this SP adds no new
cross-layer import — `app.appexport.miniserver` only imports from
`app.analytics`/`app.collections`/`app.appexport`, all already below or
alongside `app.appexport` in the existing layered-architecture contract).

- [ ] **Step 5: Commit**

```bash
git add core/pyproject.toml core/tests/test_appexport_standalone_e2e.py
git commit -m "test(e2e): standalone export container serves app from a real snapshot (SP-18c)"
```

---

### Task 13: widen `AppExportMode` on the shell

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `AppExportMode = "static" | "connected" | "standalone"`.

- [ ] **Step 1: Widen the type**

In `shell/src/api/types.ts`, change:

```ts
export type AppExportMode = "static" | "connected";
```

to:

```ts
export type AppExportMode = "static" | "connected" | "standalone";
```

- [ ] **Step 2: Run the type checker**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): AppExportMode gains \"standalone\" (SP-18c)"
```

---

### Task 14: "Autoporté" button on `AppExportPanel`

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.tsx`
- Modify: `shell/src/builder/appexport/AppExportPanel.test.tsx`

**Interfaces:**
- Produces: same public component signature — a third dialog button next to
  Statique/Connecté. Reuses the `pendingWarningMode: AppExportMode | null`
  mechanism SP-18b already fixed (Task 8 of the SP-18b plan) — no new bug
  class here, `pendingWarningMode` was already generalized past a single
  hardcoded mode.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/appexport/AppExportPanel.test.tsx`:

```tsx


  it("triggers a standalone export and shows a download link once done", async () => {
    const client = makeClient({
      createAppExport: vi.fn().mockResolvedValue({ jobId: "job1" }),
      getAppExportJob: vi.fn().mockResolvedValue({ id: "job1", status: "done", resultUrl: "https://x.test/bundle.zip", error: null }),
    });
    render(
      <ItemClientProvider client={client}>
        <AppExportPanel itemId="item1" config={config()} />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /exporter/i }));
    await userEvent.click(screen.getByRole("button", { name: /autoport/i }));
    await waitFor(() => expect(screen.getByRole("link", { name: /télécharger/i })).toBeInTheDocument());
    expect(client.createAppExport).toHaveBeenCalledWith("item1", "standalone");
  });
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: FAIL — no "Autoporté" button exists yet.

- [ ] **Step 3: Add the button in `AppExportPanel.tsx`**

In `shell/src/builder/appexport/AppExportPanel.tsx`, replace the dialog's
button row:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
            Connecté
          </Button>
        </div>
```

with:

```tsx
        <div className="flex justify-end gap-2">
          <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
            Statique
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
            Connecté
          </Button>
          <Button type="button" size="sm" onClick={() => onChooseMode("standalone")}>
            Autoporté
          </Button>
        </div>
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the shell's full check suite**

Run: `cd shell && npm run test && npx tsc --noEmit`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/appexport/AppExportPanel.test.tsx
git commit -m "feat(shell): AppExportPanel gains an Autoporté button (SP-18c)"
```

---

## Self-review notes

- **Spec coverage:** design §3.1 (snapshot production, CDC-compatible
  layout) → Task 4. §3.2 (mini-server, same CORS-enumerated path allowlist,
  serves the shell bundle from the same origin) → Tasks 5/6. §3.3 (guard:
  connected-style `is_public` leniency + static-style widget allowlist) →
  Task 1. §3.4 (ghcr.io distribution, `:latest`, documented unverified-pull
  gap, E2E builds locally) → Tasks 10/11/12 + Global Constraints. §3.5
  (artifact shape: data/ + generated compose + README) → Task 7. §4 (no
  writes, no auto-refresh, no third-party widgets) → enforced by Task 1's
  guard and the mini-server never exposing a write route (Task 6). §5 (real
  E2E, cold container, no Postgres/Keycloak/MinIO in the generated compose)
  → Task 12.
- **Placeholder scan:** none found — every step has complete, runnable code
  or an exact command with an expected result.
- **Type consistency:** `CollectionSnapshotEntry` defined once in Task 3's
  `manifest.py`, constructed identically in Task 4 (`snapshot.py`) and
  consumed identically in Task 6 (`main.py`, via `read_manifest`) — same
  field names (`id`, `tenant_id`, `collection_json`, `schema_json`,
  `table_info`) throughout. `select_features`/`get_feature`'s
  `(conn, *, base_uri, tenant_id, collection_id, table_info, ...)` signature
  from Task 5 is called identically in Task 6. `build_standalone_bundle_zip(config,
  *, snapshot_dir)` defined in Task 7, called identically in Task 8 and
  Task 12. `AppExportMode` widened in Task 13, used identically in Task 14
  (`onChooseMode("standalone")`) — no shell code elsewhere hardcodes the
  two-mode union (verified against SP-18b's Task 6/8, which already
  generalized `pendingWarningMode` past a single mode).

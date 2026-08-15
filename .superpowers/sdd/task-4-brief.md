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


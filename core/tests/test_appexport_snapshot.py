# SPDX-License-Identifier: Apache-2.0
"""write_snapshot (SP-18c) — mêmes contraintes PostGIS-réelles que
test_appexport_freeze.py : introspect_table/insert_feature/select_features
touchent pg_class/pg_namespace/geometry_columns et RLS Postgres réelle, ni
portable SQLite ni simulable sans une vraie base."""

import pytest
from duckdb import connect as duckdb_connect
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

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_snapshot_x"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, audit_log, items, users, tenants CASCADE"
            )
        )


def _app_config(data_sources) -> BuilderConfig:
    return BuilderConfig(
        kind="app",
        dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[
            Page(
                id="p1",
                name="Page 1",
                layout=Layout(
                    type="grid",
                    items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
                ),
            )
        ],
    )


def test_no_data_sources_writes_empty_manifest(pg_session, tmp_path):
    entries = write_snapshot(
        pg_session,
        tenant_id="t1",
        config=_app_config([]),
        snapshot_dir=str(tmp_path),
    )
    assert entries == []
    assert read_manifest(str(tmp_path / "manifest.json")) == []


def test_features_source_is_written_as_geoparquet(pg_session, tmp_path):
    s = pg_session
    s.execute(
        text(
            "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
        )
    )
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_snapshot_x",
        title="X",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    s.commit()

    info = introspect_table(s, col.table_name)
    with rls_scope(s, tenant.id):
        insert_feature(s, info, properties={"name": "Alpha"}, geometry=None)
        insert_feature(s, info, properties={"name": "Beta"}, geometry=None)
    s.commit()

    config = _app_config(
        [
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ]
    )
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert len(entries) == 1
    entry = entries[0]
    assert entry.id == col.id
    assert entry.collection_json["featureCount"] == 2
    assert entry.collection_json["isPublic"] is True
    assert entry.collection_json["canWrite"] is False
    assert entry.schema_json["pk"] == "id"

    parquet_path = (
        tmp_path
        / "snapshot"
        / f"tenant_id={tenant.id}"
        / f"collection_id={col.id}"
        / "dt=snapshot"
        / "data.parquet"
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
    s.execute(
        text(
            "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
        )
    )
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_snapshot_x",
        title="X",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    s.commit()

    config = _app_config(
        [
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
        ]
    )
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert entries[0].collection_json["featureCount"] == 0
    parquet_dir = tmp_path / "snapshot" / f"tenant_id={tenant.id}" / f"collection_id={col.id}"
    assert not parquet_dir.exists()


def test_same_collection_referenced_twice_is_written_once(pg_session, tmp_path):
    s = pg_session
    s.execute(
        text(
            "CREATE TABLE t_snapshot_x (id serial PRIMARY KEY, tenant_id text NOT NULL, name text)"
        )
    )
    s.commit()
    apply_collection_ddl(s, "t_snapshot_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s,
        tenant_id=tenant.id,
        owner_id=owner.id,
        table_name="t_snapshot_x",
        title="X",
        description="",
        is_public=True,
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
    )
    s.commit()

    config = _app_config(
        [
            DataSource(id="s1", type="features", service="core", layer=col.id, query={}),
            DataSource(id="s2", type="statistics", service="core", layer=col.id, query={}),
        ]
    )
    entries = write_snapshot(s, tenant_id=tenant.id, config=config, snapshot_dir=str(tmp_path))

    assert len(entries) == 1

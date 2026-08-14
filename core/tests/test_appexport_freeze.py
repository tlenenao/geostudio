# SPDX-License-Identifier: Apache-2.0
"""freeze_config (SP-18a Task 5) — mêmes contraintes PostGIS-réelles que
test_mcp_tools_query_features.py/test_features_repository.py :
introspect_table/insert_feature/select_features touchent pg_class/
pg_namespace/geometry_columns (introspection_pg.py) et RLS Postgres réelle
(policy USING current_setting('app.tenant_id')) — ni portable SQLite, ni
simulable sans une vraie base. @pytest.mark.postgis seul ne route jamais
vers Postgres dans ce dépôt : le skip vient uniquement de la fixture
pg_engine (cf. le même piège documenté dans test_mcp_tools_query_features.py)."""
import pytest
from sqlalchemy import text

import app.main  # noqa: F401 — import-only, registers every model (incl.
# app.items.models's Item, FK target of item_shares.item_id) on
# Base.metadata before create_all(); mirrors test_features_integration.py's
# pg_app fixture. Without it, Base.metadata.create_all() raises
# NoReferencedTableError when this module runs standalone (item_shares'
# FK to items.id unresolved) — reproduced empirically.
from app.appexport.freeze import freeze_config
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


# Même patron que test_collections_repository.py's `pg_session` : les
# tables app-level (tenants/users/collections/...) sont créées via
# Base.metadata.create_all() (jamais alembic upgrade head en test), pas la
# table physique de la collection elle-même (RLS Postgres réelle) — celle-ci
# est du DDL brut + apply_collection_ddl, comme
# test_mcp_tools_query_features.py's _register_incidents_collection.
@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_freeze_x"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, items, "
            "users, tenants CASCADE"
        ))


def _app_config(data_sources) -> BuilderConfig:
    # BuilderConfig._require_kind_payload (app/configs/schemas.py) requires
    # a top-level `layout` for kind="app" — distinct from each Page's own
    # `layout` — the brief's draft omitted it (schema has grown a
    # validator since the plan was written).
    return BuilderConfig(
        kind="app", dataSources=data_sources,
        layout=Layout(type="grid", items=[]),
        pages=[Page(id="p1", name="Page 1", layout=Layout(
            type="grid", items=[LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2)],
        ))],
    )


def test_static_source_passes_through_unchanged(pg_session):
    config = _app_config([
        DataSource(id="s1", type="static", service="core", layer="", query={"records": [{"id": 1}]}),
    ])
    frozen = freeze_config(pg_session, tenant_id="t1", config=config)
    assert frozen.dataSources[0].type == "static"
    assert frozen.dataSources[0].query["records"] == [{"id": 1}]


def test_features_source_is_frozen_into_static_records(pg_session):
    s = pg_session
    s.execute(text(
        "CREATE TABLE t_freeze_x (id serial PRIMARY KEY, tenant_id text NOT NULL, "
        "name text)"
    ))
    s.commit()
    apply_collection_ddl(s, "t_freeze_x")

    tenant = get_or_create_default_tenant(s)
    owner = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="", bootstrap_admin=False,
    )
    s.commit()
    col = create_collection(
        s, tenant_id=tenant.id, owner_id=owner.id, table_name="t_freeze_x",
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
    frozen = freeze_config(s, tenant_id=tenant.id, config=config)

    out = frozen.dataSources[0]
    assert out.type == "static"
    names = sorted(r["properties"]["name"] for r in out.query["records"])
    assert names == ["Alpha", "Beta"]


def test_config_shape_is_otherwise_unchanged(pg_session):
    config = _app_config([])
    frozen = freeze_config(pg_session, tenant_id="t1", config=config)
    assert frozen.pages[0].id == "p1"
    assert frozen.kind == "app"

# SPDX-License-Identifier: Apache-2.0
"""Tests de POST /analytics/sql (SP-11c, Task 9) — mêmes fixtures/montage que
test_features_aggregate_routes.py (engine SQLite, introspector fake, factory
DuckDB spatial-only, base_uri = tmp_path), avec en plus un utilisateur
analyste (bootstrap_analyst=True) et, pour un des tests, une collection
privée non partagée à l'analyste."""

import duckdb
import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


def fake_introspector(session, table_name):
    if table_name != "villes":
        raise TableNotFound(table_name)
    return INFO


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _build_env(tmp_path, *, with_analyst=False):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        analyst = None
        if with_analyst:
            analyst = get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub="an",
                username="analyst",
                email=None,
                first_name="",
                last_name="",
                bootstrap_analyst=True,
            )
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table: None
    )

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        fake_duckdb_factory
    )
    monkeypatch_base_uri = str(tmp_path)
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: monkeypatch_base_uri

    client = TestClient(app)
    return app, client, admin, regular, analyst, tmp_path, tenant_id, Session


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    return client.post("/collections", json={"tableName": "villes", "isPublic": public}).json()


@pytest.fixture()
def env(tmp_path):
    app, client, admin, regular, _analyst, tmp_path, tenant_id, Session = _build_env(tmp_path)
    return app, client, admin, regular, tmp_path, tenant_id, Session


@pytest.fixture()
def env_with_analyst(tmp_path):
    app, client, admin, _regular, analyst, tmp_path, tenant_id, Session = _build_env(
        tmp_path, with_analyst=True
    )
    col = _register(app, client, admin, public=True)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
            {
                "id": 2,
                "region": "Sud",
                "pop": 5,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1, 1),
            },
        ],
    )
    return app, client, analyst, tmp_path, tenant_id, col, Session


@pytest.fixture()
def env_with_analyst_and_private(tmp_path):
    app, client, admin, _regular, analyst, tmp_path, tenant_id, Session = _build_env(
        tmp_path, with_analyst=True
    )
    private_col = _register(app, client, admin, public=False)
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=private_col["id"],
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
        ],
    )
    return app, client, analyst, private_col, Session


def test_non_analyst_gets_403(env):
    app, client, _admin, regular, _tmp, _tid, _Session = env
    _as(app, regular)  # regular : ni admin ni analyste
    resp = client.post("/analytics/sql", json={"sql": "SELECT 1"})
    assert resp.status_code == 403


def test_admin_can_access_sql_lab(env):
    # Le rôle admin porte tous les privilèges (Tâche 1, BUILT_IN_ROLE_PRIVILEGES) —
    # l'ancienne orthogonalité is_admin/is_analyst n'existe plus : un admin
    # accède à SQL Lab sans devoir être en plus analyste.
    app, client, admin, _r, _tmp, _tid, _Session = env
    _as(app, admin)
    resp = client.post("/analytics/sql", json={"sql": "SELECT 1"})
    assert resp.status_code == 200


def test_analyst_queries_readable_view(env_with_analyst):
    app, client, analyst, tmp_path, tenant_id, col, Session = env_with_analyst
    _as(app, analyst)
    resp = client.post(
        "/analytics/sql",
        json={
            "sql": (
                f"SELECT region, sum(pop) AS total FROM {col['id']} GROUP BY region ORDER BY region"
            )
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["region", "total"]
    assert body["truncated"] is False
    assert body["rows"] == [["Nord", 10], ["Sud", 5]]
    with Session() as s:
        log = s.execute(select(AuditLog).where(AuditLog.action == "analytics.sql")).scalar_one()
        assert log.payload["outcome"] == "success"


def test_analyst_cannot_reach_unauthorized_collection(env_with_analyst_and_private):
    # Une collection privée non partagée à l'analyste n'est pas dans list_visible_collections
    # → non matérialisée → "table introuvable" → 400 (jamais de fuite).
    app, client, analyst, private_col, _Session = env_with_analyst_and_private
    _as(app, analyst)
    resp = client.post("/analytics/sql", json={"sql": f"SELECT * FROM {private_col['id']}"})
    assert resp.status_code == 400


def test_custom_role_with_collections_manage_reaches_private_collection(
    env_with_analyst_and_private,
):
    # Un rôle sur mesure porteur d'analytics.sql_lab.access ET
    # admin.collections.manage doit matérialiser une collection privée
    # non partagée dans SQL Lab (can_see_all=True), au même titre que
    # list_visible_collections ailleurs (SP-35).
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.repository import set_user_role

    app, client, analyst, private_col, Session = env_with_analyst_and_private

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Analyste + collections",
            privileges=[
                Privilege.ANALYTICS_SQL_LAB_ACCESS.value,
                Privilege.ADMIN_COLLECTIONS_MANAGE.value,
            ],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=analyst.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        analyst_id = analyst.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, analyst_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)

        resp = client.post("/analytics/sql", json={"sql": f"SELECT * FROM {private_col['id']}"})
        assert resp.status_code == 200


def test_invalid_sql_returns_400(env_with_analyst):
    app, client, analyst, *rest = env_with_analyst
    _as(app, analyst)
    resp = client.post("/analytics/sql", json={"sql": "DROP TABLE villes"})
    assert resp.status_code == 400


def test_rejected_sql_attempt_is_audited(env_with_analyst):
    app, client, analyst, tmp_path, tenant_id, col, Session = env_with_analyst
    _as(app, analyst)
    resp = client.post("/analytics/sql", json={"sql": "DROP TABLE villes"})
    assert resp.status_code == 400

    # Le trail doit persister malgré le rollback de request_scoped_session sur
    # l'exception 400 re-levée : preuve qu'une nouvelle session voit bien la ligne.
    with Session() as s:
        log = s.execute(select(AuditLog).where(AuditLog.action == "analytics.sql")).scalar_one()
        assert log.actor_id == analyst.id
        assert log.tenant_id == tenant_id
        assert log.payload["outcome"] == "error"
        assert "DROP TABLE villes" in log.payload["sql"]

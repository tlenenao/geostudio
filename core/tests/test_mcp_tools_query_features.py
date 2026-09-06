# SPDX-License-Identifier: Apache-2.0
"""query_features (SP-7 Task 9) — mince adaptateur MCP au-dessus de
select_features, même permissions que GET /collections/{id}/items.

app_client ici est PostGIS-réel (contrairement à celui de
test_mcp_tools_create.py, qui est SQLite) : apply_collection_ddl et les
fonctions ST_* utilisées par _register_incidents_collection ci-dessous sont
du SQL PostgreSQL/PostGIS pur, pas dialecte-agnostique — @pytest.mark.postgis
seul ne route jamais vers Postgres dans ce dépôt, le skip vient uniquement de
la fixture pg_engine (cf. progress.md Task 6, même piège déjà rencontré et
corrigé)."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401

pytestmark = pytest.mark.postgis


@pytest.fixture()
def app_client(monkeypatch, pg_engine):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    # create_app() builds its own engine from DATABASE_URL and the MCP tools
    # close over *that* session_factory (see test_mcp_tools_create.py's
    # app_client for the same rationale) — route it at the real Postgres
    # test database rather than an on-disk SQLite file, since this test
    # needs apply_collection_ddl + PostGIS geometry functions.
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        # CORE_AUTH_MODE=mock always resolves this exact identity (see
        # app/auth/dependency.py's mock branch and MockTokenVerifier).
        mock_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        setup_session.commit()

    app = create_app()
    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.mock_user = mock_user  # type: ignore[attr-defined]
    yield test_client
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS incidents"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, audit_log, items, users, tenants CASCADE"
            )
        )


def _register_incidents_collection(app_client):
    with app_client.session_factory() as session:
        from sqlalchemy import text

        from app.collections import repository as collections_repo
        from app.collections.ddl import apply_collection_ddl

        session.execute(
            text(
                "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "titre text, geom geometry(Point, 4326))"
            )
        )
        session.commit()
        apply_collection_ddl(session, "incidents")
        col = collections_repo.create_collection(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.execute(
            text(
                "INSERT INTO incidents (tenant_id, titre, geom) VALUES "
                "(:tid, 'Nid de poule', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
            ),
            {"tid": app_client.tenant.id},
        )
        session.commit()
        return col.id


def test_query_features_returns_geojson_for_a_readable_collection(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        result = call_tool(app_client, "query_features", {"collectionId": collection_id})

    assert result["type"] == "FeatureCollection"
    assert result["numberReturned"] == 1
    assert result["features"][0]["properties"]["titre"] == "Nid de poule"


def test_query_features_relays_geom_intersects(app_client):
    """GAP-47 (reste) : select_features() supporte déjà l'intersection
    géométrique, et la route REST équivalente la relaie déjà — query_features
    (MCP) ne proposait qu'un bbox grossier avant ce correctif."""
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        # Le point inséré par _register_incidents_collection est (2.3, 48.8) —
        # intersection exacte avec ce même point.
        result = call_tool(
            app_client,
            "query_features",
            {
                "collectionId": collection_id,
                "geomIntersects": {"type": "Point", "coordinates": [2.3, 48.8]},
            },
        )
    assert result["numberReturned"] == 1
    assert result["features"][0]["properties"]["titre"] == "Nid de poule"


def test_query_features_geom_intersects_excludes_non_matching(app_client):
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        # Un point loin de (2.3, 48.8) ne doit rien retourner.
        result = call_tool(
            app_client,
            "query_features",
            {
                "collectionId": collection_id,
                "geomIntersects": {"type": "Point", "coordinates": [-70.0, 10.0]},
            },
        )
    assert result["numberReturned"] == 0


def test_query_features_unknown_collection_errors(app_client):
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "query_features", {"collectionId": "nope"}
        )
    assert "not found" in error_text


def _register_private_incidents_collection_owned_by_other(app_client):
    """Same backing table as _register_incidents_collection, but private
    (is_public=False) and owned by a different user, with no share granting
    app_client.mock_user any access — the denial path query_features never
    exercised before this review (every existing test here reads a public
    collection)."""
    with app_client.session_factory() as session:
        from app.collections import repository as collections_repo
        from app.collections.ddl import apply_collection_ddl

        tenant = get_or_create_default_tenant(session)
        other_owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="other-owner-qf-sub",
            username="otherowner-qf",
            email=None,
            first_name="Other",
            last_name="Owner",
        )
        session.execute(
            text(
                "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "titre text, geom geometry(Point, 4326))"
            )
        )
        session.commit()
        apply_collection_ddl(session, "incidents")
        col = collections_repo.create_collection(
            session,
            tenant_id=tenant.id,
            owner_id=other_owner.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=False,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.commit()
        return col.id


def test_query_features_on_private_unshared_collection_errors(app_client):
    with app_client:
        collection_id = _register_private_incidents_collection_owned_by_other(app_client)
        error_text = call_tool_expecting_error(
            app_client,
            "query_features",
            {"collectionId": collection_id},
        )
    assert "not found" in error_text


def test_query_features_sees_a_private_collection_via_admin_collections_manage(app_client):
    # SP-42/F-coeur-federation-05 : _require_collection_read se prétendait
    # miroir de get_readable_collection (app/collections/routes.py) mais
    # n'appliquait jamais l'extension can_manage_collections (privilège
    # admin.collections.manage, SP-35) — un rôle sur mesure porteur de ce
    # seul privilège voit et gère la collection via REST (200) mais
    # obtenait "collection not found" via tout outil MCP passant par
    # _require_collection_read.
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    with app_client:
        collection_id = _register_private_incidents_collection_owned_by_other(app_client)

        with app_client.session_factory() as session:
            custom_role = create_role(
                session,
                tenant_id=app_client.tenant.id,
                name="Gestionnaire de collections",
                privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
            )
            set_user_role(
                session,
                tenant_id=app_client.tenant.id,
                user_id=app_client.mock_user.id,
                role_id=custom_role.id,
                role_slug=custom_role.slug,
            )
            session.commit()

        result = call_tool(app_client, "query_features", {"collectionId": collection_id})
    assert result["type"] == "FeatureCollection"

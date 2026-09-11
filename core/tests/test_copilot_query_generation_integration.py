# SPDX-License-Identifier: Apache-2.0
"""Preuve bout-en-bout (spec GAP-17 §3, critères 1-3) : un tour de
copilote qui appelle generate_sql_query puis applySqlDraft ne modifie
jamais la base ni n'exécute le SQL ; le SQL généré, une fois soumis
séparément par l'utilisateur via POST /v1/analytics/sql, traverse
exactement le même run_analyst_sql que le SQL manuel.

Fixture calquée sur tests/test_mcp_tools_query_features.py::app_client
(même patron `_register_incidents_collection` : postgis réel, DROP TABLE
IF EXISTS incidents + TRUNCATE ... CASCADE en teardown pour rester
rejouable sur le conteneur pg_engine partagé, session-scope) et sur
tests/test_copilot_routes.py::_make_copilot_app (McpLoopbackSession
réinjectée via ASGITransport, TestClient en context manager pour que le
lifespan MCP démarre réellement)."""

import os

import duckdb
import geopandas as gpd
import httpx
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point
from sqlalchemy import text

from app import db
from app.copilot.llm_provider import FakeLLMProvider, LLMTurn, ToolCall
from app.db import Base, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role

pytestmark = pytest.mark.postgis


def _fake_duckdb_factory():
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-09-06"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geom", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(monkeypatch, pg_engine, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_LLM_PROVIDER", "fake")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        mock_user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        role = create_role(
            s,
            tenant_id=tenant.id,
            name="Analyste SQL",
            privileges=[Privilege.ANALYTICS_SQL_LAB_ACCESS.value],
        )
        set_user_role(
            s, tenant_id=tenant.id, user_id=mock_user.id, role_id=role.id, role_slug=role.slug
        )

        from app.collections import repository as collections_repo
        from app.collections.ddl import apply_collection_ddl

        s.execute(
            text(
                "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "titre text, geom geometry(Point, 4326))"
            )
        )
        s.commit()
        apply_collection_ddl(s, "incidents")
        col = collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=mock_user.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            # NOTE (discrepancy vs. the brief's literal fixture code):
            # create_collection() has no defaults for geometry_type/srid
            # (app/collections/repository.py) — omitting them raised
            # TypeError: create_collection() missing 2 required keyword-only
            # arguments at fixture setup, before the behaviour under test
            # ever ran. Added, matching the exact values used by the
            # established real-postgres helper this fixture is modelled on
            # (tests/test_mcp_tools_query_features.py::_register_incidents_collection).
            geometry_type="Point",
            srid=4326,
        )
        s.commit()
        collection_id = col.id
        tenant_id = tenant.id

    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=collection_id,
        rows=[
            {
                "id": 1,
                "tenant_id": tenant_id,
                "titre": "Nid de poule",
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geom": Point(2.3, 48.8),
            }
        ],
    )

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    # get_duckdb_connection_factory/get_analytics_base_uri are captured by
    # value inside features_routes.analytics_sql's own `Depends(...)`
    # default arguments at module-import time — monkeypatch.setattr on the
    # module attribute (the pattern used for the MCP-tool direct-call path
    # in test_mcp_tools_run_analytics_query.py) does NOT affect an
    # already-resolved FastAPI dependency. The REST route needs the real
    # override mechanism instead (same pattern as
    # test_analytics_sql_routes.py's env fixture).
    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: (
        _fake_duckdb_factory
    )
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)

    import app.copilot.routes as routes_module

    real_mcp_loopback_session = routes_module.McpLoopbackSession

    def _loopback_session_via_asgi(mcp_token):
        http_client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://localhost:8200"
        )
        return real_mcp_loopback_session(mcp_token, http_client=http_client)

    monkeypatch.setattr(routes_module, "McpLoopbackSession", _loopback_session_via_asgi)

    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = "Bearer mock:alice"
        yield test_client, collection_id

    # Same cleanup as _register_incidents_collection's caller
    # (test_mcp_tools_query_features.py::app_client): pg_engine is
    # session-scoped and shared across the whole test file/session, and
    # "incidents" is a fixed, un-namespaced table name used by several
    # other real-postgres test files — leaving it (and this fixture's rows
    # in shared tables) behind breaks later tests with DuplicateTable/
    # UniqueViolation, unrelated to whatever they're testing (cf. CLAUDE.md
    # "Suivis non bloquants" — this exact class of contamination has been
    # hit and fixed by several prior SPs).
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS incidents"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, audit_log, items, users, tenants CASCADE"
            )
        )


def test_generated_sql_is_never_auto_executed_but_round_trips_through_the_same_sandbox(
    env, monkeypatch
):
    test_client, collection_id = env
    generated_sql = f'SELECT titre FROM "{collection_id}"'

    # Outer turn loop (the LLM that decides which tool to call):
    # 1st call -> asks for generate_sql_query ; 2nd call -> asks for
    # applySqlDraft with the tool's result ; never a 3rd call needed since
    # applySqlDraft is a client op that ends the turn.
    monkeypatch.setattr(
        "app.copilot.routes.get_llm_provider",
        lambda: FakeLLMProvider(
            responses=[
                LLMTurn(
                    text="",
                    tool_calls=[
                        ToolCall(
                            id="1",
                            name="generate_sql_query",
                            arguments={"collectionId": collection_id, "question": "les titres"},
                        )
                    ],
                ),
                LLMTurn(
                    text="Voici un brouillon.",
                    tool_calls=[
                        ToolCall(id="2", name="applySqlDraft", arguments={"sql": generated_sql})
                    ],
                ),
            ]
        ),
    )
    # Inner call made by generate_sql_query's own body:
    monkeypatch.setattr(
        "app.mcp.tools.query_generation.get_llm_provider",
        lambda: FakeLLMProvider(responses=[LLMTurn(text=generated_sql)]),
    )

    response = test_client.post(
        "/v1/copilot/turn",
        json={
            "message": "écris une requête sur les titres",
            "history": [],
            "mcpToken": "anything",
            "currentConfig": {"sql": ""},
            "clientTools": [
                {
                    "name": "applySqlDraft",
                    "description": "insert a SQL draft",
                    "inputSchema": {"type": "object", "properties": {"sql": {"type": "string"}}},
                }
            ],
            "surface": "sql_lab",
        },
    )
    assert response.status_code == 200
    body = response.json()
    # Critère #3 : jamais de résultat de requête exécutée dans la réponse —
    # uniquement un ClientOp, jamais exécuté côté serveur.
    assert body["clientOps"] == [{"op": "applySqlDraft", "args": {"sql": generated_sql}}]

    # Critère #2 : le même SQL, soumis séparément par l'utilisateur, traverse
    # exactement POST /v1/analytics/sql -> run_analyst_sql — aucun nouveau
    # chemin d'exécution.
    exec_response = test_client.post("/v1/analytics/sql", json={"sql": generated_sql})
    assert exec_response.status_code == 200
    assert exec_response.json()["rows"] == [["Nid de poule"]]

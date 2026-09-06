# SPDX-License-Identifier: Apache-2.0
"""Preuve que le point de calcul unique de l'emprise spatiale (SP-55 §2.3,
GAP-06 : recompute_item_bbox, appelé DEPUIS app.configs.repository.update_config)
fonctionne aussi bien via l'outil MCP save_app_config qu'via la route REST —
sans jamais appeler PUT /configs/by-item/{id}. C'est le test qui protège
contre la classe de bug documentée dans CLAUDE.md (« déjà rouvert trois
fois » : REST -> MCP -> terrain3d/tileset3d) : si le câblage était fait au
mauvais endroit (le handler de route plutôt que la fonction de bas niveau),
ce test échouerait alors que test_configs_bbox.py (qui appelle
configs_repo.update_config directement) resterait vert."""

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.collections.models import Collection
from app.configs import repository as configs_repo
from app.configs.schemas import BaseMap, BuilderConfig, MapConfig, MapLayer, MapView
from app.db import Base, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

# Dérivé de CORE_TEST_DATABASE_URL, jamais codé en dur : c'était un littéral
# `postgresql://gis:gis@127.0.0.1:5433/gis_test` — le port 5433 est la
# convention d'un poste de développement, pas celle de la CI (5432). Le test
# passait donc en local et échouait en CI sur « connection refused », alors
# que le commentaire ci-dessous affirmait déjà pointer vers le même
# postgis-test que `pg_engine`. `pg_engine` skippe déjà proprement quand la
# variable est absente, donc la lire ici ne peut pas faire échouer un
# environnement sans PostGIS.
_PG_URL = os.environ.get("CORE_TEST_DATABASE_URL", "")


@pytest.fixture()
def app_client(monkeypatch, pg_engine):
    # Contrairement à test_mcp_tools_configs.py (SQLite jetable) : ce test a
    # besoin d'un vrai PostGIS pour recompute_item_bbox (ST_Extent via
    # app.collections.extent.table_extent). create_app() construit son
    # propre moteur depuis DATABASE_URL (app/main.py) — pointé ici vers le
    # même postgis-test que pg_engine (CORE_TEST_DATABASE_URL).
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    monkeypatch.setenv("DATABASE_URL", _PG_URL)
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)

    with Session() as s:
        conn = s.connection()
        conn.execute(text("DROP TABLE IF EXISTS t_mcp_bbox_a"))
        conn.execute(
            text(
                "CREATE TABLE t_mcp_bbox_a (id serial PRIMARY KEY, nom text, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_mcp_bbox_a (nom, geom) VALUES "
                "('A', ST_SetSRID(ST_MakePoint(1.0, 45.0), 4326))"
            )
        )
        conn.execute(text("DROP TABLE IF EXISTS t_mcp_bbox_b"))
        conn.execute(
            text(
                "CREATE TABLE t_mcp_bbox_b (id serial PRIMARY KEY, nom text, "
                "tenant_id text NOT NULL DEFAULT 'default', geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_mcp_bbox_b (nom, geom) VALUES "
                "('B', ST_SetSRID(ST_MakePoint(20.0, 60.0), 4326))"
            )
        )
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
        s.add_all(
            [
                Collection(
                    id="t_mcp_bbox_a",
                    tenant_id=tenant.id,
                    owner_id=mock_user.id,
                    table_name="t_mcp_bbox_a",
                    title="A",
                    pk_column="id",
                    geometry_column="geom",
                    geometry_type="Point",
                    srid=4326,
                ),
                Collection(
                    id="t_mcp_bbox_b",
                    tenant_id=tenant.id,
                    owner_id=mock_user.id,
                    table_name="t_mcp_bbox_b",
                    title="B",
                    pk_column="id",
                    geometry_column="geom",
                    geometry_type="Point",
                    srid=4326,
                ),
            ]
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    test_client = TestClient(app, base_url="http://localhost:8200")
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.mock_user = mock_user  # type: ignore[attr-defined]
    yield test_client
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_mcp_bbox_a, t_mcp_bbox_b"))
        conn.execute(
            text("TRUNCATE items, configs, config_revisions, collections, users, tenants CASCADE")
        )


def call_tool(test_client, name: str, arguments: dict) -> dict:
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer anything",
    }
    init_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        },
        headers=headers,
    )
    assert init_response.status_code == 200
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}

    notify_response = test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers,
    )
    assert notify_response.status_code == 202

    call_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=session_headers,
    )
    assert call_response.status_code == 200
    body_line = next(line for line in call_response.text.splitlines() if line.startswith("data: "))
    payload = json.loads(body_line.removeprefix("data: "))
    result = payload["result"]
    if result.get("isError"):
        raise AssertionError(f"tool {name} errored: {result['content'][0]['text']}")
    return json.loads(result["content"][0]["text"])


def _map_config(collection_id: str) -> dict:
    return BuilderConfig(
        kind="map",
        map=MapConfig(
            basemap=BaseMap(style="https://demotiles.maplibre.org/style.json"),
            view=MapView(center=[0, 0], zoom=1),
            layers=[
                MapLayer(
                    id="l1",
                    title="Layer",
                    visible=True,
                    kind="feature",
                    collectionId=collection_id,
                    url=f"https://core.test/collections/{collection_id}/items",
                )
            ],
        ),
    ).model_dump(by_alias=True)


def test_save_app_config_via_mcp_recomputes_item_bbox_without_http_route(app_client):
    # Config initiale (kind=map, couche -> t_mcp_bbox_a) créée directement en
    # base, jamais via une route HTTP — seul l'outil MCP save_app_config, ci-
    # dessous, écrit après ce seed.
    with app_client.session_factory() as session:
        item = items_repo.create_item(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="map",
            title="Carte MCP",
        )
        session.flush()
        configs_repo.create_config(
            session,
            BuilderConfig.model_validate(_map_config("t_mcp_bbox_a")),
            item_id=item.id,
            tenant_id=app_client.tenant.id,
        )
        session.commit()
        item_id = item.id

    with app_client:
        result = call_tool(
            app_client,
            "save_app_config",
            {"itemId": item_id, "config": _map_config("t_mcp_bbox_b")},
        )
    assert result["config"]["map"]["layers"][0]["collectionId"] == "t_mcp_bbox_b"

    with app_client.session_factory() as session:
        from app.items.models import Item

        refreshed = session.get(Item, item_id)
        assert [
            refreshed.bbox_min_x,
            refreshed.bbox_min_y,
            refreshed.bbox_max_x,
            refreshed.bbox_max_y,
        ] == [20.0, 60.0, 20.0, 60.0]

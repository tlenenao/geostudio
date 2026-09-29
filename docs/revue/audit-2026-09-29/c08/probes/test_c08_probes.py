# SPDX-License-Identifier: Apache-2.0
"""Sondes de l'audit c08 (lecture seule sur le code : ce fichier n'importe que des
fixtures existantes). Rejeu :
cd core && PYTHONPATH=. uv run pytest -c pyproject.toml --rootdir . \
  ../docs/revue/audit-2026-09-29/c08/probes/test_c08_probes.py -p no:cacheprovider -q
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
    call_tool_raw,
)


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "test-share-link-routes-secret-padding-0")


def test_revoke_share_link_of_another_item(monkeypatch):
    """c08-001 : un utilisateur qui ne partage QUE l'item B révoque le lien de l'item A."""
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        alice = get_or_create_user(s, tenant_id=t.id, oidc_sub="a", username="alice", email=None, first_name="", last_name="")
        bob = get_or_create_user(s, tenant_id=t.id, oidc_sub="b", username="bob", email=None, first_name="", last_name="")
        item_a = items_repo.create_item(s, tenant_id=t.id, owner_id=alice.id, resource_type="app", title="A")
        item_b = items_repo.create_item(s, tenant_id=t.id, owner_id=bob.id, resource_type="app", title="B")
        s.commit()
        a_id, b_id = item_a.id, item_b.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    current = {"u": alice}
    app.dependency_overrides[get_current_user] = lambda: current["u"]
    c = TestClient(app)
    created = c.post(f"/v1/items/{a_id}/share-links", json={"ttlDays": 7}).json()
    link_id = c.get(f"/v1/items/{a_id}/share-links").json()[0]["id"]
    assert c.get(f"/v1/share-links/{created['token']}").status_code == 200
    current["u"] = bob
    # bob n'a aucun droit sur A
    assert c.get(f"/v1/items/{a_id}/share-links").status_code == 404
    r = c.delete(f"/v1/items/{b_id}/share-links/{link_id}")  # item B, lien de A
    assert r.status_code == 204, r.status_code
    current["u"] = alice
    assert c.get(f"/v1/share-links/{created['token']}").status_code == 401  # lien de A révoqué par bob
    engine.dispose()


def test_mcp_pagination_not_bounded_like_rest(app_client):  # noqa: F811
    """c08-003 : REST refuse page=0 (422), MCP l'accepte et produit un offset négatif."""
    with app_client:
        r = app_client.get("/v1/items?page=0", headers={"Authorization": "Bearer x"})
        print("REST page=0 ->", r.status_code)
        assert r.status_code == 422
        raw = call_tool_raw(app_client, "list_items", {"page": 0})
        print("MCP list_items page=0 -> isError=", raw.get("isError"), str(raw.get("content"))[:120])
        raw2 = call_tool_raw(app_client, "list_items", {"page": 1, "pageSize": 0})
        print("MCP list_items pageSize=0 -> isError=", raw2.get("isError"), str(raw2.get("content"))[:120])
        raw3 = call_tool_raw(app_client, "search_collections", {"page": -3})
        print("MCP search_collections page=-3 -> isError=", raw3.get("isError"), str(raw3.get("content"))[:120])
        raw4 = call_tool_raw(app_client, "query_features", {"collectionId": "x", "limit": -1})
        print("MCP query_features limit=-1 ->", raw4.get("isError"), str(raw4.get("content"))[:120])


def test_mcp_and_rest_accept_unknown_widget_and_drop_typos(app_client):  # noqa: F811
    """c08-002 : le schéma serveur laisse passer widget inconnu / clés inconnues."""
    cfg = {
        "kind": "app",
        "layout": {"type": "grid", "items": [{"widget": "nonexistent-widget", "x": 0, "y": 0, "w": 2, "h": 2,
                                                  "props": {"zzz": 1}, "visibleWhen": "((( not cel"}]},
        "bogusTopLevel": 1,
    }
    with app_client:
        item = call_tool(app_client, "create_item", {"kind": "app", "title": "t", "config": cfg})
        got = call_tool(app_client, "get_app_config", {"itemId": item["pk"] if "pk" in item else item["id"]})
        print("stored:", got["config"]["layout"]["items"][0], "bogusTopLevel" in got["config"])
        assert got["config"]["layout"]["items"][0]["widget"] == "nonexistent-widget"
        assert "bogusTopLevel" not in got["config"]

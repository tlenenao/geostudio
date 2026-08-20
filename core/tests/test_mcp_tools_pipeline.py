# SPDX-License-Identifier: Apache-2.0
import json

import pytest
from fastapi.testclient import TestClient

from app import db
from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, PipelinePayload
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    # CORE_ETL_ENABLED est lu par create_app()/register_tools() à la
    # construction (pas par requête) — les appelants doivent le positionner
    # via monkeypatch.setenv AVANT que cette fixture construise l'app.
    # D'où une fixture-fabrique plutôt qu'un TestClient figé.
    def _build(etl_enabled: bool):
        monkeypatch.setenv("CORE_ETL_ENABLED", "true" if etl_enabled else "false")
        engine = make_engine(db_url)
        init_db(engine)
        Session = make_session_factory(engine)
        with Session() as setup_session:
            tenant = get_or_create_default_tenant(setup_session)
            # CORE_AUTH_MODE=mock résout toujours cette identité fixe (cf.
            # app/auth/dependency.py branche mock et MockTokenVerifier) — un
            # "second utilisateur" ne peut donc être simulé qu'en semant des
            # lignes appartenant à un autre owner_id directement en base
            # (même idiome que test_mcp_tools_sharing.py::_stranger).
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

        def override_session():
            with request_scoped_session(Session) as session:
                yield session

        app.dependency_overrides[db.get_session] = override_session
        test_client = TestClient(app, base_url="http://localhost:8200")
        test_client.session_factory = Session  # type: ignore[attr-defined]
        test_client.tenant = tenant  # type: ignore[attr-defined]
        test_client.mock_user = mock_user  # type: ignore[attr-defined]
        return test_client

    return _build


def _init_and_list_tools(test_client) -> set[str]:
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
    session_id = init_response.headers["mcp-session-id"]
    session_headers = {**headers, "mcp-session-id": session_id}
    test_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=session_headers,
    )
    list_response = test_client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        headers=session_headers,
    )
    body_line = next(line for line in list_response.text.splitlines() if line.startswith("data: "))
    payload = json.loads(body_line.removeprefix("data: "))
    return {tool["name"] for tool in payload["result"]["tools"]}


def test_pipeline_tools_absent_when_etl_disabled(app_client):
    client = app_client(etl_enabled=False)
    with client:
        names = _init_and_list_tools(client)
    assert "create_pipeline" not in names
    assert "run_pipeline" not in names
    assert "explain_pipeline" not in names


def test_pipeline_tools_present_when_etl_enabled(app_client):
    client = app_client(etl_enabled=True)
    with client:
        names = _init_and_list_tools(client)
    assert {"create_pipeline", "run_pipeline", "explain_pipeline"} <= names


def _register_collections(test_client, *, owner=None):
    """Sème une collection lisible (source) et une collection inscriptible
    (cible), toutes deux détenues par `owner` (par défaut mock_user) — le
    minimum pour que le validateur réel reader.collection/writer.collection
    (app.pipelines.config_validation, importé par app.main) laisse passer
    un pipeline linéaire à deux nœuds."""
    owner_user = owner or test_client.mock_user
    with test_client.session_factory() as session:
        source = collections_repo.create_collection(
            session,
            tenant_id=test_client.tenant.id,
            owner_id=owner_user.id,
            table_name="villes",
            title="Villes",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        target = collections_repo.create_collection(
            session,
            tenant_id=test_client.tenant.id,
            owner_id=owner_user.id,
            table_name="villes_propres",
            title="Villes propres",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.commit()
        return source.id, target.id


def _linear_pipeline_args(source_id: str, target_id: str) -> dict:
    return {
        "title": "Pipeline villes",
        "nodes": [
            {
                "id": "r1",
                "kind": "reader",
                "op": "reader.collection",
                "params": {"collectionId": source_id},
            },
            {
                "id": "w1",
                "kind": "writer",
                "op": "writer.collection",
                "params": {"collectionId": target_id},
            },
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    }


def test_explain_pipeline_by_owner_succeeds(app_client):
    client = app_client(etl_enabled=True)
    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))
        result = call_tool(client, "explain_pipeline", {"pipelineId": created["pk"]})

    assert result["title"] == "Pipeline villes"
    node_ids = {n["id"] for n in result["nodes"]}
    assert node_ids == {"r1", "w1"}
    assert result["edges"] == [{"from": "r1", "to": "w1"}]


def test_explain_pipeline_invisible_to_a_stranger_errors(app_client):
    # Mirrors test_get_sharing_invisible_to_a_stranger_errors
    # (test_mcp_tools_sharing.py) — CORE_AUTH_MODE=mock always resolves the
    # same fixed caller identity, so "a user with no access" is seeded by
    # owning the item/config as a distinct DB row rather than by
    # authenticating as someone else. Regression for the reviewer finding:
    # explain_pipeline used to return the full graph to ANY caller in the
    # tenant, with no read-access check at all (fixed alongside run_pipeline's
    # sibling check).
    client = app_client(etl_enabled=True)
    with client.session_factory() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=client.tenant.id,
            oidc_sub="sub-stranger",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        session.flush()
        item = items_repo.create_item(
            session,
            tenant_id=client.tenant.id,
            owner_id=stranger.id,
            resource_type="pipeline",
            title="Not mine",
        )
        config = BuilderConfig(
            version=1,
            kind="pipeline",
            pipeline=PipelinePayload(
                nodes=[
                    {
                        "id": "r1",
                        "kind": "reader",
                        "op": "reader.collection",
                        "params": {"collectionId": "villes"},
                    },
                    {
                        "id": "w1",
                        "kind": "writer",
                        "op": "writer.collection",
                        "params": {"collectionId": "villes_propres"},
                    },
                ],
                edges=[{"id": "e1", "from": "r1", "to": "w1"}],
            ),
        )
        configs_repo.create_config(session, config, item_id=item.id, tenant_id=client.tenant.id)
        session.commit()
        pipeline_id = item.id

    with client:
        error_text = call_tool_expecting_error(
            client, "explain_pipeline", {"pipelineId": pipeline_id}
        )

    assert "not found" in error_text.lower()


def test_explain_pipeline_missing_id_errors_the_same_way(app_client):
    # Same "pipeline not found" message for a nonexistent id as for a real
    # id the caller can't read — explain_pipeline must not leak which case
    # it hit (mirrors run_pipeline's not-found path).
    client = app_client(etl_enabled=True)
    with client:
        error_text = call_tool_expecting_error(
            client, "explain_pipeline", {"pipelineId": "does-not-exist"}
        )
    assert "not found" in error_text.lower()


def test_explain_pipeline_includes_refresh_policy_when_set(app_client):
    client = app_client(etl_enabled=True)
    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))

        # refreshPolicy n'est pas un argument de create_pipeline (design
        # SP-15h §4 : transite par le PATCH de config générique, pas un
        # nouvel outil) — on le pose directement via configs_repo, comme le
        # ferait PUT /configs/by-item/{id}. model_validate (pas model_copy)
        # est nécessaire ici : model_copy(update=...) n'exécute aucun
        # validateur, donc refreshPolicy resterait un dict brut sans
        # .model_dump() — exactement ce qu'explain_pipeline appellerait et
        # ferait planter.
        with client.session_factory() as session:
            config = configs_repo.get_config_by_item(session, created["pk"])
            payload_dict = config.config.pipeline.model_dump(by_alias=True)
            payload_dict["refreshPolicy"] = {"enabled": True, "cron": "*/15 * * * *"}
            payload = PipelinePayload.model_validate(payload_dict)
            new_config = BuilderConfig(version=1, kind="pipeline", pipeline=payload)
            configs_repo.update_config(session, config.id, new_config, tenant_id=client.tenant.id)
            session.commit()

        result = call_tool(client, "explain_pipeline", {"pipelineId": created["pk"]})

    assert result["refreshPolicy"] == {"enabled": True, "cron": "*/15 * * * *"}


def test_explain_pipeline_refresh_policy_is_none_when_unset(app_client):
    client = app_client(etl_enabled=True)
    with client:
        source_id, target_id = _register_collections(client)
        created = call_tool(client, "create_pipeline", _linear_pipeline_args(source_id, target_id))
        result = call_tool(client, "explain_pipeline", {"pipelineId": created["pk"]})

    assert result["refreshPolicy"] is None

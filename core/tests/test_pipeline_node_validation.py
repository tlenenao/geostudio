# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _pipeline_body(*, reader_collection: str, writer_collection: str) -> dict:
    return {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection",
                     "params": {"collectionId": reader_collection}},
                    {"id": "w1", "kind": "writer", "op": "writer.collection",
                     "params": {"collectionId": writer_collection}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        # created_at/updated_at n'ont pas de défaut SQL (seulement Python-side
        # via l'ORM, cf. app.collections.models._now) : un INSERT brut doit
        # les fournir explicitement, sans quoi SQLite lève NOT NULL.
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('readable', :t, :o, 'readable', 'Readable', '', 'id', NULL, 1, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('writable', :t, :o, 'writable', 'Writable', '', 'id', NULL, 0, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('locked', :t, :o, 'locked', 'Locked', '', 'id', NULL, 0, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ), {"t": tenant.id, "o": other.id})
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    return TestClient(app)


def test_valid_pipeline_with_existing_collections_saves(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="writable",
    ))
    assert response.status_code == 201


def test_reader_collection_missing_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="does-not-exist", writer_collection="writable",
    ))
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_writer_collection_not_editable_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="locked",
    ))
    assert response.status_code == 422


def test_missing_required_param_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["params"] = {}
    response = env.post("/configs", json=body)
    assert response.status_code == 422


def test_unknown_op_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["op"] = "reader.does-not-exist"
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "unknown op" in response.json()["detail"]


def _pipeline_body_op(op: str, params: dict) -> dict:
    return {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "t1", "kind": "transform", "op": op, "params": params},
                    {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "writable"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
            },
        },
    }


def test_transform_intersection_with_collection_missing_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body_op(
        "transform.intersection", {"withCollectionId": "does-not-exist"},
    ))
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_transform_count_within_with_collection_readable_saves(env):
    response = env.post("/configs", json=_pipeline_body_op(
        "transform.countWithin", {"withCollectionId": "readable"},
    ))
    assert response.status_code == 201


def test_writer_dataset_collection_not_editable_is_rejected(env):
    body = {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "w1", "kind": "writer", "op": "writer.dataset",
                     "params": {"collectionId": "locked", "title": "D"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    response = env.post("/configs", json=body)
    assert response.status_code == 422


def test_writer_dataset_collection_writable_saves(env):
    body = {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
                    {"id": "w1", "kind": "writer", "op": "writer.dataset",
                     "params": {"collectionId": "writable", "title": "D"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    response = env.post("/configs", json=body)
    assert response.status_code == 201


def _pipeline_body_binary_op(op: str, params: dict, edges_extra: list[dict] | None = None,
                              nodes_extra: list[dict] | None = None,
                              include_primary_edge: bool = True) -> dict:
    nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}},
        {"id": "t1", "kind": "transform", "op": op, "params": params},
        {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "writable"}},
    ]
    edges = [{"id": "e2", "from": "t1", "to": "w1"}]
    if include_primary_edge:
        edges.insert(0, {"id": "e1", "from": "r1", "to": "t1"})
    if nodes_extra:
        nodes += nodes_extra
    if edges_extra:
        edges += edges_extra
    return {
        "title": "P",
        "config": {"version": 1, "kind": "pipeline", "pipeline": {"nodes": nodes, "edges": edges}},
    }


def test_transform_merge_with_neither_collection_id_nor_secondary_edge_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body_binary_op("transform.merge", {}))
    assert response.status_code == 422
    assert "requires either" in response.json()["detail"]


def test_transform_merge_with_both_collection_id_and_secondary_edge_is_rejected(env):
    body = _pipeline_body_binary_op(
        "transform.merge", {"withCollectionId": "readable"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "cannot have both" in response.json()["detail"]


def test_transform_merge_via_secondary_edge_saves(env):
    body = _pipeline_body_binary_op(
        "transform.merge", {},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 201


def test_non_binary_op_with_secondary_edge_is_rejected(env):
    body = _pipeline_body_binary_op(
        "transform.filter", {"expr": "1=1"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "does not accept a secondary input edge" in response.json()["detail"]


def test_transform_join_with_only_secondary_edge_and_no_collection_id_saves(env):
    body = _pipeline_body_binary_op(
        "transform.join", {"on": "id"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 201


def test_transform_join_with_only_secondary_edge_and_no_primary_edge_is_rejected(env):
    # Régression finding final review SP-15g : un op binaire satisfait le XOR
    # (secondaire seule, pas de withCollectionId) mais n'a AUCUNE arête
    # primaire entrante — doit être rejeté à la sauvegarde, pas planter au
    # runtime (predecessor_id() renvoie None, assert sans message).
    body = _pipeline_body_binary_op(
        "transform.join", {"on": "id"},
        nodes_extra=[{"id": "r2", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "readable"}}],
        edges_extra=[{"id": "e3", "from": "r2", "to": "t1", "role": "secondary"}],
        include_primary_edge=False,
    )
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "requires a primary input edge" in response.json()["detail"]

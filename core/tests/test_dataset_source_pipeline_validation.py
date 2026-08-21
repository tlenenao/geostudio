# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.collections import repository as collections_repo
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _client_and_user(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'source_pipeline_validation.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, tenant, user, Session


def _seed_collection(Session, tenant, user) -> str:
    with Session() as s:
        col = collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="communes",
            title="Communes",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.commit()
        return col.id


def _dataset_body(collection_id: str, source_pipeline_id: str | None) -> dict:
    return {
        "title": "Vue synthèse",
        "config": {
            "kind": "dataset",
            "dataset": {
                "source": "collection",
                "collectionId": collection_id,
                "sourcePipelineId": source_pipeline_id,
            },
        },
    }


def test_create_dataset_rejects_a_nonexistent_source_pipeline(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    resp = client.post("/configs", json=_dataset_body(collection_id, "does-not-exist"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "pipeline not found"


def test_create_dataset_rejects_a_non_pipeline_source_pipeline_id(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    with Session() as s:
        other_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Not a pipeline",
        )
        s.commit()
        other_item_id = other_item.id
    resp = client.post("/configs", json=_dataset_body(collection_id, other_item_id))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "pipeline not found"


def test_create_dataset_succeeds_with_a_readable_source_pipeline(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    with Session() as s:
        pipeline_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="pipeline",
            title="Ma requête",
        )
        s.commit()
        pipeline_item_id = pipeline_item.id
    resp = client.post("/configs", json=_dataset_body(collection_id, pipeline_item_id))
    assert resp.status_code == 201
    assert resp.json()["kind"] == "dataset"


def test_create_dataset_without_source_pipeline_id_still_works(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    resp = client.post("/configs", json=_dataset_body(collection_id, None))
    assert resp.status_code == 201

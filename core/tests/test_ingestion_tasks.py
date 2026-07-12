"""Bout en bout : run_ingestion_task, connecteur procrastinate remplacé par
InMemoryConnector (pattern documenté procrastinate.testing) pour ne dépendre
d'aucun vrai worker en CI ; PostGIS réel pour les écritures du pipeline."""
import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.ingestion import repository as ingestion_repo
from app.ingestion import tasks as ingestion_tasks
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self._objects = objects

    def get_object(self, Bucket, Key):  # noqa: N803 - signature boto3
        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._objects[Key])}


@pytest.fixture()
def env(pg_engine, monkeypatch):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("DATABASE_URL", str(pg_engine.url))
    in_memory = testing.InMemoryConnector()
    with ingestion_tasks.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE ingestion_jobs, items, configs, config_revisions, "
            "collections, audit_log, users, tenants CASCADE"
        ))


def test_valid_geojson_marks_job_done_with_collection_and_item(env, monkeypatch):
    app, Session, tenant, user = env
    geojson = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
    )
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k1": geojson})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k1",
            filename="villes.geojson", collection_title="Villes import",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "done"
        assert fetched.collection_id is not None
        assert fetched.item_id is not None


def test_corrupted_file_marks_job_error_not_zombie(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k2": b"not json"})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k2",
            filename="broken.geojson", collection_title="Casse",
            lat_field=None, lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "error"
        assert fetched.error_message is not None


def test_missing_job_is_a_noop_not_a_crash(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({}))
    ingestion_tasks.run_ingestion_task.defer(job_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])  # ne doit pas lever

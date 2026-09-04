# SPDX-License-Identifier: Apache-2.0
"""Bout en bout : run_ingestion_task, connecteur procrastinate remplacé par
InMemoryConnector (pattern documenté procrastinate.testing) pour ne dépendre
d'aucun vrai worker en CI ; PostGIS réel pour les écritures du pipeline."""

import pytest
from procrastinate import testing
from sqlalchemy import select, text

from app.db import Base, make_session_factory
from app.ingestion import repository as ingestion_repo
from app.ingestion import tasks as ingestion_tasks
from app.notifications import repository as notifications_repo
from app.notifications.models import Notification
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
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    in_memory = testing.InMemoryConnector()
    with ingestion_tasks.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE ingestion_jobs, items, configs, config_revisions, "
                "collections, audit_log, users, tenants CASCADE"
            )
        )


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
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k1",
            filename="villes.geojson",
            collection_title="Villes import",
            lat_field=None,
            lon_field=None,
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
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k2",
            filename="broken.geojson",
            collection_title="Casse",
            lat_field=None,
            lon_field=None,
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


def test_success_writes_a_notification_for_the_creator(env, monkeypatch):
    app, Session, tenant, user = env
    geojson = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
    )
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k3": geojson})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k3",
            filename="villes.geojson",
            collection_title="Villes notif",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == user.id
        assert notification.kind == "ingestion"
        assert notification.status == "success"
        assert notification.item_resource_type == "dataset"
        assert notification.item_title == "Villes notif"
        assert notification.item_id is not None


def test_failure_writes_a_notification_with_no_item(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k4": b"not json"})
    )
    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k4",
            filename="broken.geojson",
            collection_title="Casse notif",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.status == "failure"
        assert notification.item_id is None
        assert notification.item_title == "Casse notif"
        assert notification.error_message is not None


def test_notification_write_failure_does_not_affect_job_status(env, monkeypatch):
    """I2 (revue finale SP-39) : une erreur dans l'écriture de la
    notification ne doit jamais affecter le statut du job lui-même. Boom
    réel (viole une contrainte NOT NULL, SAWarning-as-error sous pytest ou
    IntegrityError hors pytest) plutôt qu'une exception Python qui ne
    toucherait jamais la session — cf. test_report_jobs.py pour la même
    falsification."""
    app, Session, tenant, user = env
    geojson = (
        b'{"type":"FeatureCollection","features":[{"type":"Feature",'
        b'"properties":{"nom":"A"},"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
    )
    monkeypatch.setattr(
        ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({"k6": geojson})
    )

    def _boom(session, **kwargs):
        session.add(
            Notification(
                tenant_id=tenant.id,
                recipient_user_id=user.id,
                kind="x",
                status="failure",
                item_title="x",
            )
        )
        session.flush()

    monkeypatch.setattr(notifications_repo, "create_notification", _boom)

    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k6",
            filename="villes.geojson",
            collection_title="Villes best-effort",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task.defer(job_id=job_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["ingestion"])

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "done"
        assert fetched.item_id is not None
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is None


def test_early_failure_before_created_by_bound_does_not_crash(env, monkeypatch):
    """Régression : si get_job/mark_running lève avant que created_by/
    collection_title ne soient affectés, le handler générique `except
    Exception` de run_ingestion_task appelait _notify(created_by=...,
    collection_title=...) sur ces deux locales jamais liées ->
    UnboundLocalError levée AVANT même d'entrer dans le try/except de
    _notify, donc jamais avalée par lui — elle s'échappait de
    run_ingestion_task en entier (trouvé en revue de la Task 4, SP-39).
    Appel direct de la fonction (pas de passage par le worker
    procrastinate) : c'est cette levée qu'on veut voir absente ici."""
    app, Session, tenant, user = env
    monkeypatch.setattr(ingestion_tasks, "_make_s3_client_from_env", lambda: _FakeS3Client({}))

    def _boom(session, *, job_id):
        raise RuntimeError("connectivité DB perdue")

    monkeypatch.setattr(ingestion_repo, "mark_running", _boom)

    with Session() as s:
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k5",
            filename="peu-importe.geojson",
            collection_title="Titre peu importe",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        job_id = job.id

    ingestion_tasks.run_ingestion_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        fetched = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert fetched.status == "error"
        assert fetched.error_message is not None
        assert "connectivité DB perdue" in fetched.error_message

        # Pas de destinataire connu (created_by jamais lié) : aucune
        # notification de repli n'est écrite — le job est déjà marqué
        # "error" ci-dessus, la garantie best-effort porte sur la
        # notification, pas sur le statut du job.
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is None

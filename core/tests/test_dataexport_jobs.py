# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import select

from app.collections.introspection import ColumnInfo, TableInfo
from app.collections.models import Collection
from app.dataexport import jobs as dx_jobs
from app.dataexport import repository as dx_repo
from app.db import init_db, make_engine, make_session_factory
from app.features import routes as features_routes
from app.features.repository import FeaturePage
from app.notifications.models import Notification
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="region", type="string", required=True)],
)


class _FakeS3:
    def __init__(self):
        self.objects = {}

    def create_bucket(self, **kw):
        pass

    def put_bucket_cors(self, **kw):
        pass

    def put_bucket_lifecycle_configuration(self, **kw):
        pass

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[(Bucket, Key)] = (Body, ContentType)

    def delete_object(self, *, Bucket, Key):
        self.objects.pop((Bucket, Key), None)


class _FakeRepo:
    """Pages keyset de 2 sur n lignes ; enregistre les appels (masquage, filtres)."""

    def __init__(self, n):
        self.n = n
        self.calls = []

    def select_features(self, session, info, *, limit, after=None, **kw):
        self.calls.append({"info": info, "after": after, **kw})
        start = int(after) if after else 0
        stop = min(start + 2, self.n)
        feats = [
            {
                "type": "Feature",
                "id": i,
                "properties": {"region": "r"},
                "geometry": {"type": "Point", "coordinates": [0, 0]},
            }
            for i in range(start + 1, stop + 1)
        ]
        return FeaturePage(
            features=feats,
            number_matched=None,
            number_returned=len(feats),
            next_cursor=str(stop) if stop < self.n else None,
        )


@pytest.fixture()
def env(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'dx.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "t")
    monkeypatch.setenv("S3_SECRET_KEY", "t")
    engine = make_engine(url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="A",
            last_name="",
            bootstrap_admin=True,  # data.view_sensitive : le verdict est recalculé à l'exécution
        )
        s.add(
            Collection(
                id="villes",
                tenant_id=tenant.id,
                owner_id=user.id,
                table_name="villes",
                title="Villes",
                pk_column="id",
                sensitive_fields=["region"],
            )
        )
        s.commit()
        ids = (tenant.id, user.id)
    s3 = _FakeS3()
    repo = _FakeRepo(5)
    monkeypatch.setattr(dx_jobs, "s3_client_from_env", lambda: s3)
    monkeypatch.setattr(dx_jobs, "features_repo", repo)
    monkeypatch.setattr(dx_jobs, "rls_scope", features_routes.null_rls_scope)
    monkeypatch.setattr(dx_jobs, "introspect_table", lambda session, name: INFO)
    return factory, ids, s3, repo


def _new_job(factory, ids, **kw):
    with factory() as s:
        job = dx_repo.create_job(
            s,
            tenant_id=ids[0],
            collection_id=kw.pop("collection_id", "villes"),
            requested_by=ids[1],
            fmt="geojson",
            masked=kw.pop("masked", True),
            **kw,
        )
        s.commit()
        return job.id


def _job(factory, ids, job_id):
    with factory() as s:
        return dx_repo.get_job(s, job_id, ids[0])


def test_job_done_uploads_pages_and_notifies(env):
    factory, ids, s3, repo = env
    job_id = _new_job(factory, ids, query={"bbox": [0, 0, 1, 1], "filters": {"region": "r"}})
    dx_jobs.run_collection_export(job_id, ids[0])
    job = _job(factory, ids, job_id)
    assert job.status == "done" and job.started_at and job.finished_at
    assert job.result_key == f"{ids[0]}/data-exports/{job_id}.geojson"
    assert ("geostudio-exports", job.result_key) in s3.objects
    assert len(repo.calls) == 3  # 5 lignes, pages de 2 : le curseur est suivi
    assert repo.calls[0]["bbox"] == (0, 0, 1, 1) and repo.calls[0]["filters"] == {"region": "r"}
    # masquage GAP-22 : la colonne sensible n'est pas lue
    assert [c.name for c in repo.calls[0]["info"].columns] == []
    with factory() as s:
        n = s.scalars(select(Notification)).one()
    assert (n.kind, n.status, n.item_id) == ("data_export", "success", None)


def test_unmasked_job_keeps_sensitive_columns(env):
    factory, ids, _s3, repo = env
    dx_jobs.run_collection_export(_new_job(factory, ids, masked=False), ids[0])
    assert [c.name for c in repo.calls[0]["info"].columns] == ["region"]


def test_notification_failure_does_not_undo_done(env, monkeypatch):
    factory, ids, _s3, _repo = env

    def boom(*a, **k):
        raise RuntimeError("notif down")

    monkeypatch.setattr("app.jobs.common.notifications_repo.create_notification", boom)
    job_id = _new_job(factory, ids)
    dx_jobs.run_collection_export(job_id, ids[0])
    assert _job(factory, ids, job_id).status == "done"


def test_over_job_max_fails(env, monkeypatch):
    factory, ids, s3, _repo = env
    monkeypatch.setenv("CORE_EXPORT_JOB_MAX", "3")
    job_id = _new_job(factory, ids)
    dx_jobs.run_collection_export(job_id, ids[0])
    job = _job(factory, ids, job_id)
    assert job.status == "failed" and "too many entities" in job.error and job.finished_at
    assert not s3.objects


def test_collection_deleted_meanwhile_fails(env, monkeypatch):
    # En base la suppression cascade sur le job ; reste la fenêtre de course
    # entre la prise du job et la relecture de la collection.
    factory, ids, _s3, _repo = env
    job_id = _new_job(factory, ids)
    monkeypatch.setattr(dx_jobs.collections_repo, "get_collection", lambda *a, **k: None)
    dx_jobs.run_collection_export(job_id, ids[0])
    job = _job(factory, ids, job_id)
    assert job.status == "failed" and "collection not found" in job.error


def test_late_upload_after_reclaim_deletes_orphan_and_does_not_notify_success(env, monkeypatch):
    """Job passe `failed` (reprise) pendant l'envoi : l'objet S3 est supprime."""
    factory, ids, s3, _repo = env
    job_id = _new_job(factory, ids)
    real_put = s3.put_object

    def put_then_reclaimed(**kw):
        real_put(**kw)
        with factory() as s:
            dx_repo.mark_failed(s, job_id, "export timed out (worker crashed or hung)")
            s.commit()

    monkeypatch.setattr(s3, "put_object", put_then_reclaimed)
    dx_jobs.run_collection_export(job_id, ids[0])
    assert _job(factory, ids, job_id).status == "failed"
    assert not s3.objects
    with factory() as s:
        assert s.scalars(select(Notification)).all() == []


def test_running_reclaim_minutes_is_configurable(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_RUNNING_TIMEOUT_MINUTES", "7")
    assert dx_repo.running_reclaim_minutes() == 7
    monkeypatch.delenv("CORE_EXPORT_RUNNING_TIMEOUT_MINUTES")
    assert dx_repo.running_reclaim_minutes() == 60

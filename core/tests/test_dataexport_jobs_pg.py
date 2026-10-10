# SPDX-License-Identifier: Apache-2.0
"""Export asynchrone de collection sur PostGIS réel (vrai select_features, vraie
RLS par colonne) : revérification des droits à l'exécution (GAP-22, REV-283e)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.dataexport import jobs as dx_jobs
from app.dataexport import repository as dx_repo
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3:
    def __init__(self):
        self.objects = {}

    def create_bucket(self, **kw):
        pass

    def put_bucket_cors(self, **kw):
        pass

    def put_bucket_lifecycle_configuration(self, **kw):
        pass

    def delete_object(self, **kw):
        pass

    def put_object(self, *, Bucket, Key, Body, ContentType):
        self.objects[Key] = Body


@pytest.fixture()
def pg(pg_engine, monkeypatch):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dx_villes"))
        conn.execute(
            text(
                "CREATE TABLE dx_villes (id serial PRIMARY KEY, nom text, "
                "salaire integer, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        kw = dict(tenant_id=tenant.id, email=None, first_name="", last_name="")
        admin = get_or_create_user(s, oidc_sub="a", username="admin", bootstrap_admin=True, **kw)
        regular = get_or_create_user(s, oidc_sub="r", username="regular", **kw)
        s.commit()
        ids = (tenant.id, admin.id, regular.id)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3()
    client = TestClient(app)
    assert (
        client.post(
            "/v1/collections", json={"tableName": "dx_villes", "isPublic": True}
        ).status_code
        == 201
    )
    for n, sal in (("Lyon", 111), ("Nice", 222)):
        client.post(
            "/v1/collections/dx_villes/items",
            json={
                "type": "Feature",
                "properties": {"nom": n, "salaire": sal},
                "geometry": {"type": "Point", "coordinates": [1, 1]},
            },
        )
    client.patch("/v1/collections/dx_villes", json={"sensitiveFields": ["salaire"]})
    s3 = _FakeS3()
    monkeypatch.setattr(dx_jobs, "s3_client_from_env", lambda: s3)
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "t")
    monkeypatch.setenv("S3_SECRET_KEY", "t")
    monkeypatch.setattr(db, "get_session_factory", lambda: Session, raising=False)
    monkeypatch.setattr(dx_jobs, "session_factory", lambda: Session)
    yield client, Session, ids, s3
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS dx_villes"))
        conn.execute(
            text(
                "TRUNCATE collection_export_jobs, collection_shares, collections, audit_log,"
                " notifications, users, tenants CASCADE"
            )
        )


def _run(Session, ids, *, by, masked, query=None):
    with Session() as s:
        job = dx_repo.create_job(
            s,
            tenant_id=ids[0],
            collection_id="dx_villes",
            requested_by=by,
            fmt="geojson",
            masked=masked,
            query=query,
        )
        s.commit()
        job_id = job.id
    dx_jobs.run_collection_export(job_id, ids[0])
    with Session() as s:
        return dx_repo.get_job(s, job_id, ids[0])


def test_admin_unmasked_export_keeps_sensitive_column(pg):
    _c, Session, ids, s3 = pg
    job = _run(Session, ids, by=ids[1], masked=False)
    assert job.status == "done", job.error
    assert json.loads(s3.objects[job.result_key])["features"][0]["properties"]["salaire"] == 111


def test_privilege_removed_before_execution_masks_columns(pg):
    # Job créé masked=False, demandeur sans data.view_sensitive à l'exécution.
    _c, Session, ids, s3 = pg
    job = _run(Session, ids, by=ids[2], masked=False)
    assert job.status == "done", job.error
    body = s3.objects[job.result_key].decode()
    assert "Lyon" in body and "salaire" not in body and "111" not in body


def test_read_right_removed_before_execution_fails(pg):
    client, Session, ids, s3 = pg
    client.patch("/v1/collections/dx_villes", json={"isPublic": False})
    job = _run(Session, ids, by=ids[2], masked=True)
    assert job.status == "failed" and job.error
    assert not s3.objects


def test_filter_on_masked_column_fails(pg):
    _c, Session, ids, s3 = pg
    job = _run(Session, ids, by=ids[2], masked=True, query={"filters": {"salaire": "111"}})
    assert job.status == "failed" and "salaire" in job.error
    assert not s3.objects

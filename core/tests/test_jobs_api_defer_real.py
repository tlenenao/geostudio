# SPDX-License-Identifier: Apache-2.0
"""P01.01 (RC-1) : le process API doit pouvoir déférer pour de vrai.

Aucun deferrer n'est mocké ici : POST /v1/uploads passe par le vrai
`run_ingestion_task.defer(...)` et doit laisser une ligne `procrastinate_jobs`.
Avant le correctif, le lifespan n'ouvrait pas le connecteur procrastinate et la
route levait `AppNotOpen` (500) après avoir commité la ligne `ingestion_jobs`."""

import os

import procrastinate
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user
from app.db import Base, core_table_names, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.jobs import app as jobs_app
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_post_uploads_inserts_a_real_procrastinate_job(
    monkeypatch, pg_engine_with_procrastinate_schema
):
    engine = pg_engine_with_procrastinate_schema
    core_table_names()
    Base.metadata.create_all(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="p01",
            username="p01",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        tenant_id = tenant.id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))

    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    api = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    api.dependency_overrides[db.get_session] = override_session
    api.dependency_overrides[get_current_user] = lambda: user
    # Seul S3 est simulé (quotas éteints → aucun appel S3) ; le deferrer reste le vrai.
    api.dependency_overrides[ingestion_routes.get_s3_client] = lambda: object()

    with jobs_app.replace_connector(procrastinate.PsycopgConnector(conninfo=conninfo)):
        with TestClient(api) as client:  # exécute le lifespan
            res = client.post(
                "/v1/uploads",
                json={
                    "key": f"{tenant_id}/up/f.geojson",
                    "filename": "f.geojson",
                    "collectionTitle": "C",
                },
            )
    assert res.status_code == 201, res.text
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT task_name, args->>'tenant_id' FROM procrastinate_jobs")
        ).all()
    assert len(rows) == 1
    assert rows[0][0].endswith("run_ingestion_task")
    assert rows[0][1] == tenant_id

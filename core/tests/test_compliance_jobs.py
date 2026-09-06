# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 10 : purge_tenant_task — confirme que le déclenchement
asynchrone (session/commit propres au job, s3 client construit depuis
l'environnement) n'introduit pas de régression par rapport à un appel
direct de purge_tenant (Tâche 9) — même patron que la Tâche 9 Step 4 du
plan ("réutiliser le test caractéristique en le faisant passer par le
job")."""

import pytest

from app.compliance.jobs import purge_tenant_task
from app.compliance.models import PurgeReceipt
from app.db import init_db, make_engine, make_session_factory
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}

    def delete_objects(self, *, Bucket, Delete):
        pass

    def delete_object(self, *, Bucket, Key):
        pass


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio.test")
    monkeypatch.setenv("S3_ACCESS_KEY", "test")
    monkeypatch.setenv("S3_SECRET_KEY", "test")
    db_path = tmp_path / "compliance_jobs.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
        tenant_id, user_id = tenant.id, user.id
    return Session, tenant_id, user_id


def test_purge_tenant_task_commits_and_creates_the_receipt(env, monkeypatch):
    Session, tenant_id, user_id = env
    monkeypatch.setattr("app.compliance.jobs.s3_client_from_env", lambda: _FakeS3Client())

    purge_tenant_task(purge_id="job-purge-1", tenant_id=tenant_id, requested_by_user_id=user_id)

    with Session() as s:
        receipt = s.get(PurgeReceipt, "job-purge-1")
        assert receipt is not None
        assert receipt.tenant_slug == "default"
        assert receipt.requested_by_user_id == user_id
        from app.tenants.models import Tenant

        assert s.get(Tenant, tenant_id) is None

# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import repository as repo
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    return Session, tenant, alice


def test_create_job_defaults_to_pending(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key=f"{tenant.id}/x/city.zip",
            upload_id="mpu-1", filename="city.zip", title="Ville",
        )
        s.commit()
        assert job.status == "pending"
        assert job.item_id is None
        assert job.error_message is None


def test_get_job_scopes_by_tenant(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id) is not None
        assert repo.get_job(s, tenant_id="other-tenant", job_id=job_id) is None


def test_mark_finalizing_then_done_transitions_status_and_sets_item_id(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_finalizing(s, job_id=job_id)
        s.commit()
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id).status == "finalizing"
    with Session() as s:
        repo.mark_done(s, job_id=job_id, item_id="item-42")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id == "item-42"


def test_mark_error_sets_status_and_message(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_error(s, job_id=job_id, error_message="archive zip invalide")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.error_message == "archive zip invalide"

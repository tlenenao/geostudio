# SPDX-License-Identifier: Apache-2.0
"""Job d'embedding d'une collection (SP-7 Task 7) — même pattern que
test_items_jobs.py."""

import pytest
from procrastinate import testing
from sqlalchemy import text

from app.collections import jobs as collection_jobs
from app.collections import repository as collections_repo
from app.db import Base, make_session_factory
from app.jobs import app as jobs_app
from app.search.providers import FakeProvider
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


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
    with jobs_app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE collections, users, tenants CASCADE"))


def test_embed_collection_task_sets_the_embedding_column(env, monkeypatch):
    app, Session, tenant, user = env
    with Session() as s:
        col = collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="incidents",
            title="Incidents",
            description="Voirie",
            is_public=False,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.commit()
        col_id = col.id

    fake = FakeProvider(vectors={"Incidents\nVoirie": [0.5] * 1536})
    monkeypatch.setattr(collection_jobs, "get_embedding_provider", lambda: fake)

    collection_jobs.embed_collection_task.defer(collection_id=col_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])

    with Session() as s:
        from app.collections.models import Collection

        reloaded = s.get(Collection, col_id)
        assert reloaded.embedding == pytest.approx([0.5] * 1536)


def test_embed_collection_task_missing_collection_is_a_noop_not_a_crash(env):
    app, Session, tenant, _user = env
    collection_jobs.embed_collection_task.defer(collection_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])  # ne doit pas lever

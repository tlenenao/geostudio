"""Job d'embedding d'un item (SP-7 Task 5) — même pattern que
test_ingestion_tasks.py : connecteur procrastinate remplacé par
InMemoryConnector, écritures contre PostGIS réel."""
import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.items import jobs as item_jobs
from app.items import repository as items_repo
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    in_memory = testing.InMemoryConnector()
    with jobs_app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


def test_embed_item_task_sets_the_embedding_column(env, monkeypatch):
    app, Session, tenant, user = env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id,
            resource_type="app", title="Incidents voirie",
        )
        s.commit()
        item_id = item.id

    fake = FakeProvider(vectors={"Incidents voirie\n\n": [0.5] * 1536})
    monkeypatch.setattr(item_jobs, "get_embedding_provider", lambda: fake)

    item_jobs.embed_item_task.defer(item_id=item_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])

    with Session() as s:
        from app.items.models import Item
        reloaded = s.get(Item, item_id)
        assert reloaded.embedding == pytest.approx([0.5] * 1536)


def test_embed_item_task_missing_item_is_a_noop_not_a_crash(env):
    app, Session, tenant, _user = env
    item_jobs.embed_item_task.defer(item_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["search"])  # ne doit pas lever

# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, users, tenants CASCADE"
        ))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


def test_create_get_list_source(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://stac.example.com/collections", mode="reference",
        enabled=True, interval_minutes=60,
    )
    fetched = repo.get_source(session, tenant_id=tenant.id, source_id=source.id)
    assert fetched.url == "https://stac.example.com/collections"
    assert [s.id for s in repo.list_sources(session, tenant_id=tenant.id)] == [source.id]


def test_get_source_cross_tenant_returns_none(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    assert repo.get_source(session, tenant_id="other-tenant", source_id=source.id) is None


def test_update_source_patches_fields(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.update_source(session, source, url="https://b", enabled=False)
    assert source.url == "https://b"
    assert source.enabled is False


def test_delete_source_cascades_to_records(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="ext-1",
        item_id=None, collection_id=None, content_hash="h",
    )
    session.flush()
    repo.delete_source(session, source)
    session.flush()
    assert repo.get_source(session, tenant_id=tenant.id, source_id=source.id) is None
    from app.harvest.models import HarvestRecord
    assert session.query(HarvestRecord).count() == 0


def test_mark_running_sets_status(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    repo.mark_running(session, tenant_id=tenant.id, source_id=source.id)
    assert source.last_status == "running"


def test_mark_missing_as_stale_flags_unseen_records_only(session, tenant_and_user):
    tenant, user = tenant_and_user
    source = repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    seen = repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="keep",
        item_id=None, collection_id=None, content_hash="h1",
    )
    gone = repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="gone",
        item_id=None, collection_id=None, content_hash="h2",
    )
    session.flush()
    repo.mark_missing_as_stale(
        session, tenant_id=tenant.id, source_id=source.id, seen_external_ids={"keep"},
    )
    assert seen.is_stale is False
    assert gone.is_stale is True


def test_list_due_sources_includes_never_run_and_overdue_enabled_sources(session, tenant_and_user):
    tenant, user = tenant_and_user

    def make(url, *, enabled=True, interval_minutes=30, last_run_at=None):
        s = repo.create_source(
            session, tenant_id=tenant.id, owner_id=user.id, type="stac", url=url,
            mode="reference", enabled=enabled, interval_minutes=interval_minutes,
        )
        s.last_run_at = last_run_at
        return s

    never_run = make("https://a")
    overdue = make("https://b", last_run_at=datetime.now(timezone.utc) - timedelta(hours=1))
    fresh = make("https://c", last_run_at=datetime.now(timezone.utc))
    make("https://d", enabled=False, last_run_at=None)
    make("https://e", interval_minutes=None, last_run_at=None)
    session.flush()

    due_ids = {s.id for s in repo.list_due_sources(session)}
    assert due_ids == {never_run.id, overdue.id}
    assert fresh.id not in due_ids


@pytest.mark.postgis
def test_unique_constraint_rejects_duplicate_external_id_for_same_source(pg_session, pg_tenant_and_user):
    tenant, user = pg_tenant_and_user
    source = repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    pg_session.commit()
    repo.create_record(
        pg_session, tenant_id=tenant.id, source_id=source.id, external_id="dup",
        item_id=None, collection_id=None, content_hash="h",
    )
    pg_session.commit()
    with pytest.raises(IntegrityError):
        repo.create_record(
            pg_session, tenant_id=tenant.id, source_id=source.id, external_id="dup",
            item_id=None, collection_id=None, content_hash="h2",
        )
        pg_session.commit()
    pg_session.rollback()

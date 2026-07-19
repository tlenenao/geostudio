# SPDX-License-Identifier: Apache-2.0
"""Bout en bout : run_harvest_task/run_harvest_sweep_task, connecteur
procrastinate remplacé par InMemoryConnector (même pattern que
test_ingestion_tasks.py) ; PostGIS réel pour les tables harvest_*/items."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from procrastinate import testing
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.harvest import jobs as harvest_jobs
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.base import HarvestedRecord
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

RECORD = HarvestedRecord(
    external_id="buildings", title="Bâtiments", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0], external_url="https://a", items_url=None,
)


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
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "false")
    in_memory = testing.InMemoryConnector()
    with harvest_jobs.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, configs, "
            "config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


def test_run_harvest_task_harvests_a_reference_source(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    with Session() as s:
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://a",
            mode="reference", enabled=True, interval_minutes=None,
        )
        s.commit()
        source_id = source.id

    harvest_jobs.run_harvest_task.defer(source_id=source_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        fetched = harvest_repo.get_source(s, tenant_id=tenant.id, source_id=source_id)
        assert fetched.last_status == "ok"
        rec = harvest_repo.get_record(s, tenant_id=tenant.id, source_id=source_id, external_id="buildings")
        assert rec is not None


def test_run_harvest_task_missing_source_is_a_noop(env):
    app, Session, tenant, user = env
    harvest_jobs.run_harvest_task.defer(source_id="does-not-exist", tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])  # ne doit pas lever


def test_run_harvest_task_short_circuits_in_read_only_mode(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with Session() as s:
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://a",
            mode="reference", enabled=True, interval_minutes=None,
        )
        s.commit()
        source_id = source.id

    harvest_jobs.run_harvest_task.defer(source_id=source_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        fetched = harvest_repo.get_source(s, tenant_id=tenant.id, source_id=source_id)
        assert fetched.last_status is None  # jamais moissonné


def test_sweep_defers_due_sources_only(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    with Session() as s:
        due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        not_due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://not-due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        not_due.last_run_at = datetime.now(timezone.utc)
        s.commit()
        due_id, not_due_id = due.id, not_due.id

    harvest_jobs.run_harvest_sweep_task.defer(timestamp=0)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=due_id).last_status == "ok"
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=not_due_id).last_status is None


def test_sweep_short_circuits_in_read_only_mode(env, monkeypatch):
    app, Session, tenant, user = env
    monkeypatch.setattr(service, "get_connector", lambda t: Mock(fetch=Mock(return_value=[RECORD])))
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with Session() as s:
        due = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=user.id, type="stac", url="https://due",
            mode="reference", enabled=True, interval_minutes=30,
        )
        s.commit()
        due_id = due.id

    harvest_jobs.run_harvest_sweep_task.defer(timestamp=0)
    app.run_worker(wait=False, queues=["harvest"])

    with Session() as s:
        assert harvest_repo.get_source(s, tenant_id=tenant.id, source_id=due_id).last_status is None

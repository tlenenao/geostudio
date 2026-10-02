# SPDX-License-Identifier: Apache-2.0
"""P01.07 (t02-013, j09-014) : /health expose la santé de la file de jobs."""

import os

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def test_health_reports_backlog_age_when_worker_is_stopped(
    monkeypatch, pg_engine_with_procrastinate_schema
):
    engine = pg_engine_with_procrastinate_schema
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args, status, "
                "scheduled_at) VALUES ('q', 't', NULL, '{}', 'todo', now() - interval '10 minutes')"
            )
        )
    try:
        backlog = TestClient(create_app()).get("/health").json()["jobsBacklog"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM procrastinate_jobs"))
    assert backlog["todo"] == 1
    assert 590 <= backlog["oldestTodoAgeSeconds"] <= 700


def test_health_reports_backlog_age_of_a_job_deferred_without_schedule(
    monkeypatch, pg_engine_with_procrastinate_schema
):
    # Cas réel : un .defer() sans schedule_in laisse scheduled_at NULL — l'âge se lit
    # alors sur l'événement « deferred », sinon un worker arrêté resterait invisible.
    engine = pg_engine_with_procrastinate_schema
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args, status) "
                "VALUES ('q', 't', NULL, '{}', 'todo')"
            )
        )
        conn.execute(text("UPDATE procrastinate_events SET at = now() - interval '10 minutes'"))
    try:
        backlog = TestClient(create_app()).get("/health").json()["jobsBacklog"]
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM procrastinate_jobs"))
    assert backlog["todo"] == 1
    assert 590 <= backlog["oldestTodoAgeSeconds"] <= 700


def test_health_caches_the_backlog_query(monkeypatch):
    # /health est anonyme : le COUNT SQL ne doit pas partir à chaque appel.
    calls = []
    monkeypatch.setattr("app.main.jobs_backlog", lambda: calls.append(1) or {"todo": 0})
    client = TestClient(create_app())
    for _ in range(3):
        assert client.get("/health").json()["jobsBacklog"] == {"todo": 0}
    assert len(calls) == 1


def test_health_backlog_is_null_when_queue_unreadable(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    res = TestClient(create_app()).get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["jobsBacklog"] is None

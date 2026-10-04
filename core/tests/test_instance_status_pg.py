# SPDX-License-Identifier: Apache-2.0
"""REV-274c : seuil « job bloqué » configurable, slot CDC absent = non configuré."""

from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.cdc.consumer import SLOT_NAME
from app.instance import routes


def test_slot_name_matches_the_cdc_consumer():
    # instance ne peut pas importer cdc (contrat de couches) : la constante
    # est dupliquée, ce test empêche qu'elle dérive.
    assert routes._CDC_SLOT == SLOT_NAME


@pytest.fixture
def status(monkeypatch, pg_engine_with_procrastinate_schema):
    engine = pg_engine_with_procrastinate_schema
    monkeypatch.setattr(routes, "require_privilege", lambda *a, **k: None)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        job_id = conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args, status) "
                "VALUES ('q', 't', NULL, '{}', 'doing') RETURNING id"
            )
        ).scalar_one()
        # Le trigger procrastinate n'insère un événement que pour 'todo' :
        # on pose à la main un « started » vieux de 30 minutes.
        conn.execute(
            text(
                "INSERT INTO procrastinate_events (job_id, type, at) "
                "VALUES (:j, 'started', now() - interval '30 minutes')"
            ),
            {"j": job_id},
        )

    def call() -> dict:
        with Session(engine) as session:
            return routes.get_instance_status(user=SimpleNamespace(), session=session, s3=None)

    yield call
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))


def test_stalled_threshold_comes_from_env(status, monkeypatch):
    monkeypatch.setenv("CORE_STALLED_JOB_MINUTES", "10")
    assert status()["jobs"]["stalled"] == 1
    monkeypatch.delenv("CORE_STALLED_JOB_MINUTES")
    assert status()["jobs"]["stalled"] == 0  # défaut 60 min


def test_stalled_threshold_ignores_invalid_values(status, monkeypatch):
    for bad in ("abc", "0", "-5"):
        monkeypatch.setenv("CORE_STALLED_JOB_MINUTES", bad)
        assert status()["jobs"]["stalled"] == 0


def test_cdc_probe_reports_absent_slot_as_not_configured(
    status, pg_engine_with_procrastinate_schema
):
    with pg_engine_with_procrastinate_schema.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_replication_slots WHERE slot_name = :n"), {"n": SLOT_NAME}
        ).first()
    cdc = status()["cdc"]
    assert cdc["ok"] is True
    if exists is None:
        assert cdc == {"ok": True, "configured": False}
    else:  # base de test où un slot traîne : la forme « configurée » est complète
        assert cdc["configured"] is True and isinstance(cdc["slotActive"], bool)

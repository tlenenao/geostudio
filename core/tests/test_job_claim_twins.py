# SPDX-License-Identifier: Apache-2.0
"""REV-295 : mark_running des jumelles de pipelines.repository.mark_running
est une transition conditionnelle pending -> running (un job terminé, en
erreur ou inconnu n'est jamais ré-armé par une re-livraison de tâche)."""

import pytest
from sqlalchemy import event, select

from app.appexport import repository as appexport_repo
from app.appexport.models import AppExportJob
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.export.models import ExportJob
from app.ingestion import repository as ingestion_repo
from app.ingestion.models import IngestionJob


@pytest.fixture
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)

    @event.listens_for(engine, "connect")
    def _fk_off(dbapi_conn, _rec):
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")

    with make_session_factory(engine)() as s:
        s.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")
        yield s


def _ingestion(status):
    return IngestionJob(
        id="j", tenant_id="t", created_by="u", status=status,
        source_key="k", filename="f.csv", collection_title="T",
    )  # fmt: skip


def _export(status):
    return ExportJob(id="j", tenant_id="t", item_id="i", user_id="u", format="png", status=status)


def _appexport(status):
    return AppExportJob(
        id="j", tenant_id="t", item_id="i", user_id="u", mode="static", status=status
    )


CASES = [
    (ingestion_repo, IngestionJob, _ingestion),
    (export_repo, ExportJob, _export),
    (appexport_repo, AppExportJob, _appexport),
]


@pytest.mark.parametrize("repo,model,make", CASES)
def test_pending_job_is_claimed_once(session, repo, model, make):
    session.add(make("pending"))
    session.commit()
    assert repo.mark_running(session, job_id="j") is True
    session.commit()
    assert session.scalar(select(model.status)) == "running"
    assert repo.mark_running(session, job_id="j") is False  # déjà pris


@pytest.mark.parametrize("repo,model,make", CASES)
@pytest.mark.parametrize("status", ["done", "error", "running"])
def test_non_pending_job_is_never_rearmed(session, repo, model, make, status):
    session.add(make(status))
    session.commit()
    assert repo.mark_running(session, job_id="j") is False
    session.commit()
    assert session.scalar(select(model.status)) == status


@pytest.mark.parametrize("repo,model,make", CASES)
def test_unknown_job_returns_false(session, repo, model, make):
    assert repo.mark_running(session, job_id="ghost") is False


# --- terrain3d / tileset3d (REV-295, jumelles restantes) ---
from app.terrain3d import repository as terrain_repo  # noqa: E402
from app.terrain3d.models import Terrain3DJob  # noqa: E402
from app.tileset3d import repository as tileset_repo  # noqa: E402
from app.tileset3d.models import Tileset3DJob  # noqa: E402

_CLAIM = [
    (terrain_repo.mark_converting, Terrain3DJob, "converting"),
    (tileset_repo.mark_finalizing, Tileset3DJob, "finalizing"),
]


_START = {Terrain3DJob: "uploaded", Tileset3DJob: "pending"}


def _job3d(model, status):
    extra = {"upload_id": "u"} if model is Tileset3DJob else {}
    return model(
        id="j", tenant_id="t", created_by="u", status=status,
        source_key="k", filename="f", title="T", **extra,
    )  # fmt: skip


@pytest.mark.parametrize("mark,model,running", _CLAIM)
def test_3d_pending_claimed_once(session, mark, model, running):
    session.add(_job3d(model, _START[model]))
    session.commit()
    assert mark(session, job_id="j") is True
    session.commit()
    assert session.scalar(select(model.status)) == running
    assert mark(session, job_id="j") is False


@pytest.mark.parametrize("mark,model,running", _CLAIM)
@pytest.mark.parametrize("status", ["done", "error"])
def test_3d_terminal_never_rearmed(session, mark, model, running, status):
    session.add(_job3d(model, status))
    session.commit()
    assert mark(session, job_id="j") is False
    session.commit()
    assert session.scalar(select(model.status)) == status
    assert mark(session, job_id="ghost") is False

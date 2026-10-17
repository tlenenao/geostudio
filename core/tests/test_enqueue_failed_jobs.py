# SPDX-License-Identifier: Apache-2.0
"""AUD-025 : un `defer()` définitivement échoué marque le job `error` tout de suite
(transition conditionnelle `pending|uploaded -> error`), sans écraser un job déjà pris."""

import pytest

from app.appexport import repository as appexport_repo
from app.export import repository as export_repo
from app.ingestion import repository as ingestion_repo
from app.raster import repository as raster_repo
from app.terrain3d import repository as terrain3d_repo
from app.tileset3d import repository as tileset3d_repo
from tests.test_reclaim_pending_jobs import _env

_UP = dict(source_key="k", filename="f", title="T")


def _make(name, session, tenant, user, item):
    if name == "export":
        return (
            export_repo,
            export_repo.create_job(
                session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="csv"
            ),
            "error",
        )
    if name == "appexport":
        return (
            appexport_repo,
            appexport_repo.create_job(
                session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static"
            ),
            "error",
        )
    if name == "ingestion":
        return (
            ingestion_repo,
            ingestion_repo.create_job(
                session,
                tenant_id=tenant.id,
                created_by=user.id,
                source_key="k",
                filename="f.geojson",
                collection_title="V",
                lat_field=None,
                lon_field=None,
            ),
            "error_message",
        )
    if name == "raster":
        return (
            raster_repo,
            raster_repo.create_job(session, tenant_id=tenant.id, created_by=user.id, **_UP),
            "error_message",
        )
    if name == "terrain3d":
        return (
            terrain3d_repo,
            terrain3d_repo.create_job(session, tenant_id=tenant.id, created_by=user.id, **_UP),
            "error_message",
        )
    return (
        tileset3d_repo,
        tileset3d_repo.create_job(
            session, tenant_id=tenant.id, created_by=user.id, upload_id="u", **_UP
        ),
        "error_message",
    )


DOMAINS = ["export", "appexport", "ingestion", "raster", "terrain3d", "tileset3d"]


@pytest.mark.parametrize("name", DOMAINS)
def test_mark_enqueue_failed_errors_a_fresh_job(name):
    session, tenant, user, item = _env()
    repo, job, errcol = _make(name, session, tenant, user, item)
    session.commit()
    assert repo.mark_enqueue_failed(session, job_id=job.id)
    session.commit()
    session.refresh(job)
    assert job.status == "error" and "mise en file" in getattr(job, errcol)


@pytest.mark.parametrize("name", DOMAINS)
def test_mark_enqueue_failed_never_overwrites_a_taken_job(name):
    session, tenant, user, item = _env()
    repo, job, _ = _make(name, session, tenant, user, item)
    job.status = "done"
    session.commit()
    assert not repo.mark_enqueue_failed(session, job_id=job.id)
    session.refresh(job)
    assert job.status == "done"

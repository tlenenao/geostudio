# SPDX-License-Identifier: Apache-2.0
"""AUD-028 : un worker tué laisse son job en 'doing' (verrou `lock=` tenu à jamais :
compaction/snapshot CDC bloqués). La reprise le termine en 'failed' ; un job d'un worker
vivant n'est pas touché."""

import asyncio
import os
import uuid

import procrastinate
import pytest
from sqlalchemy import text

from app.jobs.recovery import recover_stalled_jobs


def _app():
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    return procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=conninfo))


def _doing_job(c, *, queue, task, lock, worker_id):
    job_id = c.execute(
        text(
            "INSERT INTO procrastinate_jobs (queue_name, task_name, lock, args) "
            "VALUES (:q, :t, :l, '{}') RETURNING id"
        ),
        {"q": queue, "t": task, "l": lock},
    ).scalar()
    c.execute(
        text("UPDATE procrastinate_jobs SET status = 'doing', worker_id = :w WHERE id = :id"),
        {"w": worker_id, "id": job_id},
    )
    return job_id


@pytest.mark.postgis
def test_job_of_a_dead_worker_is_failed_and_a_live_one_is_kept(
    pg_engine_with_procrastinate_schema,
):
    engine = pg_engine_with_procrastinate_schema
    with engine.begin() as c:
        dead = c.execute(
            text(
                "INSERT INTO procrastinate_workers (last_heartbeat) "
                "VALUES (now() - interval '1 hour') RETURNING id"
            )
        ).scalar()
        alive = c.execute(
            text("INSERT INTO procrastinate_workers (last_heartbeat) VALUES (now()) RETURNING id")
        ).scalar()
        stalled = _doing_job(
            c,
            queue="cdc",
            task="app.cdc.jobs.run_compaction_cycle_task",
            lock=f"l1b-{uuid.uuid4().hex}",
            worker_id=dead,
        )
        orphan = _doing_job(  # worker déjà élagué (FK ON DELETE SET NULL)
            c,
            queue="cdc",
            task="app.cdc.jobs.run_compaction_cycle_task",
            lock=f"l1b-{uuid.uuid4().hex}",
            worker_id=None,
        )
        running = _doing_job(
            c, queue="etl", task="app.pipelines.jobs.run_pipeline_task", lock=None, worker_id=alive
        )
    ids = (stalled, orphan, running)

    async def _run():
        app = _app()
        async with app.open_async():
            return await recover_stalled_jobs(app.job_manager)

    try:
        recovered = asyncio.run(_run())
        assert stalled in recovered and orphan in recovered and running not in recovered
        with engine.connect() as c:
            statuses = dict(
                c.execute(
                    text("SELECT id, status::text FROM procrastinate_jobs WHERE id = ANY(:ids)"),
                    {"ids": list(ids)},
                ).all()
            )
        assert statuses == {stalled: "failed", orphan: "failed", running: "doing"}
    finally:
        with engine.begin() as c:
            c.execute(
                text("DELETE FROM procrastinate_jobs WHERE id = ANY(:ids)"), {"ids": list(ids)}
            )
            c.execute(
                text("DELETE FROM procrastinate_workers WHERE id IN (:a, :b)"),
                {"a": dead, "b": alive},
            )

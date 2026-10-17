# SPDX-License-Identifier: Apache-2.0
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from sqlalchemy import text

from app import observability

pytestmark = pytest.mark.postgis


def _read_backlog(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "geostudio.jobs.backlog":
                    return {dp.attributes["queue"]: dp.value for dp in metric.data.data_points}
    return {}


def test_jobs_backlog_gauge_counts_todo_and_doing_per_queue(pg_engine_with_procrastinate_schema):
    engine = pg_engine_with_procrastinate_schema
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, status) VALUES "
                "('ingestion', 't1', 'todo'), ('ingestion', 't2', 'doing'), "
                "('search', 't3', 'todo'), ('ingestion', 't4', 'succeeded'), "
                "('search', 't5', 'failed')"
            )
        )

    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_jobs_backlog_gauge(engine, meter=meter)

    assert _read_backlog(reader) == {"ingestion": 2, "search": 1}


def _read(reader: InMemoryMetricReader, name: str) -> dict[str, float]:
    for resource_metrics in reader.get_metrics_data().resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    return {dp.attributes["queue"]: dp.value for dp in metric.data.data_points}
    return {}


def test_failed_and_oldest_age_gauges_cover_every_known_queue(pg_engine_with_procrastinate_schema):
    """AUD-035 : échecs sur 24 h et âge du plus ancien job exigible, un point
    par file connue (0 compris) — sinon une file vide disparaît et les règles
    en `noDataState: Alerting` sonneraient sur une instance au repos."""
    engine = pg_engine_with_procrastinate_schema
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM procrastinate_jobs"))
        conn.execute(
            text(
                "INSERT INTO procrastinate_jobs (queue_name, task_name, status) VALUES "
                "('ingestion', 'a', 'todo'), ('search', 'b', 'todo'), ('etl', 'c', 'todo'), "
                "('etl', 'd', 'todo')"
            )
        )
        # Vraies transitions : les triggers procrastinate écrivent les événements.
        conn.execute(
            text("UPDATE procrastinate_jobs SET status = 'doing' WHERE task_name IN ('b', 'c')")
        )
        conn.execute(
            text("UPDATE procrastinate_jobs SET status = 'failed' WHERE task_name IN ('b', 'c')")
        )
        conn.execute(
            text(
                "UPDATE procrastinate_events SET at = now() - interval '2 days' "
                "WHERE type = 'failed' "
                "AND job_id = (SELECT id FROM procrastinate_jobs WHERE task_name = 'c')"
            )
        )
        conn.execute(
            text(
                "UPDATE procrastinate_events SET at = now() - interval '600 seconds' "
                "WHERE type = 'deferred' "
                "AND job_id = (SELECT id FROM procrastinate_jobs WHERE task_name = 'a')"
            )
        )
        # Job planifié dans le futur : pas encore exigible, n'a pas d'âge.
        conn.execute(
            text(
                "UPDATE procrastinate_jobs SET scheduled_at = now() + interval '1 hour' "
                "WHERE task_name = 'd'"
            )
        )

    reader = InMemoryMetricReader()
    meter = MeterProvider(metric_readers=[reader]).get_meter("test")
    observability.register_jobs_backlog_gauge(engine, meter=meter)

    assert _read(reader, "geostudio.jobs.failed") == {"etl": 0, "ingestion": 0, "search": 1}
    ages = _read(reader, "geostudio.jobs.oldest_age_seconds")
    assert ages.keys() == {"etl", "ingestion", "search"}
    assert ages["etl"] == 0 and ages["search"] == 0
    assert 590 <= ages["ingestion"] <= 900
    assert _read(reader, "geostudio.jobs.backlog") == {"etl": 1, "ingestion": 1, "search": 0}

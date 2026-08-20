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

# SPDX-License-Identifier: Apache-2.0
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from procrastinate.job_context import JobContext
from procrastinate.jobs import Job

from app import observability


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_context(*, task_name="app.demo.task", queue="default", job_id=7):
    job = Job(
        id=job_id, status="doing", queue=queue, lock=None, queueing_lock=None, task_name=task_name
    )
    return JobContext(app=None, job=job, start_timestamp=0.0, abort_reason=lambda: None)


@pytest.mark.anyio
async def test_worker_middleware_wraps_job_execution_in_a_span(anyio_backend):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    middleware = observability.make_worker_middleware(tracer_provider=provider)

    async def call_next():
        return "ok"

    result = await middleware(call_next, _make_context(), worker=None)

    assert result == "ok"
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "procrastinate.job.app.demo.task"
    assert spans[0].attributes["procrastinate.job.task_name"] == "app.demo.task"
    assert spans[0].attributes["procrastinate.job.queue"] == "default"
    assert spans[0].attributes["procrastinate.job.id"] == 7
    assert spans[0].status.status_code.name == "UNSET"


@pytest.mark.anyio
async def test_worker_middleware_records_exception_and_reraises(anyio_backend):
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    middleware = observability.make_worker_middleware(tracer_provider=provider)

    async def call_next():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await middleware(call_next, _make_context(), worker=None)

    spans = exporter.get_finished_spans()
    assert spans[0].status.status_code.name == "ERROR"
    assert spans[0].events[0].name == "exception"

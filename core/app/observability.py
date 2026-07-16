# SPDX-License-Identifier: Apache-2.0
"""Instrumentation OTel du cœur — SP-10a. setup() configure les providers
process-wide une seule fois (mémoïsation module-level via _configured) :
create_app() est appelé des dizaines de fois par la suite de tests
(DATABASE_URL/CORE_AUTH_MODE différents par test), un second appel ne doit
ni lever, ni reconstruire de providers (et de toute façon, l'API OTel logue
un warning et no-op sur un second set_tracer_provider/set_meter_provider,
indépendamment de ce flag). Sans OTEL_EXPORTER_OTLP_ENDPOINT (comportement
par défaut, toute la suite de tests), aucun exportateur n'est attaché :
spans/métriques/logs sont créés mais jamais envoyés, coût négligeable, zéro
appel réseau."""
import json
import logging
import os
import sys

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_configured = False

_original_record_factory = logging.getLogRecordFactory()


def _record_factory_with_trace_context(*args, **kwargs):
    """Ajoute trace_id/span_id à chaque LogRecord au moment de sa création
    (pas au moment du format()) — un log peut être formaté après la fin du
    span actif, la capture doit donc se faire à la création. Installé par
    setup(), donc uniquement actif une fois l'observabilité configurée."""
    record = _original_record_factory(*args, **kwargs)
    span_context = trace.get_current_span().get_span_context()
    record.trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
    record.span_id = format(span_context.span_id, "016x") if span_context.is_valid else None
    return record


class JSONFormatter(logging.Formatter):
    """Une ligne JSON par log, trace_id/span_id du span actif inclus (None
    si aucun span n'est actif). Toujours utilisé, endpoint OTLP configuré ou
    non — `docker compose logs` reste corrélable dans les deux cas."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "span_id": getattr(record, "span_id", None),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _otlp_endpoint() -> str | None:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")


def _build_tracer_provider(resource: Resource, endpoint: str | None) -> TracerProvider:
    provider = TracerProvider(resource=resource)
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    return provider


def _build_meter_provider(resource: Resource, endpoint: str | None) -> MeterProvider:
    metric_readers = []
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        metric_readers = [PeriodicExportingMetricReader(OTLPMetricExporter())]
    return MeterProvider(resource=resource, metric_readers=metric_readers)


def setup() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    logging.setLogRecordFactory(_record_factory_with_trace_context)

    service_name = os.environ.get("OTEL_SERVICE_NAME", "geostudio-core")
    resource = Resource.create({"service.name": service_name})
    endpoint = _otlp_endpoint()

    trace.set_tracer_provider(_build_tracer_provider(resource, endpoint))
    metrics.set_meter_provider(_build_meter_provider(resource, endpoint))

    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()
    BotocoreInstrumentor().instrument()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def instrument_app(app, *, tracer_provider=None) -> None:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)


def instrument_engine(engine, *, tracer_provider=None) -> None:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=tracer_provider)


def make_worker_middleware(*, tracer_provider=None):
    from opentelemetry.trace import Status, StatusCode

    tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer(__name__)

    async def _otel_worker_middleware(call_next, context, worker):
        job = context.job
        with tracer.start_as_current_span(
            f"procrastinate.job.{job.task_name}",
            attributes={
                "procrastinate.job.id": job.id if job.id is not None else -1,
                "procrastinate.job.task_name": job.task_name,
                "procrastinate.job.queue": job.queue,
            },
        ) as span:
            try:
                return await call_next()
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise

    return _otel_worker_middleware


otel_worker_middleware = make_worker_middleware()

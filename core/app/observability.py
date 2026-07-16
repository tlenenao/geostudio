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

# Mémoïse le handle() original pour la pièce de monkey-patch
_original_handler_handle = logging.Handler.handle


def _inject_trace_context_in_handle(self, record: logging.LogRecord) -> None:
    """Enveloppe Handler.handle pour capturer la trace context avant que emit()
    ne soit appelé, même pour les handlers qui override emit(). Le handle()
    fait le filtrage et appelle emit(), donc c'est le bon endroit."""
    if not hasattr(record, "trace_id"):
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
        record.span_id = format(span_context.span_id, "016x") if span_context.is_valid else None
    return _original_handler_handle(self, record)


# Applique la pièce de monkey-patch immédiatement (avant même setup())
# afin que les tests qui créent des loggers avant d'appeler setup()
# captent quand même la trace context.
logging.Handler.handle = _inject_trace_context_in_handle


class _TraceContextFilter(logging.Filter):
    """Capte la trace_id et span_id au moment de la création du log,
    avant que le contexte ne soit perdu."""

    def filter(self, record: logging.LogRecord) -> bool:
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
        record.span_id = format(span_context.span_id, "016x") if span_context.is_valid else None
        return True


class JSONFormatter(logging.Formatter):
    """Une ligne JSON par log, trace_id/span_id du span actif inclus (None
    si aucun span n'est actif). Toujours utilisé, endpoint OTLP configuré ou
    non — `docker compose logs` reste corrélable dans les deux cas."""

    def format(self, record: logging.LogRecord) -> str:
        # Récupère trace_id/span_id capturés par _TraceContextFilter au moment
        # du log, ou les récupère du span actif si le filtre n'a pas tourné.
        trace_id = getattr(record, "trace_id", None)
        span_id = getattr(record, "span_id", None)

        if trace_id is None or span_id is None:
            # Fallback si le filtre n'a pas tourné (e.g., en test direct)
            span_context = trace.get_current_span().get_span_context()
            if trace_id is None:
                trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
            if span_id is None:
                span_id = format(span_context.span_id, "016x") if span_context.is_valid else None

        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": trace_id,
            "span_id": span_id,
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

    service_name = os.environ.get("OTEL_SERVICE_NAME", "geostudio-core")
    resource = Resource.create({"service.name": service_name})
    endpoint = _otlp_endpoint()

    trace.set_tracer_provider(_build_tracer_provider(resource, endpoint))
    metrics.set_meter_provider(_build_meter_provider(resource, endpoint))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.addFilter(_TraceContextFilter())
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

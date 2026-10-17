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

import contextvars
import json
import logging
import os
import re
import sys
import uuid
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

_configured = False

_original_record_factory = logging.getLogRecordFactory()

# AUD-040 : identifiant de requête — repris de l'amont (Traefik, client) s'il
# est sûr à recopier dans un en-tête/log, sinon généré.
_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_REQUEST_ID_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def current_request_id() -> str | None:
    return _request_id.get()


class RequestIdMiddleware:
    """ASGI pur (pas BaseHTTPMiddleware) : pose X-Request-ID sur la réponse,
    l'attribut `http.request_id` sur le span serveur et le contextvar lu par
    les logs. Le contextvar n'est jamais réinitialisé : le gestionnaire de 500
    (ServerErrorMiddleware, hors de cette pile) le relit après l'exception."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"")
        try:
            candidate = incoming.decode("ascii")
        except UnicodeDecodeError:
            candidate = ""
        rid = candidate if _REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex
        _request_id.set(rid)
        trace.get_current_span().set_attribute("http.request_id", rid)

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"x-request-id"]
                headers.append((b"x-request-id", rid.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)


def tag_current_span_with_user(user: Any) -> None:
    """Tenant et utilisateur sur le span serveur (AUD-040) — identifiants
    internes, jamais l'e-mail ni le nom."""
    span = trace.get_current_span()
    span.set_attribute("enduser.id", str(user.id))
    span.set_attribute("geostudio.tenant_id", str(user.tenant_id))


def _record_factory_with_trace_context(*args, **kwargs):
    """Ajoute trace_id/span_id à chaque LogRecord au moment de sa création
    (pas au moment du format()) — un log peut être formaté après la fin du
    span actif, la capture doit donc se faire à la création. Installé par
    setup(), donc uniquement actif une fois l'observabilité configurée."""
    record = _original_record_factory(*args, **kwargs)
    span_context = trace.get_current_span().get_span_context()
    record.trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else None
    record.span_id = format(span_context.span_id, "016x") if span_context.is_valid else None
    record.request_id = _request_id.get()
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
            "request_id": getattr(record, "request_id", None),
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


def _build_resource() -> Resource:
    """service.version (GEOSTUDIO_VERSION, tag d'image) et
    deployment.environment (CORE_ENV, vide = production) : sans eux, une
    trace ou un log ne dit pas quelle version l'a émis (AUD-040)."""
    return Resource.create(
        {
            "service.name": os.environ.get("OTEL_SERVICE_NAME", "geostudio-core"),
            "service.version": os.environ.get("GEOSTUDIO_VERSION") or "dev",
            "deployment.environment": os.environ.get("CORE_ENV") or "production",
        }
    )


def _build_logger_provider(resource: Resource, endpoint: str | None):
    """Export OTLP des logs (→ Loki d'otel-lgtm), AUD-036 — None sans
    endpoint : les logs restent alors seulement sur stdout (JSONFormatter)."""
    if not endpoint:
        return None
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    return provider


def setup() -> None:
    global _configured
    if _configured:
        return
    _configured = True
    logging.setLogRecordFactory(_record_factory_with_trace_context)

    resource = _build_resource()
    endpoint = _otlp_endpoint()

    trace.set_tracer_provider(_build_tracer_provider(resource, endpoint))
    metrics.set_meter_provider(_build_meter_provider(resource, endpoint))
    logger_provider = _build_logger_provider(resource, endpoint)

    from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument()
    BotocoreInstrumentor().instrument()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    if logger_provider is not None:
        from opentelemetry.sdk._logs import LoggingHandler

        otlp_handler = LoggingHandler(logger_provider=logger_provider)
        # Un échec d'export OTLP se journalise lui-même : ne pas le réexporter
        # (boucle tant que le collecteur est injoignable) — il reste sur stdout.
        otlp_handler.addFilter(lambda r: not r.name.startswith("opentelemetry"))
        root_logger.addHandler(otlp_handler)


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


# Une ligne par file CONNUE (présente dans procrastinate_jobs), valeur 0
# comprise : une file vide qui disparaîtrait de la série ferait sonner les
# règles en `noDataState: Alerting` sur une instance au repos (SP-L3).
# ponytail: GROUP BY sur toute la table à chaque tick d'export (aucune purge
# de procrastinate_jobs aujourd'hui) ; index/purge si le tick ralentit.
_JOBS_GAUGES_SQL = {
    "geostudio.jobs.backlog": (
        "SELECT queue_name, COUNT(*) FILTER (WHERE status IN ('todo', 'doing')) "
        "FROM procrastinate_jobs GROUP BY queue_name",
        "Jobs procrastinate en attente ou en cours, par file",
        "",
    ),
    "geostudio.jobs.failed": (
        "SELECT j.queue_name, COUNT(DISTINCT j.id) FILTER ("
        "WHERE j.status = 'failed' AND e.at > now() - interval '24 hours') "
        "FROM procrastinate_jobs j LEFT JOIN procrastinate_events e "
        "ON e.job_id = j.id AND e.type = 'failed' GROUP BY j.queue_name",
        "Jobs procrastinate passés en échec dans les dernières 24 heures, par file",
        "",
    ),
    "geostudio.jobs.oldest_age_seconds": (
        "SELECT j.queue_name, COALESCE(EXTRACT(EPOCH FROM now() "
        "- MIN(COALESCE(j.scheduled_at, e.at)) FILTER (WHERE j.status = 'todo' "
        "AND (j.scheduled_at IS NULL OR j.scheduled_at <= now()))), 0) "
        "FROM procrastinate_jobs j LEFT JOIN procrastinate_events e "
        "ON e.job_id = j.id AND e.type = 'deferred' GROUP BY j.queue_name",
        "Âge du plus ancien job exigible en attente d'un worker, par file",
        "s",
    ),
}


def register_jobs_backlog_gauge(engine, *, meter=None) -> None:
    """ObservableGauges geostudio.jobs.{backlog,failed,oldest_age_seconds},
    un point de données par file (attribut `queue`, cf. _JOBS_GAUGES_SQL) —
    backlog compte les lignes procrastinate_jobs en statut todo/doing
    (SP-10b) ; failed et oldest_age_seconds ajoutés par SP-L3 (AUD-035).
    Callback appelé paresseusement à chaque tick d'export du
    PeriodicExportingMetricReader (déjà posé par setup(), SP-10a) — aucune
    nouvelle boucle de polling, aucun nouveau thread.

    unit="" et pas "1" : un ObservableGauge avec unit="1" se traduit côté
    Prometheus par un nom suffixé _ratio (convention de nommage OTel→
    Prometheus : l'unité UCUM "1" est interprétée comme un ratio sur les
    gauges) — vérifié empiriquement en faisant transiter la métrique par un
    vrai collecteur. geostudio.jobs.backlog est un compte, pas un ratio ;
    unit="" produit le nom geostudio_jobs_backlog attendu par les dashboards
    et règles d'alerte (Tasks 4/5)."""
    from opentelemetry.metrics import Observation
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError

    meter = meter or metrics.get_meter(__name__)

    def _make_callback(sql: str):
        def _callback(options):
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text(sql))
                    return [Observation(float(v), {"queue": queue}) for queue, v in rows]
            except ProgrammingError:
                # procrastinate_jobs peut ne pas encore exister (worker pas
                # encore démarré / `schema --apply` pas encore joué) — le
                # endpoint OTLP étant désormais inconditionnel (SP-10b Task 1),
                # ce callback tourne à chaque tick d'export dans tout
                # déploiement, y compris avant que la table existe. On ne
                # laisse pas cette exception remonter du callback ; le prochain
                # tick réessaiera une fois la table créée.
                return []

        return _callback

    for name, (sql, description, unit) in _JOBS_GAUGES_SQL.items():
        meter.create_observable_gauge(
            name, callbacks=[_make_callback(sql)], unit=unit, description=description
        )


def register_cdc_lag_gauge(get_lag_seconds, *, meter=None) -> None:
    """ObservableGauge geostudio.cdc.lag_seconds (SP-11a), un point de donnée
    par collection (attribut collection_id) — écart en secondes entre
    l'horloge murale et l'horodatage du dernier flush GeoParquet réussi pour
    cette collection. `get_lag_seconds` est un callable fourni par le
    cdc-worker (état en mémoire du process, pas une requête DB —
    contrairement à register_jobs_backlog_gauge) qui retourne
    {collection_id: lag_secondes} à l'instant de l'appel ; c'est lui qui
    calcule time.time() - last_flush_ts, pas ce module, pour rester
    testable sans horloge réelle (cf. test_observability_cdc_lag.py)."""
    from opentelemetry.metrics import Observation

    meter = meter or metrics.get_meter(__name__)

    def _callback(options):
        return [
            Observation(lag, {"collection_id": collection_id})
            for collection_id, lag in get_lag_seconds().items()
        ]

    meter.create_observable_gauge(
        "geostudio.cdc.lag_seconds",
        callbacks=[_callback],
        unit="s",
        description=(
            "Écart entre l'horloge murale et le dernier flush GeoParquet réussi, par collection"
        ),
    )

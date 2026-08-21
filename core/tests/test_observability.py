# SPDX-License-Identifier: Apache-2.0
import json
import logging

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

from app import observability


def test_build_tracer_provider_without_endpoint_has_no_span_processor():
    provider = observability._build_tracer_provider(Resource.create({"service.name": "x"}), None)
    assert provider._active_span_processor._span_processors == ()


def test_build_tracer_provider_with_endpoint_attaches_a_span_processor():
    provider = observability._build_tracer_provider(
        Resource.create({"service.name": "x"}),
        "http://localhost:4318",
    )
    assert len(provider._active_span_processor._span_processors) == 1


def test_setup_only_builds_providers_once(monkeypatch):
    monkeypatch.setattr(observability, "_configured", False)
    calls = {"n": 0}
    original = observability._build_tracer_provider

    def counting_build(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(observability, "_build_tracer_provider", counting_build)
    observability.setup()
    observability.setup()
    assert calls["n"] == 1


def test_json_formatter_includes_trace_and_span_id_when_a_span_is_active():
    # TracerProvider local, pas le global : ce test ne doit pas dépendre de
    # si observability.setup() a déjà tourné ailleurs dans la session pytest.
    observability.setup()
    tracer = SDKTracerProvider().get_tracer(__name__)
    record_holder: dict = {}

    class _Capture(logging.Handler):
        def emit(self, record):
            record_holder["record"] = record

    logger = logging.getLogger("test_observability_capture")
    logger.setLevel(logging.INFO)
    logger.addHandler(_Capture())
    logger.propagate = False

    with tracer.start_as_current_span("test-span") as span:
        logger.info("hello")
        expected_trace_id = format(span.get_span_context().trace_id, "032x")
        expected_span_id = format(span.get_span_context().span_id, "016x")

    formatted = observability.JSONFormatter().format(record_holder["record"])
    payload = json.loads(formatted)
    assert payload["message"] == "hello"
    assert payload["trace_id"] == expected_trace_id
    assert payload["span_id"] == expected_span_id


def test_json_formatter_has_null_ids_without_an_active_span():
    record = logging.LogRecord(
        name="x",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="no span",
        args=(),
        exc_info=None,
    )
    payload = json.loads(observability.JSONFormatter().format(record))
    assert payload["trace_id"] is None
    assert payload["span_id"] is None

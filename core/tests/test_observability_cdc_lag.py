# SPDX-License-Identifier: Apache-2.0
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

from app import observability


def _read_lag(reader: InMemoryMetricReader) -> dict[str, float]:
    data = reader.get_metrics_data()
    if not data:
        return {}
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "geostudio.cdc.lag_seconds":
                    return {
                        dp.attributes["collection_id"]: dp.value for dp in metric.data.data_points
                    }
    return {}


def test_cdc_lag_gauge_reports_per_collection_lag():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_cdc_lag_gauge(lambda: {"parcelles": 12.5, "routes": 3.0}, meter=meter)

    assert _read_lag(reader) == {"parcelles": 12.5, "routes": 3.0}


def test_cdc_lag_gauge_reports_empty_when_no_collection_tracked():
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader])
    meter = provider.get_meter("test")

    observability.register_cdc_lag_gauge(lambda: {}, meter=meter)

    assert _read_lag(reader) == {}

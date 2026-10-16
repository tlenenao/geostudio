# SPDX-License-Identifier: Apache-2.0
"""REV-119 : métriques nommées d'un dataset (schéma + résolution)."""

import pytest
from pydantic import ValidationError

from app.analytics.aggregate import (
    METRIC_AGGS,
    AggregateMeasure,
    AggregateRequestBody,
    UnknownAggregateField,
    _agg_expr,
    resolve_metrics,
)
from app.configs.schemas import BuilderConfig, DatasetMetric


def _body(metrics: dict) -> dict:
    return {
        "version": 1,
        "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": "c", "metrics": metrics},
    }


def test_metrics_valides_roundtrip():
    cfg = BuilderConfig.model_validate(
        _body({"recettes": {"field": "montant", "agg": "sum", "unit": "EUR"}})
    )
    assert cfg.dataset.metrics["recettes"].agg == "sum"
    assert BuilderConfig.model_validate(cfg.model_dump())


def test_defaut_vide():
    assert BuilderConfig.model_validate(_body({})).dataset.metrics == {}


@pytest.mark.parametrize(
    "metrics",
    [
        {"Bad-Key": {"agg": "count"}},
        {"1abc": {"agg": "count"}},
        {"m": {"agg": "sum"}},  # field requis
        {"m": {"agg": "nope", "field": "x"}},
        {"m": {"agg": "percentile", "field": "x"}},  # p requis
        {"m": {"agg": "sum", "field": "x", "p": 50}},  # p interdit
        {"m": {"agg": "percentile", "field": "x", "p": 100}},
        {f"m{i}": {"agg": "count"} for i in range(51)},
    ],
)
def test_metrics_invalides_rejetees(metrics):
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_body(metrics))


def test_count_sans_field_et_percentile_ok():
    BuilderConfig.model_validate(
        _body({"n": {"agg": "count"}, "p90": {"agg": "percentile", "field": "x", "p": 90}})
    )


def test_aggs_alignes_sur_agg_expr():
    for agg in METRIC_AGGS:
        _agg_expr(agg, "f", 50.0 if agg == "percentile" else None)


def test_resolve_metrics_remplace_et_libelle_par_cle():
    metrics = {"rec": DatasetMetric(field="montant", agg="sum", label="Recettes")}
    req = AggregateRequestBody(
        groupBy="commune",
        measures=[AggregateMeasure(metric="rec"), AggregateMeasure(agg="count", label="n")],
    )
    out = resolve_metrics(req, metrics)
    m0, m1 = out.measures
    assert (m0.field, m0.agg, m0.label, m0.metric) == ("montant", "sum", "rec", None)
    assert m1.label == "n"


def test_resolve_metrics_label_explicite_conserve():
    metrics = {"rec": DatasetMetric(field="montant", agg="sum")}
    out = resolve_metrics(
        AggregateRequestBody(measures=[AggregateMeasure(metric="rec", label="x")]), metrics
    )
    assert out.measures[0].label == "x"


def test_resolve_metrics_inconnue_refusee():
    with pytest.raises(UnknownAggregateField):
        resolve_metrics(AggregateRequestBody(measures=[AggregateMeasure(metric="zz")]), {})


def test_resolve_sans_metric_identite():
    req = AggregateRequestBody(agg="count")
    assert resolve_metrics(req, {}) is req

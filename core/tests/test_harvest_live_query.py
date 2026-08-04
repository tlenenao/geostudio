# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.harvest import live_query


@pytest.fixture(autouse=True)
def _clear_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def test_translate_features_query_builds_where_from_filters():
    params = live_query.translate_features_query(
        filters={"statut": "actif", "annee__gte": "2020", "annee__lte": "2024", "type__in": "a,b"},
        bbox=None, limit=50, offset=10,
    )
    assert "statut = 'actif'" in params["where"]
    assert "annee >= '2020'" in params["where"]
    assert "annee <= '2024'" in params["where"]
    assert "type IN ('a', 'b')" in params["where"]
    assert params["resultRecordCount"] == "50"
    assert params["resultOffset"] == "10"
    assert params["f"] == "geojson"
    assert params["outFields"] == "*"
    assert "geometry" not in params


def test_translate_features_query_no_filters_is_1_equals_1():
    params = live_query.translate_features_query(filters={}, bbox=None, limit=100, offset=0)
    assert params["where"] == "1=1"


def test_translate_features_query_bbox_adds_envelope_params():
    params = live_query.translate_features_query(
        filters={}, bbox=(1.0, 2.0, 3.0, 4.0), limit=100, offset=0,
    )
    assert params["geometry"] == "1.0,2.0,3.0,4.0"
    assert params["geometryType"] == "esriGeometryEnvelope"
    assert params["inSR"] == "4326"
    assert params["spatialRel"] == "esriSpatialRelIntersects"


def test_translate_features_query_escapes_single_quotes():
    params = live_query.translate_features_query(
        filters={"nom": "l'école"}, bbox=None, limit=10, offset=0,
    )
    assert "l''école" in params["where"]


def test_translate_features_query_rejects_invalid_field_name():
    with pytest.raises(live_query.ArcgisQueryError):
        live_query.translate_features_query(
            filters={"1) OR (1=1--": "x"}, bbox=None, limit=10, offset=0,
        )


def test_translate_aggregate_query_count_no_groupby():
    params = live_query.translate_aggregate_query(
        group_by=[], measures=[("count", None, "total")], filters={}, bbox=None,
    )
    assert params["f"] == "json"
    assert "groupByFieldsForStatistics" not in params
    stats = params["outStatistics"]
    assert '"statisticType": "count"' in stats or "'statisticType': 'count'" in stats or "statisticType" in stats


def test_translate_aggregate_query_groupby_single_field():
    params = live_query.translate_aggregate_query(
        group_by=["commune"], measures=[("sum", "population", "total_pop")], filters={}, bbox=None,
    )
    assert params["groupByFieldsForStatistics"] == "commune"


def test_translate_aggregate_query_groupby_multi_field():
    params = live_query.translate_aggregate_query(
        group_by=["commune", "annee"], measures=[("count", None, "n")], filters={}, bbox=None,
    )
    assert params["groupByFieldsForStatistics"] == "commune,annee"


def test_translate_aggregate_query_unknown_agg_raises():
    with pytest.raises(live_query.ArcgisQueryError):
        live_query.translate_aggregate_query(
            group_by=[], measures=[("median", "x", "m")], filters={}, bbox=None,
        )


def test_translate_aggregate_query_non_count_without_field_raises():
    with pytest.raises(live_query.ArcgisQueryError):
        live_query.translate_aggregate_query(
            group_by=[], measures=[("sum", None, "m")], filters={}, bbox=None,
        )


def test_fetch_query_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://gis.example.com/FeatureServer/0/query")
        return httpx.Response(200, json={"features": [{"attributes": {"a": 1}}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    data = live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert data == {"features": [{"attributes": {"a": 1}}]}


def test_fetch_query_caches_within_ttl(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"features": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    clock = {"t": 1000.0}
    monkeypatch.setattr(live_query.time, "monotonic", lambda: clock["t"])

    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert calls["n"] == 1  # deuxième appel servi par le cache

    clock["t"] += live_query._CACHE_TTL_SECONDS + 1
    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert calls["n"] == 2  # TTL expiré, nouvel appel réseau


def test_aggregate_response_no_groupby_single_row():
    raw = {"features": [{"attributes": {"m0": 42}}]}
    key, rows = live_query.aggregate_response(raw, group_by=[], measures=[("count", None, "total")])
    assert key == "group"
    assert rows == [{"group": "Total", "total": 42}]


def test_aggregate_response_single_groupby_field():
    raw = {"features": [
        {"attributes": {"commune": "Metz", "m0": 3}},
        {"attributes": {"commune": "Nancy", "m0": 7}},
    ]}
    key, rows = live_query.aggregate_response(
        raw, group_by=["commune"], measures=[("count", None, "n")],
    )
    assert key == "commune"
    assert rows == [{"commune": "Metz", "n": 3}, {"commune": "Nancy", "n": 7}]


def test_aggregate_response_multi_groupby_fields():
    raw = {"features": [{"attributes": {"commune": "Metz", "annee": 2020, "m0": 3}}]}
    key, rows = live_query.aggregate_response(
        raw, group_by=["commune", "annee"], measures=[("count", None, "n")],
    )
    assert key == ["commune", "annee"]
    assert rows == [{"commune": "Metz", "annee": 2020, "n": 3}]


def test_aggregate_response_no_features_empty_rows():
    key, rows = live_query.aggregate_response({"features": []}, group_by=[], measures=[("count", None, "n")])
    assert key == "group"
    assert rows == []

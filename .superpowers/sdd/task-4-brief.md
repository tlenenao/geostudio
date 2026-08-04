### Task 4: Core — `app/harvest/live_query.py` (pure translation + cache, no HTTP routes yet)

**Files:**
- Create: `core/app/harvest/live_query.py`
- Test: `core/tests/test_harvest_live_query.py` (new)

**Interfaces:**
- Produces (consumed by Task 5):
  - `class ArcgisQueryError(Exception)` with `.field: str`, `.message: str`.
  - `translate_features_query(*, filters: dict[str, str], bbox: tuple[float,float,float,float] | None, limit: int, offset: int) -> dict[str, str]`
  - `translate_aggregate_query(*, group_by: list[str], measures: list[tuple[str, str | None, str]], filters: dict[str, str], bbox: tuple[float,float,float,float] | None) -> dict[str, str]` — `measures` is `(agg, field, label)` triples; raises `ArcgisQueryError` for an unknown `agg` or a non-`count` agg with no field.
  - `fetch_query(client: httpx.Client, external_url: str, params: dict[str, str]) -> dict` — TTL-cached (20s), keyed by `external_url` + sorted params.
  - `aggregate_response(raw: dict, *, group_by: list[str], measures: list[tuple[str, str | None, str]]) -> tuple[str | list[str], list[dict]]`

- [ ] **Step 1: Write the failing unit tests**

Create `core/tests/test_harvest_live_query.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.live_query'`.

- [ ] **Step 3: Implement `core/app/harvest/live_query.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Traduction de requêtes génériques (filtres __gte/__lte/__in, bbox,
pagination, groupBy/mesures) vers l'API REST ArcGIS Feature Service, pour un
dataset source="arcgis" (SP-14k) — lecture live, sans copie locale. Les
requêtes sortantes utilisent le client HTTP injecté par la route appelante
(gardé par le même egress guard que le moissonnage, SP-12d, egress.py)."""
import json
import time
from urllib.parse import urlencode

import httpx

_CACHE_TTL_SECONDS = 20.0
_RANGE_OPS = {"__gte": ">=", "__lte": "<="}
_STAT_TYPES = {"count", "sum", "avg", "min", "max"}

_cache: dict[str, tuple[float, dict]] = {}


class ArcgisQueryError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_where(filters: dict[str, str]) -> str:
    clauses = []
    for raw_name, value in sorted(filters.items()):
        name, suffix = _split_filter_key(raw_name)
        if suffix == "__in":
            values = value.split(",")
            clauses.append(f"{name} IN ({', '.join(_sql_lit(v) for v in values)})")
        elif suffix in _RANGE_OPS:
            clauses.append(f"{name} {_RANGE_OPS[suffix]} {_sql_lit(value)}")
        else:
            clauses.append(f"{name} = {_sql_lit(value)}")
    return " AND ".join(clauses) if clauses else "1=1"


def _bbox_params(bbox: tuple[float, float, float, float] | None) -> dict[str, str]:
    if bbox is None:
        return {}
    minx, miny, maxx, maxy = bbox
    return {
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def translate_features_query(
    *, filters: dict[str, str], bbox: tuple[float, float, float, float] | None,
    limit: int, offset: int,
) -> dict[str, str]:
    return {
        "where": _build_where(filters),
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": str(limit),
        "resultOffset": str(offset),
        **_bbox_params(bbox),
    }


def translate_aggregate_query(
    *, group_by: list[str], measures: list[tuple[str, str | None, str]],
    filters: dict[str, str], bbox: tuple[float, float, float, float] | None,
) -> dict[str, str]:
    out_statistics = []
    for i, (agg, field, _label) in enumerate(measures):
        if agg not in _STAT_TYPES:
            raise ArcgisQueryError("agg", f"unknown agg '{agg}'")
        if agg != "count" and field is None:
            raise ArcgisQueryError("field", f"agg '{agg}' requires a field")
        out_statistics.append({
            "statisticType": agg,
            "onStatisticField": field or "1",
            "outStatisticFieldName": f"m{i}",
        })
    params: dict[str, str] = {
        "where": _build_where(filters),
        "outStatistics": json.dumps(out_statistics),
        "f": "json",
        **_bbox_params(bbox),
    }
    if group_by:
        params["groupByFieldsForStatistics"] = ",".join(group_by)
    return params


def _cache_key(external_url: str, params: dict[str, str]) -> str:
    return f"{external_url}?{urlencode(sorted(params.items()))}"


def fetch_query(client: httpx.Client, external_url: str, params: dict[str, str]) -> dict:
    key = _cache_key(external_url, params)
    cached = _cache.get(key)
    if cached is not None:
        expires_at, value = cached
        if time.monotonic() < expires_at:
            return value
        del _cache[key]
    response = client.get(f"{external_url}/query", params=params)
    response.raise_for_status()
    data = response.json()
    _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, data)
    return data


def aggregate_response(
    raw: dict, *, group_by: list[str], measures: list[tuple[str, str | None, str]],
) -> tuple[str | list[str], list[dict]]:
    features = raw.get("features", [])
    if not group_by:
        if not features:
            return "group", []
        attrs = features[0].get("attributes", {})
        row = {"group": "Total"}
        for i, (_agg, _field, label) in enumerate(measures):
            row[label] = attrs.get(f"m{i}")
        return "group", [row]
    if len(group_by) == 1:
        field = group_by[0]
        rows = []
        for feat in features:
            attrs = feat.get("attributes", {})
            row: dict = {field: str(attrs.get(field))}
            for i, (_agg, _field, label) in enumerate(measures):
                row[label] = attrs.get(f"m{i}")
            rows.append(row)
        return field, rows
    rows = []
    for feat in features:
        attrs = feat.get("attributes", {})
        row = {f: attrs.get(f) for f in group_by}
        for i, (_agg, _field, label) in enumerate(measures):
            row[label] = attrs.get(f"m{i}")
        rows.append(row)
    return group_by, rows
```

- [ ] **Step 4: Run to verify all tests pass**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/live_query.py tests/test_harvest_live_query.py
git commit -m "feat(core): live_query translates filters/bbox/groupBy to ArcGIS REST (SP-14k)"
```

---


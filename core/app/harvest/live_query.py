# SPDX-License-Identifier: Apache-2.0
"""Traduction de requêtes génériques (filtres __gte/__lte/__in, bbox,
pagination, groupBy/mesures) vers l'API REST ArcGIS Feature Service, pour un
dataset source="arcgis" (SP-14k) — lecture live, sans copie locale. Les
requêtes sortantes utilisent le client HTTP injecté par la route appelante
(gardé par le même egress guard que le moissonnage, SP-12d, egress.py)."""
import json
import re
import time
from urllib.parse import urlencode

import httpx

_CACHE_TTL_SECONDS = 20.0
_RANGE_OPS = {"__gte": ">=", "__lte": "<="}
_STAT_TYPES = {"count", "sum", "avg", "min", "max"}
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

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
        if not _FIELD_NAME_RE.match(name):
            raise ArcgisQueryError(raw_name, f"invalid filter field name '{name}'")
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
        if field is not None and not _FIELD_NAME_RE.match(field):
            raise ArcgisQueryError(field, f"invalid measure field name '{field}'")
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
        for field_name in group_by:
            if not _FIELD_NAME_RE.match(field_name):
                raise ArcgisQueryError(field_name, f"invalid groupBy field name '{field_name}'")
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

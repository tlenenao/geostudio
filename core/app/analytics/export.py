# SPDX-License-Identifier: Apache-2.0
"""Sérialisation d'export (SP-16a) : lignes attributaires (mode agrégé,
sans géométrie par construction) ou features GeoJSON (mode entités brutes)
vers CSV/XLSX/GeoJSON/GPKG. Fonctions pures, réutilisables telles quelles
par SP-16b (rapports planifiés) sans passer par un appel HTTP interne."""

import json
import re
import tempfile
import unicodedata
from csv import DictWriter
from datetime import UTC, date, datetime, time
from decimal import Decimal
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from uuid import UUID

import duckdb
from openpyxl import Workbook

EXPORT_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "geojson": "application/geo+json",
    "gpkg": "application/geopackage+sqlite3",
}


def _json_default(value: object) -> str | None:
    """Encodeur de repli pour json.dumps() sur des properties issues de psycopg
    brut (contrairement à GET /collections/{id}/items, protégé par
    jsonable_encoder de FastAPI) : date/datetime/time -> isoformat,
    Decimal/UUID -> str, bytes/memoryview -> None (binaire non représentable
    en JSON/GeoJSON)."""
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return None
    raise TypeError(f"unserializable value of type {type(value).__name__}")


def _xlsx_cell_value(value: object) -> object:
    """Coercition avant écriture d'une cellule (rows_to_xlsx) : openpyxl gère
    nativement str/int/float/bool/None/date/Decimal/datetime naïf, mais
    rejette les datetime tz-aware, les dict/list/tuple, et — comme colonnes
    Postgres uuid/bytea remontées brutes par psycopg — UUID et bytes/
    memoryview (mêmes choix de coercition que _json_default ci-dessus)."""
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (bytes, memoryview)):
        return None
    return value


def export_filename(title: str, *, format: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower() or "export"
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{stamp}.{format}"


def rows_to_csv(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    buf = StringIO()
    writer = DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def rows_to_xlsx(rows: list[dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([_xlsx_cell_value(row.get(h)) for h in headers])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rows_to_format(rows: list[dict[str, Any]], *, format: str) -> bytes:
    if format == "csv":
        return rows_to_csv(rows)
    if format == "xlsx":
        return rows_to_xlsx(rows)
    raise ValueError(f"unsupported row format '{format}'")


def features_to_geojson(features: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        default=_json_default,
    ).encode("utf-8")


def features_to_gpkg(features: list[dict[str, Any]], conn: duckdb.DuckDBPyConnection) -> bytes:
    with tempfile.TemporaryDirectory() as scratch_dir:
        in_path = Path(scratch_dir) / "in.geojson"
        out_path = Path(scratch_dir) / "out.gpkg"
        in_path.write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, default=_json_default),
        )
        conn.execute(f"CREATE TABLE t AS SELECT * FROM ST_Read('{in_path}')")
        conn.execute("ALTER TABLE t DROP COLUMN OGC_FID")
        conn.execute(f"COPY t TO '{out_path}' WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:4326')")
        return out_path.read_bytes()


def features_to_format(
    features: list[dict[str, Any]], *, format: str, conn: duckdb.DuckDBPyConnection | None = None
) -> bytes:
    if format in ("csv", "xlsx"):
        return rows_to_format([f.get("properties") or {} for f in features], format=format)
    if format == "geojson":
        return features_to_geojson(features)
    if format == "gpkg":
        assert conn is not None, "features_to_format(format='gpkg') requires a duckdb connection"
        return features_to_gpkg(features, conn)
    raise ValueError(f"unsupported feature format '{format}'")

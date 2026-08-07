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
from datetime import datetime, timezone
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import Workbook

EXPORT_MEDIA_TYPES = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "geojson": "application/geo+json",
    "gpkg": "application/geopackage+sqlite3",
}


def export_filename(title: str, *, format: str) -> str:
    normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower() or "export"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{slug}-{stamp}.{format}"


def rows_to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = StringIO()
    writer = DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def rows_to_xlsx(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([row.get(h) for h in headers])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def rows_to_format(rows: list[dict], *, format: str) -> bytes:
    if format == "csv":
        return rows_to_csv(rows)
    if format == "xlsx":
        return rows_to_xlsx(rows)
    raise ValueError(f"unsupported row format '{format}'")


def features_to_geojson(features: list[dict]) -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": features}).encode("utf-8")


def features_to_gpkg(features: list[dict], conn) -> bytes:
    with tempfile.TemporaryDirectory() as scratch_dir:
        in_path = Path(scratch_dir) / "in.geojson"
        out_path = Path(scratch_dir) / "out.gpkg"
        in_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}))
        conn.execute(f"CREATE TABLE t AS SELECT * FROM ST_Read('{in_path}')")
        conn.execute("ALTER TABLE t DROP COLUMN OGC_FID")
        conn.execute(f"COPY t TO '{out_path}' WITH (FORMAT GDAL, DRIVER 'GPKG', SRS 'EPSG:4326')")
        return out_path.read_bytes()


def features_to_format(features: list[dict], *, format: str, conn=None) -> bytes:
    if format in ("csv", "xlsx"):
        return rows_to_format([f.get("properties") or {} for f in features], format=format)
    if format == "geojson":
        return features_to_geojson(features)
    if format == "gpkg":
        assert conn is not None, "features_to_format(format='gpkg') requires a duckdb connection"
        return features_to_gpkg(features, conn)
    raise ValueError(f"unsupported feature format '{format}'")

### Task 2: Serialization module `app.analytics.export`

**Files:**
- Create: `core/app/analytics/export.py`
- Test: `core/tests/test_analytics_export.py`

**Interfaces:**
- Consumes: `open_spatial_connection()` from Task 1 (test-only, for the GPKG round-trip test).
- Produces (used by Tasks 3-6):
  - `EXPORT_MEDIA_TYPES: dict[str, str]` — keys `"csv"`, `"xlsx"`, `"geojson"`, `"gpkg"`.
  - `export_filename(title: str, *, format: str) -> str`
  - `rows_to_format(rows: list[dict], *, format: str) -> bytes` — `format` must be `"csv"` or `"xlsx"`.
  - `features_to_format(features: list[dict], *, format: str, conn=None) -> bytes` — `format` one of `"csv"`/`"xlsx"`/`"geojson"`/`"gpkg"`; `conn` (a `duckdb.DuckDBPyConnection` with `spatial` loaded) is required only when `format == "gpkg"`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_analytics_export.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import json

import openpyxl
import pytest

from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    features_to_format,
    rows_to_format,
)


def test_rows_to_format_csv_has_header_and_data_rows():
    content = rows_to_format([{"region": "Nord", "pop": 10}, {"region": "Sud", "pop": 5}], format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "region,pop"
    assert "Nord,10" in text


def test_rows_to_format_csv_empty_rows_is_empty_bytes():
    assert rows_to_format([], format="csv") == b""


def test_rows_to_format_xlsx_round_trips_through_openpyxl():
    content = rows_to_format([{"region": "Nord", "pop": 10}], format="xlsx")
    import io
    wb = openpyxl.load_workbook(io.BytesIO(content))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows == [("region", "pop"), ("Nord", 10)]


def test_rows_to_format_rejects_geojson():
    with pytest.raises(ValueError):
        rows_to_format([{"a": 1}], format="geojson")


def test_features_to_format_geojson_wraps_a_feature_collection():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="geojson")
    body = json.loads(content)
    assert body == {"type": "FeatureCollection", "features": features}


def test_features_to_format_csv_flattens_properties_and_drops_geometry():
    features = [{"type": "Feature", "properties": {"nom": "X", "pop": 3}, "geometry": {"type": "Point", "coordinates": [1, 2]}}]
    content = features_to_format(features, format="csv")
    text = content.decode("utf-8")
    assert text.splitlines()[0] == "nom,pop"
    assert "geometry" not in text


def test_features_to_format_gpkg_requires_a_connection():
    with pytest.raises(AssertionError):
        features_to_format([{"type": "Feature", "properties": {}, "geometry": None}], format="gpkg")


def test_features_to_format_gpkg_round_trips_a_point():
    features = [{"type": "Feature", "properties": {"nom": "X"}, "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}]
    conn = open_spatial_connection()
    try:
        content = features_to_format(features, format="gpkg", conn=conn)
        assert content[:16] == b"SQLite format 3\x00"
        read_back = open_spatial_connection()
        try:
            with open("/tmp/sp16a_test.gpkg", "wb") as f:
                f.write(content)
            row = read_back.execute("SELECT nom FROM ST_Read('/tmp/sp16a_test.gpkg')").fetchone()
            assert row[0] == "X"
        finally:
            read_back.close()
    finally:
        conn.close()


def test_export_filename_slugifies_the_title_and_appends_the_format():
    name = export_filename("Bâtiments (2026)", format="csv")
    assert name.startswith("batiments-2026")
    assert name.endswith(".csv")


def test_export_filename_falls_back_to_export_for_an_empty_title():
    assert export_filename("", format="xlsx").startswith("export")


def test_export_media_types_cover_all_four_formats():
    assert set(EXPORT_MEDIA_TYPES) == {"csv", "xlsx", "geojson", "gpkg"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_analytics_export.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analytics.export'`

- [ ] **Step 3: Implement**

Create `core/app/analytics/export.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_analytics_export.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/export.py core/tests/test_analytics_export.py
git commit -m "feat(core): SP-16a — module de sérialisation d'export CSV/XLSX/GeoJSON/GPKG"
```

---


# SPDX-License-Identifier: Apache-2.0
"""ARC-33 × ARC-25 : op `transform.zonalStats` (raster × polygones d'une entrée de pipeline) —
mêmes portes que POST /v1/raster/{item}/zonal-stats (can(read), limites géo, plafonds)."""

from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from rasterio.mask import mask
from sqlalchemy import select

from app.audit.models import AuditLog
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import raster as raster_op
from app.pipelines.ops.contracts import OPERATIONS
from app.raster import zonal
from tests.test_raster_reader import _conn, env  # noqa: F401

SQUARE = "POLYGON((2.1 48.9, 2.3 48.9, 2.3 48.7, 2.1 48.7, 2.1 48.9))"


def _run(conn, env, user, params=None, srid=4326):  # noqa: F811
    s = env[0]
    OPERATIONS["transform.zonalStats"].execute(
        conn,
        input_view="src",
        view_name="out",
        params={"itemId": env[2], "stats": ["count", "mean", "max"], **(params or {})},
        secret_resolver=SimpleNamespace(session=s, user=user),
        preview=False,
        input_srid=srid,
    )
    return conn.execute("SELECT name, zonal_count, zonal_mean, zonal_max FROM out").fetchall()


def _src(conn, rows):
    conn.execute("CREATE TABLE src (name VARCHAR, geometry GEOMETRY)")
    for name, wkt in rows:
        conn.execute("INSERT INTO src VALUES (?, ST_GeomFromText(?))", [name, wkt])


def test_matches_rasterio_reference_and_keeps_non_polygons(env, tmp_path):  # noqa: F811
    conn = _conn()
    _src(conn, [("carre", SQUARE), ("point", "POINT(2.2 48.8)")])
    rows = _run(conn, env, env[3])
    with rasterio.open(str(tmp_path / "a.tif")) as ds:
        data, _ = mask(
            ds,
            [
                {
                    "type": "Polygon",
                    "coordinates": [[[2.1, 48.9], [2.3, 48.9], [2.3, 48.7], [2.1, 48.7]]],
                }
            ],
            crop=True,
            filled=False,
            indexes=1,
        )
    ref = np.ma.compressed(data)
    assert rows[0][0] == "carre" and rows[0][1] == ref.size
    assert abs(rows[0][2] - float(ref.mean(dtype=np.float64))) < 1e-6
    assert rows[0][3] == float(ref.max())
    assert rows[1] == ("point", None, None, None)


def test_input_srid_is_honoured(env):  # noqa: F811
    conn = _conn()
    _src(conn, [("carre", SQUARE)])
    ref = _run(conn, env, env[3])
    conn2 = _conn()
    conn2.execute("CREATE TABLE src (name VARCHAR, geometry GEOMETRY)")
    conn2.execute(
        "INSERT INTO src SELECT 'carre', ST_Transform(ST_GeomFromText(?), 'EPSG:4326', "
        "'EPSG:3857', always_xy := true)",
        [SQUARE],
    )
    got = _run(conn2, env, env[3], srid=3857)
    assert got[0][1] == ref[0][1]


def test_unreadable_raster_is_not_found_and_not_audited(env):  # noqa: F811
    conn = _conn()
    _src(conn, [("carre", SQUARE)])
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _run(conn, env, env[4])  # bob : aucun droit de lecture sur l'item
    assert (
        env[0].scalars(select(AuditLog).where(AuditLog.action == "raster.zonal_stats")).all() == []
    )


def test_geo_limited_actor_is_refused(env, monkeypatch):  # noqa: F811
    conn = _conn()
    _src(conn, [("carre", SQUARE)])
    monkeypatch.setattr(raster_op, "resolve_geo_limits", lambda *a, **k: {"x": object()})
    with pytest.raises(PipelineRuntimeError, match="geo-limited"):
        _run(conn, env, env[3])


def test_polygon_cap_and_audit(env, monkeypatch):  # noqa: F811
    conn = _conn()
    _src(conn, [("a", SQUARE), ("b", SQUARE)])
    monkeypatch.setattr(zonal, "MAX_POLYGONS", 1)
    with pytest.raises(PipelineRuntimeError, match="more than 1 rows"):
        _run(conn, env, env[3])
    monkeypatch.setattr(zonal, "MAX_POLYGONS", 1000)
    _run(conn, env, env[3])
    audit = env[0].scalars(select(AuditLog).where(AuditLog.action == "raster.zonal_stats")).all()
    assert len(audit) == 1 and audit[0].payload["polygons"] == 2


def test_no_actor_is_refused(env):  # noqa: F811
    conn = _conn()
    _src(conn, [("carre", SQUARE)])
    with pytest.raises(PipelineRuntimeError, match="acteur"):
        OPERATIONS["transform.zonalStats"].execute(
            conn, input_view="src", view_name="out", params={"itemId": env[2]}
        )

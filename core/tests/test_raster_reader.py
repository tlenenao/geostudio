# SPDX-License-Identifier: Apache-2.0
"""ARC-33 : op `reader.raster` (cellules valides -> points), contrôle d'accès et décimation."""

from contextlib import contextmanager

import duckdb
import pytest
import rasterio

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import raster as raster_op
from app.pipelines.registries import READERS
from app.raster.models import RasterAsset
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.raster_fixtures import write_tif


@pytest.fixture()
def env(tmp_path, monkeypatch):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    tif = str(tmp_path / "a.tif")
    write_tif(tif)

    @contextmanager
    def opener(asset):
        with rasterio.open(tif) as ds:
            yield ds

    monkeypatch.setattr(raster_op, "open_asset", opener)
    with make_session_factory(engine)() as s:
        t = get_or_create_default_tenant(s)
        mk = lambda n: get_or_create_user(  # noqa: E731
            s, tenant_id=t.id, oidc_sub=n, username=n, email=None, first_name="", last_name=""
        )
        alice, bob = mk("alice"), mk("bob")
        item = items_repo.create_item(
            s, tenant_id=t.id, owner_id=alice.id, resource_type="raster", title="R"
        )
        s.add(
            RasterAsset(
                item_id=item.id,
                tenant_id=t.id,
                source_key="k",
                srid=4326,
                bounds=[2.0, 48.36, 2.64, 49.0],
                width=64,
                height=64,
                dtype="float32",
                nodata=-9999.0,
                bands=[],
                size_bytes=1,
            )
        )
        s.commit()
        yield s, t.id, item.id, alice, bob


def _run(conn, env, params, user):
    s, tid, _, _, _ = env
    return READERS["reader.raster"](
        conn,
        session=s,
        tenant_id=tid,
        node_id="n",
        params=params,
        view_name="node_n",
        user=user,
        base_uri="",
    )


def _conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def test_reader_drops_nodata_and_returns_points(env):
    c = _conn()
    srid = _run(c, env, {"itemId": env[2]}, env[3])
    assert srid == 4326
    # 64x64 moins la ligne 0 (nodata) ; 1er pixel valide = ligne 1, col 0 -> valeur 64
    assert c.execute("SELECT count(*) FROM node_n").fetchone()[0] == 64 * 63
    x, y, v, wkt = c.execute(
        "SELECT x, y, value, ST_AsText(geometry) FROM node_n ORDER BY value LIMIT 1"
    ).fetchone()
    assert (round(x, 3), round(y, 3), v) == (2.005, 48.985, 64.0)
    assert wkt.startswith("POINT")


def test_reader_decimates_over_max_cells(env):
    c = _conn()
    _run(c, env, {"itemId": env[2], "maxCells": 1024}, env[3])
    assert c.execute("SELECT count(*) FROM node_n").fetchone()[0] <= 1024


def test_reader_denies_user_without_read_access(env):
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _run(_conn(), env, {"itemId": env[2]}, env[4])


def test_reader_refuses_geo_limited_caller_when_raster_is_unattached(env, monkeypatch):
    monkeypatch.setattr(raster_op, "resolve_geo_limits", lambda *a, **k: {"t": []})
    with pytest.raises(PipelineRuntimeError, match="geo-limited"):
        _run(_conn(), env, {"itemId": env[2]}, env[3])

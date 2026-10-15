# SPDX-License-Identifier: Apache-2.0
"""Voie FME F1 : ops raster (modèle = référence d'item raster hébergé dans une colonne)."""

import shutil
import warnings
from contextlib import contextmanager
from types import SimpleNamespace

import duckdb
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import raster2 as r2
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.pipelines.registries import READERS
from app.raster import publish
from app.raster.models import RasterAsset
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role

OPS = {c.op for c in r2.CONTRACTS}


def _tif(
    path, data, *, x0=2.0, y0=49.0, res=0.01, nodata=-9999.0, crs="EPSG:4326", dtype="float32"
):
    data = np.asarray(data, dtype=dtype)
    if data.ndim == 2:
        data = data[None]
    with rasterio.open(
        str(path),
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=dtype,
        crs=crs,
        transform=from_origin(x0, y0, res, res),
        nodata=nodata,
    ) as d:
        d.write(data)
    return data


class Env:
    pass


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    paths: dict[str, str] = {}

    @contextmanager
    def opener(asset):
        with rasterio.open(paths[asset.source_key]) as ds:
            yield ds

    def upload(session, tenant_id, key, path):
        dest = tmp_path / f"store-{len(paths)}.tif"
        shutil.copyfile(path, dest)
        paths[key] = str(dest)

    monkeypatch.setattr(r2, "open_asset", opener)
    monkeypatch.setattr(publish, "_upload", upload)
    e = Env()
    e.tmp, e.paths = tmp_path, paths
    s = make_session_factory(engine)()
    t = get_or_create_default_tenant(s)
    mk = lambda n: get_or_create_user(  # noqa: E731
        s, tenant_id=t.id, oidc_sub=n, username=n, email=None, first_name="", last_name=""
    )
    e.s, e.tid, e.alice, e.bob = s, t.id, mk("alice"), mk("bob")
    roles = ensure_built_in_roles(s, tenant_id=t.id)
    set_user_role(
        s, tenant_id=t.id, user_id=e.alice.id, role_id=roles["admin"].id, role_slug="admin"
    )
    e.roles = roles

    def add(name, data, *, limit=None, **kw):
        arr = _tif(tmp_path / f"{name}.tif", data, **kw)
        item = items_repo.create_item(
            s, tenant_id=t.id, owner_id=e.alice.id, resource_type="raster", title=name
        )
        with rasterio.open(tmp_path / f"{name}.tif") as ds:
            s.add(
                RasterAsset(
                    item_id=item.id,
                    tenant_id=t.id,
                    source_key=name,
                    srid=4326,
                    bounds=list(ds.bounds),
                    width=ds.width,
                    height=ds.height,
                    dtype=ds.dtypes[0],
                    nodata=ds.nodata,
                    bands=[
                        {"index": i, "min": float(arr[i - 1].min()), "max": float(arr[i - 1].max())}
                        for i in ds.indexes
                    ],
                    size_bytes=1,
                    limit_collection_id=limit,
                )
            )
        paths[name] = str(tmp_path / f"{name}.tif")
        s.commit()
        return item.id

    e.add = add
    yield e
    s.close()


def _conn(rows=None):
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def _src(conn, ids, col="item_id"):
    conn.execute(f"CREATE TABLE src (name VARCHAR, {col} VARCHAR)")
    for i, v in enumerate(ids):
        conn.execute("INSERT INTO src VALUES (?, ?)", [f"r{i}", v])


def run(
    env, op, params, ids=None, *, user=None, preview=False, conn=None, col="item_id", srid=4326
):
    conn = conn or _conn()
    if ids is not None:
        _src(conn, ids, col)
    OPERATIONS[op].execute(
        conn,
        input_view="src",
        view_name="out",
        params=params,
        secret_resolver=SimpleNamespace(session=env.s, user=user or env.alice),
        preview=preview,
        input_srid=srid,
    )
    return conn


def rows(conn, sql="SELECT * FROM out"):
    return conn.execute(sql).fetchall()


def published(env, item_id):
    a = env.s.get(RasterAsset, item_id)
    with rasterio.open(env.paths[a.source_key]) as ds:
        d = ds.read(masked=True)
    return (d[0] if d.shape[0] == 1 else d), ds, a


RAMP = np.arange(64, dtype="float32").reshape(8, 8)

# ------------------------------------------------------------------ contrats


def test_contracts_and_catalog(monkeypatch):
    assert OPS == {
        "reader.rasterItems",
        "transform.rasterCalc",
        "transform.rasterConvolve",
        "transform.rasterMosaic",
        "transform.rasterPyramid",
        "transform.rasterStats",
        "transform.rasterBandCombine",
        "transform.rasterBandSeparate",
        "transform.rasterBandRemove",
        "transform.rasterBandNodata",
        "transform.rasterExtract",
        "transform.vectorOnRaster",
        "transform.webMapTiler",
        "transform.imageFetch",
        "transform.rasterGeoreference",
        "transform.rasterGcpSet",
        "transform.rasterGcpExtract",
        "transform.surfaceDrape",
    }
    monkeypatch.setenv("CORE_RASTER_ENABLED", "false")
    assert not OPS & set(ops_catalog())
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    assert OPS <= set(ops_catalog())
    assert all(c.engine_license for c in r2.CONTRACTS)


# ------------------------------------------------------------ portes communes


def test_reader_items_and_access_gates(env, monkeypatch):
    a = env.add("a", RAMP)
    c = _conn()
    READERS["reader.rasterItems"](
        c,
        session=env.s,
        tenant_id=env.tid,
        node_id="n",
        params={"itemIds": [a]},
        view_name="v",
        user=env.alice,
        base_uri="",
    )
    assert c.execute("SELECT item_id, width, height, bands, srid FROM v").fetchall() == [
        (a, 8, 8, 1, 4326)
    ]
    with pytest.raises(PipelineRuntimeError, match="not found"):
        READERS["reader.rasterItems"](
            _conn(),
            session=env.s,
            tenant_id=env.tid,
            node_id="n",
            params={"itemIds": [a]},
            view_name="v",
            user=env.bob,
            base_uri="",
        )
    for op, params in [("transform.rasterStats", {}), ("transform.rasterExtract", {})]:
        with pytest.raises(PipelineRuntimeError, match="not found"):
            run(env, op, params, [a], user=env.bob)
    monkeypatch.setattr("app.pipelines.ops.raster.resolve_geo_limits", lambda *x, **k: {"t": []})
    with pytest.raises(PipelineRuntimeError, match="geo-limited"):
        run(env, "transform.rasterStats", {}, [a])
    monkeypatch.undo()
    monkeypatch.setenv("CORE_RASTER_ENABLED", "false")
    with pytest.raises(PipelineRuntimeError, match="CORE_RASTER_ENABLED"):
        run(env, "transform.rasterStats", {}, [a])


def test_publish_needs_catalog_manage_and_preview_never_publishes(env):
    a = env.add("a", RAMP)
    from app.users.repository import set_user_role

    set_user_role(
        env.s,
        tenant_id=env.tid,
        user_id=env.alice.id,
        role_id=env.roles["reader"].id,
        role_slug="reader",
    )
    with pytest.raises(PipelineRuntimeError, match="catalog.manage"):
        run(env, "transform.rasterBandNodata", {"nodata": 0}, [a])
    n = env.s.query(RasterAsset).count()
    c = run(env, "transform.rasterBandNodata", {"nodata": 0}, [a], preview=True)
    assert env.s.query(RasterAsset).count() == n
    assert rows(c, "SELECT raster_item_id, raster_width FROM out") == [(None, 8)]


def test_caps_pixels_rows_and_timeout(env, monkeypatch):
    a = env.add("a", RAMP)
    monkeypatch.setattr(r2, "MAX_PIXELS", 10)
    with pytest.raises(PipelineRuntimeError, match="trop grand"):
        run(env, "transform.rasterStats", {}, [a])
    monkeypatch.setattr(r2, "MAX_PIXELS", 4_000_000)
    with pytest.raises(PipelineRuntimeError, match="more than"):
        run(env, "transform.rasterStats", {}, [a] * (r2.MAX_ROWS + 1))
    monkeypatch.setattr(r2, "MAX_SECONDS", -1.0)
    with pytest.raises(PipelineRuntimeError, match="délai"):
        run(env, "transform.rasterStats", {}, [a])


def test_degenerate_rows_and_missing_column(env):
    a = env.add("a", RAMP)
    c = run(env, "transform.rasterStats", {}, [None, "  ", a])
    got = rows(c, "SELECT name, raster_error, raster_b1_count FROM out ORDER BY name")
    assert got[0][1] and got[1][1] and got[2] == ("r2", None, 64)
    with pytest.raises(PipelineRuntimeError, match="no 'item_id'"):
        run(env, "transform.rasterStats", {}, [a], col="autre")
    c = run(env, "transform.rasterStats", {}, [])  # entrée vide
    assert rows(c) == []


# --------------------------------------------------------------------- calc


def test_calc_matches_numpy_nodata_and_div_zero(env):
    d1 = np.array(RAMP)
    d1[0, 0] = -9999
    a = env.add("a", d1)
    z = np.array(RAMP) - 10
    b = env.add("b", z)
    for op, ref in [
        ("add", d1 + z),
        ("subtract", d1 - z),
        ("multiply", d1 * z),
        ("min", np.minimum(d1, z)),
        ("max", np.maximum(d1, z)),
        ("mean", (d1 + z) / 2),
    ]:
        c = run(env, "transform.rasterCalc", {"otherItemId": b, "operation": op}, [a])
        data, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
        assert data.mask[0, 0] and ds.nodata == -9999.0
        np.testing.assert_allclose(data.data[1:], ref[1:], rtol=1e-6)
    c = run(env, "transform.rasterCalc", {"otherItemId": b, "operation": "divide"}, [a])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert data.mask[1, 2] and not data.mask[3, 3]  # b = 0 en [1, 2]
    zero = env.add("zero", np.zeros((8, 8)))
    c = run(env, "transform.rasterCalc", {"otherItemId": zero, "operation": "divide"}, [a])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert data.mask.all()


def test_calc_grid_mismatch_is_a_row_error(env):
    a, b = env.add("a", RAMP), env.add("b", np.ones((4, 4)))
    c = run(env, "transform.rasterCalc", {"otherItemId": b, "operation": "add"}, [a])
    assert "même grille" in rows(c, "SELECT raster_error FROM out")[0][0]


# ----------------------------------------------------------------- convolve


def test_convolve_identity_box_and_edges(env):
    a = env.add("a", RAMP)
    ident = [[0, 0, 0], [0, 1, 0], [0, 0, 0]]
    c = run(env, "transform.rasterConvolve", {"kernel": ident}, [a])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    np.testing.assert_allclose(data.data, RAMP)
    box = [[1] * 3] * 3
    c = run(env, "transform.rasterConvolve", {"kernel": box}, [a])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    np.testing.assert_allclose(data.data[3, 3], RAMP[2:5, 2:5].mean())
    np.testing.assert_allclose(data.data[0, 0], RAMP[0:2, 0:2].mean())  # bord renormalisé
    with pytest.raises(ValueError, match="sums to zero"):
        run(env, "transform.rasterConvolve", {"kernel": [[-1, 2, -1]] * 3}, [a])
    edge = [[-1, -1, -1], [-1, 8, -1], [-1, -1, -1]]
    run(env, "transform.rasterConvolve", {"kernel": edge, "normalize": False}, [a])
    for bad in ([[1, 1]], [[1] * 9] * 9):
        with pytest.raises(ValueError):
            run(env, "transform.rasterConvolve", {"kernel": bad}, [a])


# ------------------------------------------------------------------- mosaic


def test_mosaic_first_last_and_alignment(env, monkeypatch):
    a = env.add("a", np.full((8, 8), 1.0))
    b = env.add("b", np.full((8, 8), 2.0), x0=2.04)  # recouvre 4 colonnes
    c = run(env, "transform.rasterMosaic", {}, [a, b])
    data, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert (ds.width, ds.height) == (12, 8)
    assert list(data.data[0]) == [1.0] * 8 + [2.0] * 4
    c = run(env, "transform.rasterMosaic", {"onOverlap": "last"}, [a, b])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert list(data.data[0]) == [1.0] * 4 + [2.0] * 8
    off = env.add("off", np.ones((8, 8)), x0=2.045)
    with pytest.raises(PipelineRuntimeError, match="non alignées"):
        run(env, "transform.rasterMosaic", {}, [a, off])
    with pytest.raises(PipelineRuntimeError, match="deux rasters"):
        run(env, "transform.rasterMosaic", {}, [a])
    monkeypatch.setattr(r2, "MAX_OUT_PIXELS", 80)
    with pytest.raises(PipelineRuntimeError, match="trop grande"):
        run(env, "transform.rasterMosaic", {}, [a, b])


def test_mosaic_gap_is_nodata_and_needs_nodata(env):
    a = env.add("a", np.full((4, 4), 1.0))
    b = env.add("b", np.full((4, 4), 2.0), x0=2.08)  # trou de 4 colonnes
    c = run(env, "transform.rasterMosaic", {}, [a, b])
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert data.mask[0, 4:8].all() and not data.mask[0, 0] and not data.mask[0, 8]
    n1 = env.add("n1", np.ones((4, 4)), nodata=None)
    n2 = env.add("n2", np.ones((4, 4)), nodata=None, x0=2.04)
    with pytest.raises(PipelineRuntimeError, match="nodata requis"):
        run(env, "transform.rasterMosaic", {}, [n1, n2])
    run(env, "transform.rasterMosaic", {"nodata": -1}, [n1, n2])


# ------------------------------------------------------------------ pyramid


def test_pyramid_levels(env):
    a = env.add("a", np.arange(256, dtype="float32").reshape(16, 16))
    c = run(env, "transform.rasterPyramid", {"levels": 3}, [a])
    got = rows(c, "SELECT raster_level, raster_width, raster_height FROM out ORDER BY raster_level")
    assert got == [(1, 8, 8), (2, 4, 4), (3, 2, 2)]
    data, ds, _ = published(
        env, rows(c, "SELECT raster_item_id FROM out WHERE raster_level=1")[0][0]
    )
    assert abs(ds.res[0] - 0.02) < 1e-9
    assert data.data[0, 0] == pytest.approx(np.arange(256).reshape(16, 16)[:2, :2].mean())


# -------------------------------------------------------------------- stats


def test_stats_match_numpy_across_blocks(env, monkeypatch):
    monkeypatch.setattr(r2, "BLOCK", 3)  # force la combinaison multi-blocs
    d = np.array(RAMP)
    d[0, :] = -9999
    two = np.stack([d, RAMP * 2])
    a = env.add("a", two)
    c = run(env, "transform.rasterStats", {"bands": [1, 2]}, [a])
    r = rows(c, "SELECT * EXCLUDE (name, item_id) FROM out")[0]
    cols = [x[0] for x in c.execute("DESCRIBE out").fetchall()][2:]
    got = dict(zip(cols, r, strict=True))
    v = d[d != -9999]
    assert got["raster_b1_count"] == 56 and got["raster_b1_min"] == v.min()
    assert got["raster_b1_mean"] == pytest.approx(v.mean()) and got[
        "raster_b1_std"
    ] == pytest.approx(v.std())
    assert got["raster_b2_max"] == 126
    c = run(env, "transform.rasterStats", {"bands": [5]}, [a])
    assert "inexistante" in rows(c, "SELECT raster_error FROM out")[0][0]


# -------------------------------------------------------------- band ops


def test_band_combine_separate_remove_nodata(env):
    b1 = env.add("b1", RAMP)
    b2 = env.add("b2", RAMP * 2, dtype="float32")
    c = run(env, "transform.rasterBandCombine", {}, [b1, b2])
    data, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.count == 2 and data.data[1, 1, 1] == RAMP[1, 1] * 2
    multi = rows(c, "SELECT raster_item_id FROM out")[0][0]
    c = run(env, "transform.rasterBandSeparate", {}, [multi])
    got = rows(c, "SELECT raster_band, raster_bands FROM out ORDER BY raster_band")
    assert got == [(1, 1), (2, 1)]
    d2, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out WHERE raster_band=2")[0][0])
    assert d2.data[1, 1] == RAMP[1, 1] * 2
    c = run(env, "transform.rasterBandRemove", {"removeBands": [1]}, [multi])
    data, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.count == 1 and data.data[1, 1] == RAMP[1, 1] * 2
    c = run(env, "transform.rasterBandRemove", {"removeBands": [1, 2]}, [multi])
    assert "toutes les bandes" in rows(c, "SELECT raster_error FROM out")[0][0]
    c = run(env, "transform.rasterBandRemove", {"removeBands": [9]}, [multi])
    assert "aucune" in rows(c, "SELECT raster_error FROM out")[0][0]
    c = run(env, "transform.rasterBandNodata", {"nodata": 7.0}, [b1])
    data, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.nodata == 7.0
    np.testing.assert_array_equal(np.ma.getdata(data), RAMP)
    u8 = env.add("u8", np.ones((4, 4)), dtype="uint8", nodata=None)
    c = run(env, "transform.rasterBandNodata", {"nodata": 300}, [u8])
    assert "incompatible" in rows(c, "SELECT raster_error FROM out")[0][0]
    n = env.add("n3", np.ones((3, 3, 3)))  # 3 bandes
    four = [n] * 6  # 18 bandes > MAX_BANDS
    with pytest.raises(PipelineRuntimeError, match="bandes au total"):
        run(env, "transform.rasterBandCombine", {}, four)


# ------------------------------------------------------------------ extract


def test_extract_png_gtiff_and_limits(env, monkeypatch):
    u8 = env.add("u8", np.arange(64).reshape(8, 8), dtype="uint8", nodata=None)
    f = env.add("f", RAMP)
    c = run(env, "transform.rasterExtract", {}, [u8, f])
    got = rows(c, "SELECT raster_blob, raster_error FROM out ORDER BY name")
    assert bytes(got[0][0]).startswith(b"\x89PNG") and "PNG" in got[1][1]
    c = run(env, "transform.rasterExtract", {"format": "gtiff"}, [f])
    blob = bytes(rows(c, "SELECT raster_blob FROM out")[0][0])
    with rasterio.MemoryFile(blob) as m, m.open() as ds:
        np.testing.assert_array_equal(ds.read(1), RAMP)
    monkeypatch.setattr(r2, "MAX_BLOB_PIXELS", 10)
    with pytest.raises(PipelineRuntimeError, match="trop grand"):
        run(env, "transform.rasterExtract", {}, [u8])
    monkeypatch.setattr(r2, "MAX_BLOB_PIXELS", 1_000_000)
    monkeypatch.setattr(r2, "MAX_BLOB_BYTES", 10)
    c = run(env, "transform.rasterExtract", {}, [u8])
    assert "volumineuse" in rows(c, "SELECT raster_error FROM out")[0][0]


# -------------------------------------------------------------------- tiler


def test_tiler_png_tiles_and_cap(env, monkeypatch):
    a = env.add(
        "a",
        np.full((8, 8), 100, dtype="uint8"),
        dtype="uint8",
        nodata=None,
        x0=2.0,
        y0=49.0,
        res=0.1,
    )
    c = run(env, "transform.webMapTiler", {"minZoom": 5, "maxZoom": 6}, [a])
    got = rows(c, "SELECT z, x, y, tile FROM out")
    assert got and {g[0] for g in got} == {5, 6}
    assert all(bytes(g[3]).startswith(b"\x89PNG") for g in got)
    with rasterio.MemoryFile(bytes(got[0][3])) as m, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ds = m.open()
        assert (ds.width, ds.height, ds.count) == (256, 256, 2)
        assert ds.read(2).max() == 255 and ds.read(1).max() == 100
    monkeypatch.setattr(r2, "MAX_TILES", 1)
    with pytest.raises(PipelineRuntimeError, match="tuiles"):
        run(env, "transform.webMapTiler", {"minZoom": 5, "maxZoom": 8}, [a])
    f = env.add("f", RAMP)
    monkeypatch.setattr(r2, "MAX_TILES", 256)
    run(env, "transform.webMapTiler", {"minZoom": 6, "maxZoom": 6}, [f])  # float: stats de l'asset
    with pytest.raises(ValueError):
        run(env, "transform.webMapTiler", {"minZoom": 7, "maxZoom": 6}, [a])
    monkeypatch.setattr(r2, "MAX_TILE_BYTES", 10)
    with pytest.raises(PipelineRuntimeError, match="volumineuses"):
        run(env, "transform.webMapTiler", {"minZoom": 5, "maxZoom": 5}, [a])


# ---------------------------------------------------------- vectorOnRaster


def test_vector_on_raster_burns_existing_raster(env):
    a = env.add("a", np.zeros((8, 8)), nodata=None)
    c = _conn()
    c.execute("CREATE TABLE src (v DOUBLE, geometry GEOMETRY)")
    c.execute(
        "INSERT INTO src VALUES (5, ST_GeomFromText('POLYGON((2.02 48.98, 2.05 48.98, "
        "2.05 48.95, 2.02 48.95, 2.02 48.98))'))"
    )
    c.execute("INSERT INTO src VALUES (NULL, NULL)")  # dégénéré
    run(env, "transform.vectorOnRaster", {"itemId": a, "valueColumn": "v"}, conn=c)
    data, _, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    d = np.ma.getdata(data)
    assert (d == 5).sum() == 9 and d[2:5, 2:5].min() == 5 and d.sum() == 45
    # l'original est intact
    orig, _, _ = published(env, a)
    assert np.ma.getdata(orig).sum() == 0
    c2 = _conn()
    c2.execute("CREATE TABLE src (geometry GEOMETRY)")
    run(env, "transform.vectorOnRaster", {"itemId": a, "burnValue": 3}, conn=c2)  # aucune géométrie
    with pytest.raises(PipelineRuntimeError, match="no 'geometry'"):
        c3 = _conn()
        c3.execute("CREATE TABLE src (x INT)")
        run(env, "transform.vectorOnRaster", {"itemId": a}, conn=c3)
    u8 = env.add("u8", np.zeros((4, 4)), dtype="uint8", nodata=None)
    with pytest.raises(PipelineRuntimeError, match="incompatible"):
        run(env, "transform.vectorOnRaster", {"itemId": u8, "burnValue": 999}, conn=c)


# ------------------------------------------------------------- surface drape


def test_drape_z_slope_aspect(env):
    # plan incliné : z = 10 * colonne (monte vers l'est) -> exposition ouest (270°)
    z = np.tile(np.arange(8) * 10.0, (8, 1))
    a = env.add("dem", z, res=0.001, y0=45.0)
    c = _conn()
    c.execute("CREATE TABLE src (n INT, geometry GEOMETRY)")
    c.execute("INSERT INTO src VALUES (1, ST_Point(2.0035, 44.9965))")  # col 3, ligne 3
    c.execute("INSERT INTO src VALUES (2, ST_Point(9.0, 9.0))")  # hors raster
    c.execute("INSERT INTO src VALUES (3, ST_GeomFromText('LINESTRING(2 45, 2.001 45)'))")
    c.execute("INSERT INTO src VALUES (4, NULL)")
    run(env, "transform.surfaceDrape", {"itemId": a}, conn=c)
    got = rows(c, "SELECT n, drape_z, drape_slope, drape_aspect FROM out ORDER BY n")
    assert got[0][1] == 30.0
    slope = np.degrees(np.arctan(10 / (0.001 * 111320 * np.cos(np.radians(44.9965)))))
    assert got[0][2] == pytest.approx(slope, rel=1e-3) and got[0][3] == pytest.approx(270.0)
    assert (
        got[1][1:] == (None, None, None)
        and got[2][1:] == (None, None, None)
        and got[3][1:] == (None, None, None)
    )
    c = _conn()
    c.execute("CREATE TABLE src (geometry GEOMETRY)")
    c.execute("INSERT INTO src VALUES (ST_Point(2.0035, 44.9965))")
    run(env, "transform.surfaceDrape", {"itemId": a, "slopeAspect": False}, conn=c)
    assert rows(c, "SELECT drape_z, drape_slope FROM out") == [(30.0, None)]


def test_drape_nodata_cell_and_input_srid(env):
    z = np.ones((8, 8))
    z[3, 3] = -9999
    a = env.add("dem", z, res=0.001, y0=45.0)
    c = _conn()
    c.execute("CREATE TABLE src (geometry GEOMETRY)")
    c.execute("INSERT INTO src VALUES (ST_Point(2.0035, 44.9965))")
    run(env, "transform.surfaceDrape", {"itemId": a}, conn=c)
    assert rows(c, "SELECT drape_z, drape_slope FROM out") == [(None, None)]
    c2 = _conn()
    c2.execute("CREATE TABLE src (geometry GEOMETRY)")
    c2.execute(
        "INSERT INTO src SELECT ST_Transform(ST_Point(2.0045, 44.9955), 'EPSG:4326', "
        "'EPSG:3857', always_xy := true)"
    )
    run(env, "transform.surfaceDrape", {"itemId": a}, conn=c2, srid=3857)
    assert rows(c2, "SELECT drape_z FROM out") == [(1.0,)]


# --------------------------------------------------- georeference / GCP


def test_georeference_corners_origin_and_validation(env):
    a = env.add("a", RAMP)
    c = run(
        env,
        "transform.rasterGeoreference",
        {"mode": "corners", "srid": 4326, "ulx": 10, "uly": 20, "lrx": 18, "lry": 12},
        [a],
    )
    data, ds, asset = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.bounds == pytest.approx((10, 12, 18, 20)) and np.ma.getdata(data)[3, 3] == RAMP[3, 3]
    c = run(
        env,
        "transform.rasterGeoreference",
        {
            "mode": "origin",
            "srid": 4326,
            "originX": 1,
            "originY": 2,
            "cellWidth": 0.5,
            "cellHeight": 0.5,
            "rotation": 0,
        },
        [a],
    )
    _, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.transform.c == 1 and ds.res == (0.5, 0.5)
    c = run(
        env,
        "transform.rasterGeoreference",
        {
            "mode": "origin",
            "srid": 4326,
            "originX": 1,
            "originY": 2,
            "cellWidth": 0.5,
            "cellHeight": 0.5,
            "rotation": 30,
        },
        [a],
    )
    _, ds, _ = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert ds.transform.b != 0 and ds.transform.d != 0  # rotation appliquée
    c = run(
        env,
        "transform.rasterGeoreference",
        {"mode": "corners", "srid": 999999, "ulx": 10, "uly": 20, "lrx": 18, "lry": 12},
        [a],
    )
    assert "inconnu" in rows(c, "SELECT raster_error FROM out")[0][0]
    for bad in (
        {"mode": "corners", "srid": 4326},
        {"mode": "corners", "srid": 4326, "ulx": 5, "uly": 1, "lrx": 1, "lry": 3},
    ):
        with pytest.raises(ValueError):
            run(env, "transform.rasterGeoreference", bad, [a])


def test_gcp_set_then_extract_roundtrip_through_cog(env):
    a = env.add("a", RAMP)
    gcps = [
        {"col": 0, "row": 0, "x": 100, "y": 200},
        {"col": 8, "row": 0, "x": 108, "y": 200},
        {"col": 0, "row": 8, "x": 100, "y": 192},
        {"col": 8, "row": 8, "x": 108, "y": 192},
    ]
    c = run(env, "transform.rasterGcpSet", {"gcps": gcps, "srid": 4326}, [a])
    new, rmse = rows(c, "SELECT raster_item_id, raster_gcp_rmse FROM out")[0]
    assert rmse == pytest.approx(0, abs=1e-9)
    _, ds, _ = published(env, new)
    assert ds.bounds == pytest.approx((100, 192, 108, 200))
    c = run(
        env,
        "transform.rasterGcpExtract",
        {"itemColumn": "raster_item_id"},
        [new],
        col="raster_item_id",
    )
    got = rows(c, "SELECT gcp_col, gcp_row, gcp_x, gcp_y FROM out ORDER BY gcp_x, gcp_y")
    assert len(got) == 4 and (8.0, 8.0, 108.0, 192.0) in got
    c = run(env, "transform.rasterGcpExtract", {}, [a])  # sans point
    assert rows(c) == []
    for bad in ([{"col": 0, "row": 0, "x": 0, "y": 0}] * 3,):
        with pytest.raises(PipelineRuntimeError, match="alignés|invalides"):
            run(env, "transform.rasterGcpSet", {"gcps": bad, "srid": 4326}, [a])
    with pytest.raises(ValueError):
        run(env, "transform.rasterGcpSet", {"gcps": gcps[:2], "srid": 4326}, [a])


# --------------------------------------------------------------- imageFetch


def _png(w=4, h=4):
    with rasterio.MemoryFile() as m, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with m.open(driver="PNG", width=w, height=h, count=1, dtype="uint8") as o:
            o.write(np.full((1, h, w), 9, dtype="uint8"))
        return m.read()


def test_image_fetch_egress_guard_is_real(env):
    with pytest.raises(PipelineRuntimeError, match="egress"):
        run(
            env,
            "transform.imageFetch",
            {"bounds": [0, 0, 1, 1]},
            ["http://127.0.0.1/x.png"],
            col="url",
        )
    with pytest.raises(PipelineRuntimeError, match="egress"):
        run(
            env,
            "transform.imageFetch",
            {"bounds": [0, 0, 1, 1]},
            ["http://169.254.169.254/x.png"],
            col="url",
        )


def test_image_fetch_publishes_georeferenced_image_and_row_errors(env, monkeypatch):
    png = _png()
    monkeypatch.setattr(r2, "_fetch", lambda url: png if url.endswith("ok.png") else b"<html>")
    c = run(
        env,
        "transform.imageFetch",
        {"bounds": [0, 0, 4, 4]},
        ["http://x/ok.png", "http://x/bad", None],
        col="url",
    )
    got = rows(c, "SELECT raster_item_id, raster_error FROM out ORDER BY name")
    data, ds, _ = published(env, got[0][0])
    assert ds.bounds == pytest.approx((0, 0, 4, 4)) and np.ma.getdata(data).max() == 9
    assert "format" in got[1][1] and "URL absente" in got[2][1]
    c = run(env, "transform.imageFetch", {}, ["http://x/ok.png"], col="url")
    assert "bounds" in rows(c, "SELECT raster_error FROM out")[0][0]
    with pytest.raises(PipelineRuntimeError, match="aperçu"):
        run(
            env,
            "transform.imageFetch",
            {"bounds": [0, 0, 1, 1]},
            ["http://x/ok.png"],
            col="url",
            preview=True,
        )
    monkeypatch.setattr(r2, "MAX_PIXELS", 4)
    c = run(env, "transform.imageFetch", {"bounds": [0, 0, 4, 4]}, ["http://x/ok.png"], col="url")
    assert "trop grande" in rows(c, "SELECT raster_error FROM out")[0][0]


def test_image_fetch_size_cap_streams(monkeypatch):
    class Resp:
        headers: dict = {}

        def raise_for_status(self): ...
        def iter_content(self, n):
            for _ in range(10):
                yield b"x" * 10

        def __enter__(self):
            return self

        def __exit__(self, *a): ...

    monkeypatch.setattr(
        r2, "build_guarded_session", lambda: SimpleNamespace(get=lambda *a, **k: Resp())
    )
    monkeypatch.setattr(r2, "MAX_IMAGE_BYTES", 50)
    with pytest.raises(r2._RowError, match="volumineuse"):
        r2._fetch("http://x/")


def test_output_item_cap_and_limit_collection_inheritance(env, monkeypatch):
    a = env.add("a", RAMP, limit="col-1")
    c = run(env, "transform.rasterBandNodata", {"nodata": 0}, [a])
    _, _, asset = published(env, rows(c, "SELECT raster_item_id FROM out")[0][0])
    assert asset.limit_collection_id == "col-1" and asset.tenant_id == env.tid
    owner = env.s.get(RasterAsset, asset.item_id)
    assert owner is not None
    b = env.add("b", RAMP, limit="col-2")
    c = run(env, "transform.rasterCalc", {"otherItemId": b, "operation": "add"}, [a])
    assert "limites différentes" in rows(c, "SELECT raster_error FROM out")[0][0]
    monkeypatch.setattr(r2, "MAX_OUT_ITEMS", 2)
    with pytest.raises(PipelineRuntimeError, match="plus de 2 rasters"):
        run(env, "transform.rasterPyramid", {"levels": 3}, [env.add("p", np.ones((16, 16)))])

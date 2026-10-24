# SPDX-License-Identifier: Apache-2.0
"""Voie A FME : attributs, filtres, SCR, texte, logique (module ops/attrs.py)."""

import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import attrs
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture requise par `rig`)
from tests.test_pipeline_run_retry import _exec, _new_run, _payload, rig  # noqa: F401

OPS = {
    "transform.attributeManager", "transform.aggregateFilter", "transform.matcher",
    "transform.geometryFilter", "transform.attributeRangeFilter", "transform.planarityFilter",
    "transform.spatialRelator", "transform.featureTypeFilter", "transform.latLongToMgrs",
    "transform.mgrsToLatLong", "transform.textEncoder", "transform.textDecoder",
    "transform.htmlExtractor", "transform.terminator",
}  # fmt: skip


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE src (id INTEGER, grp VARCHAR, val INTEGER, geometry GEOMETRY)")
    c.execute(
        "INSERT INTO src VALUES (1,'a',10,ST_Point(2.2945,48.8584)),"
        "(2,'a',20,ST_Point(2.2945,48.8584)),"
        "(3,'b',30,ST_GeomFromText('LINESTRING(0 0,1 1)')),(4,'b',NULL,NULL),"
        "(5,'c',50,ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 0))'))"
    )
    return c


def _run(conn, op, params, view="out", src="src", **kw):
    c = OPERATIONS[op]
    conn.execute(f'DROP VIEW IF EXISTS "{view}"')
    if c.execute is not None:
        if c.needs_runtime_context:
            kw.setdefault("input_srid", 4326)
        else:
            kw = {}
        c.execute(conn, input_view=src, view_name=view, params=params, **kw)
    else:
        extra = {}
        if c.needs_columns:
            extra["input_columns"] = [d[0] for d in conn.execute(f"DESCRIBE {src}").fetchall()]
        sql = c.compile(params, input_view=src, join_view="sup", input_srid=4326, **extra)
        conn.execute(f'CREATE TEMP VIEW "{view}" AS {sql}')


def _ids(conn, view="out"):
    return [r[0] for r in conn.execute(f'SELECT id FROM "{view}" ORDER BY id').fetchall()]


def test_registry_and_catalog():
    assert {c.op for c in attrs.CONTRACTS} == OPS
    for op in OPS:
        assert op in ops_catalog() and OPERATIONS[op].engine_license
    assert OPERATIONS["transform.spatialRelator"].accepts_secondary_input


def test_attribute_manager(conn):
    _run(conn, "transform.attributeManager", {
        "derive": {"dbl": "val * 2", "val": "val + 1"}, "rename": {"grp": "groupe"},
        "remove": ["id"], "order": ["dbl"],
    })  # fmt: skip
    cols = [d[0] for d in conn.execute("DESCRIBE out").fetchall()]
    assert cols == ["dbl", "groupe", "val", "geometry"]
    assert conn.execute("SELECT dbl, val FROM out WHERE groupe='a' ORDER BY val").fetchall() == [
        (20, 11), (40, 21),
    ]  # fmt: skip


def test_attribute_manager_degenerate(conn):
    with pytest.raises(PipelineRuntimeError, match="introuvable"):
        _run(conn, "transform.attributeManager", {"remove": ["nope"]})
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _run(conn, "transform.attributeManager", {"remove": ["geometry"]})
    with pytest.raises(PipelineRuntimeError, match="écraserait"):
        _run(conn, "transform.attributeManager", {"rename": {"grp": "val"}})
    with pytest.raises(SqlSandboxError):
        _run(conn, "transform.attributeManager", {"derive": {"x": "(SELECT 1 FROM src)"}})


def test_aggregate_filter_keeps_detail_rows(conn):
    p = {"groupBy": ["grp"], "metrics": {"n": "count(*)"}, "having": "n >= 2"}
    _run(conn, "transform.aggregateFilter", p, "p")
    _run(conn, "transform.aggregateFilter", {**p, "output": "failed"}, "f")
    assert _ids(conn, "p") == [1, 2, 3, 4] and _ids(conn, "f") == [5]
    assert conn.execute("SELECT DISTINCT n FROM p WHERE grp='a'").fetchall() == [(2,)]
    with pytest.raises(PipelineRuntimeError, match="métrique"):
        _run(conn, "transform.aggregateFilter", {**p, "metrics": {"id": "count(*)"}})
    empty = duckdb.connect()
    empty.execute("CREATE TABLE e (grp VARCHAR)")
    _run(empty, "transform.aggregateFilter", p, "o", src="e")
    assert empty.execute("SELECT count(*) FROM o").fetchone()[0] == 0


def test_matcher(conn):
    _run(conn, "transform.matcher", {"matchGeometry": True})
    rows = conn.execute("SELECT id, match_count, is_duplicate FROM out ORDER BY id").fetchall()
    assert rows[0] == (1, 2, False) and rows[1] == (2, 2, True) and rows[2] == (3, 1, False)
    assert rows[3][1:] == (1, False)  # géométrie NULL : pas d'erreur
    _run(conn, "transform.matcher", {"keyColumns": ["grp"]}, "k")
    assert conn.execute("SELECT count(DISTINCT match_group) FROM k").fetchone()[0] == 3
    with pytest.raises(ValueError):
        attrs.TransformMatcherParams()


def test_geometry_filter_partitions(conn):
    for types, expected in [(["point"], [1, 2]), (["line", "polygon"], [3, 5]), (["null"], [4])]:
        _run(conn, "transform.geometryFilter", {"types": types}, "p")
        _run(conn, "transform.geometryFilter", {"types": types, "output": "failed"}, "f")
        assert _ids(conn, "p") == expected
        assert sorted(_ids(conn, "p") + _ids(conn, "f")) == [1, 2, 3, 4, 5]


def test_attribute_range_filter(conn):
    r = [{"min": 10, "max": 30}, {"min": 20}]
    base = {"column": "val", "ranges": r}
    _run(conn, "transform.attributeRangeFilter", base, "p")
    _run(conn, "transform.attributeRangeFilter", {**base, "output": "failed"}, "f")
    assert _ids(conn, "p") == [1, 2, 3, 5] and _ids(conn, "f") == [4]  # NULL -> failed
    _run(conn, "transform.attributeRangeFilter", {**base, "output": "annotate"}, "a")
    assert conn.execute("SELECT range_index FROM a ORDER BY id").fetchall() == [
        (0,), (0,), (1,), (None,), (1,),
    ]  # fmt: skip
    with pytest.raises(ValueError):
        attrs.TransformAttributeRangeFilterParams(column="v", ranges=[{}])


def test_planarity_filter():
    c = duckdb.connect()
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE s (id INT, geometry GEOMETRY)")
    c.execute(
        "INSERT INTO s VALUES "
        "(1, ST_GeomFromText('POLYGON Z((0 0 0,1 0 1,1 1 2,0 1 1,0 0 0))')),"  # plan z=x+y
        "(2, ST_GeomFromText('POLYGON Z((0 0 0,1 0 0,1 1 5,0 1 0,0 0 0))')),"  # gauchi
        "(3, ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 0))')),"  # 2D
        "(4, ST_Point(0,0)), (5, NULL)"
    )
    for out, exp in [("planar", [1, 3]), ("notPlanar", [2]), ("rejected", [4, 5])]:
        _run(c, "transform.planarityFilter", {"output": out, "tolerance": 1e-6}, "o", src="s")
        assert _ids(c, "o") == exp


def test_spatial_relator(conn):
    conn.execute("CREATE TABLE sup (geometry GEOMETRY)")
    conn.execute("INSERT INTO sup VALUES (ST_GeomFromText('POLYGON((-1 -1,3 -1,3 3,-1 3,-1 -1))'))")
    _run(conn, "transform.spatialRelator", {"predicate": "within"}, "all_")
    assert conn.execute(
        "SELECT id, match_count FROM all_ WHERE id IN (3,5) ORDER BY id"
    ).fetchall() == [(3, 1), (5, 1)]
    _run(conn, "transform.spatialRelator", {"predicate": "within", "output": "unrelated"}, "u")
    assert _ids(conn, "u") == [1, 2, 4]  # points en France, géométrie NULL
    _run(conn, "transform.spatialRelator", {"predicate": "touches", "output": "related"}, "t")
    assert _ids(conn, "t") == []


def test_feature_type_filter(conn):
    c = duckdb.connect()
    c.execute(
        "CREATE TABLE s AS SELECT * FROM (VALUES (1,'a''b'),(2,'c'),(3,NULL)) t(id, feature_type)"
    )
    _run(c, "transform.featureTypeFilter", {"types": ["a'b", "x"]}, "p", src="s")
    _run(
        c, "transform.featureTypeFilter", {"types": ["a'b", "x"], "output": "failed"}, "f", src="s"
    )
    assert _ids(c, "p") == [1] and _ids(c, "f") == [2, 3]


def test_mgrs_roundtrip_and_degenerate(conn):
    _run(conn, "transform.latLongToMgrs", {"precision": 5})
    got = dict(conn.execute("SELECT id, mgrs FROM out").fetchall())
    assert got[1] == "31UDQ4825211954" and got[4] is None  # NULL reste NULL
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] == 5
    _run(conn, "transform.mgrsToLatLong", {"column": "mgrs"}, "back", src="out")
    lon, lat = conn.execute("SELECT ST_X(geometry), ST_Y(geometry) FROM back WHERE id=1").fetchone()
    assert abs(lat - 48.8584) < 1e-3 and abs(lon - 2.2945) < 1e-3
    conn.execute("CREATE TABLE bad AS SELECT * FROM (VALUES (1,'zzz'),(2,NULL)) t(id, mgrs)")
    _run(conn, "transform.mgrsToLatLong", {}, "b2", src="bad")
    assert conn.execute("SELECT count(*) FROM b2 WHERE geometry IS NULL").fetchone()[0] == 2
    with pytest.raises(PipelineRuntimeError, match="4326"):
        _run(conn, "transform.latLongToMgrs", {}, input_srid=2154)


def test_text_encode_decode_roundtrip():
    c = duckdb.connect()
    c.execute("CREATE TABLE s AS SELECT * FROM (VALUES (1,'café'),(2,'日本'),(3,NULL)) t(id, t)")
    p = {"column": "t", "encoding": "latin-1", "outputColumn": "b"}
    _run(c, "transform.textEncoder", p, "e", src="s")
    rows = dict(c.execute("SELECT id, b FROM e").fetchall())
    assert rows[1] == "café".encode("latin-1") and rows[2] is None and rows[3] is None
    _run(c, "transform.textEncoder", {**p, "errors": "replace"}, "e2", src="s")
    assert dict(c.execute("SELECT id, b FROM e2").fetchall())[2] == b"??"
    _run(
        c,
        "transform.textDecoder",
        {"column": "b", "encoding": "latin-1", "outputColumn": "d"},
        "d",
        src="e",
    )
    assert dict(c.execute("SELECT id, d FROM d").fetchall()) == {1: "café", 2: None, 3: None}
    for bad in ("hex", "nope"):
        with pytest.raises(ValueError):
            attrs.TransformTextEncoderParams(column="t", encoding=bad, outputColumn="o")
    with pytest.raises(PipelineRuntimeError, match="introuvable"):
        _run(c, "transform.textEncoder", {**p, "column": "zz"}, "x", src="s")


def test_html_extractor():
    c = duckdb.connect()
    c.execute(
        "CREATE TABLE s AS SELECT * FROM (VALUES "
        '(1,\'<p>Hi <b>there</b><script>x()</script></p><a href="/u1">L1</a>'
        '<a href="/u2" class="k">L2</a>\'),'
        "(2,NULL),(3,'<div><a>unclosed')) t(id, h)"
    )
    base = {"column": "h", "outputColumn": "o", "separator": "|"}
    _run(c, "transform.htmlExtractor", base, "t", src="s")
    assert dict(c.execute("SELECT id, o FROM t").fetchall())[1] == "Hi there L1 L2"
    _run(
        c,
        "transform.htmlExtractor",
        {**base, "mode": "attribute", "tag": "a", "attribute": "href"},
        "a",
        src="s",
    )
    assert dict(c.execute("SELECT id, o FROM a").fetchall()) == {1: "/u1|/u2", 2: None, 3: ""}
    _run(
        c,
        "transform.htmlExtractor",
        {**base, "mode": "elementText", "tag": "a", "className": "k"},
        "e",
        src="s",
    )
    assert dict(c.execute("SELECT id, o FROM e").fetchall())[1] == "L2"
    with pytest.raises(ValueError):
        attrs.TransformHtmlExtractorParams(column="h", outputColumn="o", mode="attribute", tag="a")


def test_terminator(conn):
    _run(conn, "transform.terminator", {"condition": "val > 100"})
    assert _ids(conn) == [1, 2, 3, 4, 5]
    with pytest.raises(PipelineRuntimeError, match=r"trop grand.*2 ligne"):
        _run(conn, "transform.terminator", {"condition": "val >= 30", "message": "trop grand"})
    with pytest.raises(PipelineRuntimeError, match="1 ligne"):
        _run(conn, "transform.terminator", {"condition": "val IS NULL"})  # NULL détecté


def test_udf_ops_work_on_a_locked_connection(conn):
    conn.execute("SET enable_external_access=false; SET lock_configuration=true")
    _run(conn, "transform.latLongToMgrs", {})
    assert conn.execute("SELECT mgrs FROM out WHERE id=1").fetchone()[0].startswith("31U")


def test_html_extractor_deep_nesting_is_bounded_and_fast():
    import time

    c = duckdb.connect()
    c.execute("CREATE TABLE s AS SELECT 1 AS id, repeat('<div>a', 8000) AS h")
    p = {"column": "h", "outputColumn": "o", "mode": "elementText", "tag": "div"}
    t0 = time.perf_counter()
    _run(c, "transform.htmlExtractor", p, "o", src="s")
    assert c.execute("SELECT o FROM o").fetchone()[0] is None  # imbrication excessive -> NULL
    assert (
        time.perf_counter() - t0 < 5.0
    )  # borne anti-quadratique, pas une mesure de vitesse (runner arm64 chargé)
    # imbrication raisonnable : fonctionne toujours
    c.execute("CREATE TABLE s2 AS SELECT 1 AS id, '<div>a<div>b</div></div>' AS h")
    _run(c, "transform.htmlExtractor", {**p, "separator": "|"}, "o2", src="s2")
    assert c.execute("SELECT o FROM o2").fetchone()[0] == "b|ab"


def test_html_attribute_name_is_case_insensitive_and_oversized_cell_is_null():
    c = duckdb.connect()
    c.execute("CREATE TABLE s AS SELECT 1 AS id, '<a href=\"/x\">l</a>' AS h")
    base = {"column": "h", "outputColumn": "o", "mode": "attribute", "tag": "a"}
    _run(c, "transform.htmlExtractor", {**base, "attribute": "HREF"}, "o", src="s")
    assert c.execute("SELECT o FROM o").fetchone()[0] == "/x"
    c.execute(f"CREATE TABLE big AS SELECT 1 AS id, repeat('x', {attrs._MAX_CELL + 1}) AS h")
    _run(c, "transform.htmlExtractor", {**base, "attribute": "href"}, "ob", src="big")
    _run(
        c,
        "transform.textEncoder",
        {"column": "h", "encoding": "utf-8", "outputColumn": "e"},
        "eb",
        src="big",
    )
    assert c.execute("SELECT o FROM ob").fetchone()[0] is None
    assert c.execute("SELECT e FROM eb").fetchone()[0] is None  # plus de troncature silencieuse


def test_spatial_relator_keeps_identical_input_rows(conn):
    conn.execute("CREATE TABLE dup (k VARCHAR, geometry GEOMETRY)")
    conn.execute("INSERT INTO dup VALUES ('x', ST_Point(0,0)), ('x', ST_Point(0,0))")
    conn.execute("CREATE TABLE sup (geometry GEOMETRY)")
    conn.execute("INSERT INTO sup VALUES (ST_GeomFromText('POLYGON((-1 -1,1 -1,1 1,-1 1,-1 -1))'))")
    _run(conn, "transform.spatialRelator", {"predicate": "within"}, "o", src="dup")
    assert conn.execute("SELECT k, match_count FROM o").fetchall() == [("x", 1), ("x", 1)]


def test_output_column_collisions_and_inf_are_explicit_errors(conn):
    with pytest.raises(PipelineRuntimeError, match="déjà présente"):
        _run(conn, "transform.matcher", {"keyColumns": ["grp"], "matchCountColumn": "val"})
    with pytest.raises(PipelineRuntimeError, match="déjà présente"):
        _run(
            conn,
            "transform.attributeRangeFilter",
            {"column": "val", "ranges": [{"min": 1}], "output": "annotate", "rangeColumn": "id"},
        )
    conn.execute("CREATE TABLE sup (geometry GEOMETRY)")
    with pytest.raises(PipelineRuntimeError, match="déjà présente"):
        _run(conn, "transform.spatialRelator", {"countColumn": "id"})
    for bad in ("inf", "-inf", "nan"):
        with pytest.raises(ValueError):
            attrs.TransformAttributeRangeFilterParams(column="v", ranges=[{"min": float(bad)}])


def test_terminator_raises_a_non_retryable_error(conn):
    from app.pipelines.errors import PipelineTerminatedError

    with pytest.raises(PipelineTerminatedError):
        _run(conn, "transform.terminator", {"condition": "val IS NULL"})


@pytest.mark.postgis
def test_terminator_is_not_replayed_by_the_retry_policy(rig):  # noqa: F811
    """Falsification : sans l'exclusion de PipelineTerminatedError dans jobs.py, le run
    passe en `retrying` (attempt 2) et rejoue ; avec, il échoue définitivement."""
    _app, Session, tenant, _user, item_id, state = rig
    state["fail_t3"] = False
    state["retry"] = {"max": 2, "backoff": "exponential", "delaySeconds": 5}

    def payload(retry):
        p = _payload(retry)
        t3 = next(n for n in p.nodes if n.id == "t3")
        t3.op, t3.params = "transform.terminator", {"condition": "pop >= 1", "message": "stop"}
        return p

    state["payload_fn"] = payload
    run = _exec(Session, tenant, _new_run(Session, tenant, item_id))
    assert (run.status, run.attempt) == ("failed", 1)
    assert "stop" in run.error
    assert state["reader_calls"] == 1

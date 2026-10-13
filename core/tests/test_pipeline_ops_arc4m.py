# SPDX-License-Identifier: Apache-2.0
"""Voie M (ARC vague 4) : testFilter, sampler, neighborFinder, sqlExecutor, geocode, reader.wfs."""

import json

import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE src (id INTEGER, pop INTEGER, geometry GEOMETRY)")
    # 10 points alignés sur x = 1..10
    c.execute("INSERT INTO src SELECT i, i * 10, ST_Point(i, 0) FROM range(1, 11) t(i)")
    return c


def _run(conn, op, params, view="out"):
    c = OPERATIONS[op]
    if c.execute is not None:
        c.execute(conn, input_view="src", view_name=view, params=params)
    else:
        sql = c.compile(params, input_view="src", join_view=None, input_srid=4326)
        conn.execute(f'CREATE TEMP VIEW "{view}" AS {sql}')
    return conn


def _ids(conn, view="out"):
    return [r[0] for r in conn.execute(f'SELECT id FROM "{view}" ORDER BY id').fetchall()]


def test_registry_and_catalog():
    for op in (
        "transform.testFilter",
        "transform.sampler",
        "transform.neighborFinder",
        "transform.sqlExecutor",
        "transform.geocode",
        "reader.wfs",
    ):
        assert op in OPERATIONS
        assert op in ops_catalog()
        assert OPERATIONS[op].engine_license is not None or OPERATIONS[op].kind == "reader"


def test_test_filter_passed_and_failed_partition_the_input(conn):
    base = {"tests": ["pop >= 30", "pop <= 70"]}
    _run(conn, "transform.testFilter", base, "p")
    _run(conn, "transform.testFilter", {**base, "output": "failed"}, "f")
    assert _ids(conn, "p") == [3, 4, 5, 6, 7]
    assert _ids(conn, "f") == [1, 2, 8, 9, 10]


def test_test_filter_or_and_null_counts_as_failed(conn):
    conn.execute("INSERT INTO src VALUES (11, NULL, ST_Point(11, 0))")
    _run(conn, "transform.testFilter", {"tests": ["pop = 10", "pop = 20"], "combine": "or"}, "p")
    assert _ids(conn, "p") == [1, 2]
    _run(conn, "transform.testFilter", {"tests": ["pop > 0"], "output": "failed"}, "f")
    assert _ids(conn, "f") == [11]


def test_test_filter_rejects_table_reference(conn):
    with pytest.raises(SqlSandboxError):
        _run(conn, "transform.testFilter", {"tests": ["id IN (SELECT id FROM src)"]})


def test_sampler_modes(conn):
    _run(conn, "transform.sampler", {"mode": "first", "value": 3}, "a")
    assert _ids(conn, "a") == [1, 2, 3]
    _run(conn, "transform.sampler", {"mode": "everyNth", "value": 4}, "b")
    assert _ids(conn, "b") == [1, 5, 9]
    _run(conn, "transform.sampler", {"mode": "random", "value": 4, "seed": 7}, "c")
    first = _ids(conn, "c")
    assert len(first) == 4
    _run(conn, "transform.sampler", {"mode": "random", "value": 4, "seed": 7}, "d")
    assert _ids(conn, "d") == first  # graine fixe -> reproductible


def test_neighbor_finder_nearest_and_max_distance(conn):
    _run(conn, "transform.neighborFinder", {"count": 1}, "n")
    rows = conn.execute(
        "SELECT source_index, neighbor_index, neighbor_distance, neighbor_rank FROM n "
        "ORDER BY source_index"
    ).fetchall()
    assert len(rows) == 10
    assert all(r[2] == 1.0 and r[3] == 1 for r in rows)
    _run(conn, "transform.neighborFinder", {"count": 2, "maxDistance": 1.5}, "m")
    # extrémités : 1 voisin ; les 8 autres : 2 voisins (distance 1) -> 2 + 16 lignes
    assert conn.execute("SELECT count(*) FROM m").fetchone()[0] == 18
    _run(conn, "transform.neighborFinder", {"count": 1, "maxDistance": 0.5}, "z")
    # aucun voisin : les lignes sont conservées, voisin NULL
    assert (
        conn.execute("SELECT count(*) FILTER (neighbor_index IS NULL) FROM z").fetchone()[0] == 10
    )


def test_sql_executor_select_over_input(conn):
    _run(
        conn,
        "transform.sqlExecutor",
        {"sql": "SELECT id, pop * 2 AS pop2, geometry FROM input WHERE id <= 2"},
    )
    assert conn.execute("SELECT id, pop2 FROM out ORDER BY id").fetchall() == [(1, 20), (2, 40)]
    # la vue d'alias ne fuit pas
    with pytest.raises(duckdb.Error):
        conn.execute("SELECT * FROM input")


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE src",
        "ATTACH 'x.db' AS x",
        "COPY src TO 'x.csv'",
        "INSERT INTO src VALUES (99, 1, NULL)",
        "SELECT 1; DROP TABLE src",
        "SELECT * FROM src",  # table autre que `input`
        "SELECT * FROM read_csv('/etc/passwd')",
        "SELECT * FROM input; SELECT 1",
    ],
)
def test_sql_executor_refuses_non_readonly_or_foreign_tables(conn, sql):
    with pytest.raises((SqlSandboxError, PipelineRuntimeError)):
        _run(conn, "transform.sqlExecutor", {"sql": sql})
    assert conn.execute("SELECT count(*) FROM src").fetchone()[0] == 10


# --- geocode ---------------------------------------------------------------


class _FakeGeocoder:
    def __init__(self, fail_first=False):
        self.calls = []
        self.fail_first = fail_first

    def search(self, q, limit):
        from app.geocoding.provider import GeocodeResult

        self.calls.append(q)
        if self.fail_first and self.calls.count(q) == 1:
            raise RuntimeError("boom")
        if q.startswith("nowhere"):
            return []
        n = int(q.split()[-1])
        return [GeocodeResult(label=f"label {n}", lon=2.0 + n / 1000, lat=45.0)]


@pytest.fixture()
def addr_conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE src (id INTEGER, adresse VARCHAR)")
    rows = [(i, f"rue {i}" if i % 25 else f"nowhere {i}") for i in range(1000)]
    c.executemany("INSERT INTO src VALUES (?, ?)", rows)
    return c


def _geocode(monkeypatch, conn, geocoder, **params):
    from app.pipelines.ops import geocode as g

    monkeypatch.setattr(g, "get_geocoder", lambda: geocoder)
    monkeypatch.setattr(g, "_PER_SECOND", 100000.0)
    OPERATIONS["transform.geocode"].execute(
        conn, input_view="src", view_name="out", params={"addressColumns": ["adresse"], **params}
    )


def test_geocode_1000_addresses_95_percent(monkeypatch, addr_conn):
    _geocode(monkeypatch, addr_conn, _FakeGeocoder())
    total, ok = addr_conn.execute(
        "SELECT count(*), count(*) FILTER (geometry IS NOT NULL) FROM out"
    ).fetchone()
    assert total == 1000 and ok >= 950
    status = dict(
        addr_conn.execute("SELECT geocode_status, count(*) FROM out GROUP BY 1").fetchall()
    )
    assert status == {"trouvé": 960, "non_trouvé": 40}
    assert addr_conn.execute(
        "SELECT ST_X(geometry), ST_Y(geometry), geocode_label FROM out WHERE id = 7"
    ).fetchone() == (2.007, 45.0, "label 7")


def test_geocode_retries_failed_rows_once(monkeypatch, addr_conn):
    _geocode(monkeypatch, addr_conn, _FakeGeocoder(fail_first=True))
    n = addr_conn.execute("SELECT count(*) FILTER (geocode_status = 'erreur') FROM out").fetchone()[
        0
    ]
    assert n == 0


def test_geocode_concatenates_columns_and_dedups(monkeypatch):
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    c.execute("CREATE TABLE src (num VARCHAR, voie VARCHAR)")
    c.execute("INSERT INTO src VALUES ('1','rue 5'),('1','rue 5'),('2','rue 6')")
    gc = _FakeGeocoder()
    from app.pipelines.ops import geocode as g

    monkeypatch.setattr(g, "get_geocoder", lambda: gc)
    monkeypatch.setattr(g, "_PER_SECOND", 100000.0)
    OPERATIONS["transform.geocode"].execute(
        c, input_view="src", view_name="out", params={"addressColumns": ["num", "voie"]}
    )
    assert sorted(gc.calls) == ["1 rue 5", "2 rue 6"]  # dédoublonné
    assert c.execute("SELECT count(*) FROM out WHERE geometry IS NOT NULL").fetchone()[0] == 3


def test_geocode_blocked_egress_fails_the_node(monkeypatch, addr_conn):
    from app.geocoding.egress import EgressBlockedError
    from app.pipelines.ops import geocode as g

    class Blocked:
        def search(self, q, limit):
            raise EgressBlockedError("interdit")

    monkeypatch.setattr(g, "get_geocoder", lambda: Blocked())
    monkeypatch.setattr(g, "_PER_SECOND", 100000.0)
    with pytest.raises(PipelineRuntimeError, match="every address"):
        OPERATIONS["transform.geocode"].execute(
            addr_conn, input_view="src", view_name="out", params={"addressColumns": ["adresse"]}
        )


def test_geocode_output_srid_is_4326():
    c = OPERATIONS["transform.geocode"]
    assert c.output_srid({"addressColumns": ["a"]}, op=c.op, input_srid=2154) == 4326


# --- reader.wfs ------------------------------------------------------------

_FC = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "a", "n": 1},
            "geometry": {"type": "Point", "coordinates": [3.0, 45.0]},
        },
        {
            "type": "Feature",
            "properties": {"name": "b", "n": 2},
            "geometry": {"type": "Point", "coordinates": [4.0, 46.0]},
        },
    ],
}


class _Resp:
    status_code = 200
    headers = {"content-type": "application/json"}

    def __init__(self, body):
        self.content = json.dumps(body).encode()

    def raise_for_status(self):
        pass


def _read_wfs(c, params):
    from app.pipelines.ops import wfs

    return wfs.read_wfs(
        c,
        session=None,
        tenant_id="t",
        node_id="n",
        params=params,
        view_name="node_n",
        user=None,
        base_uri="",
    )


def test_wfs_reader_materializes_features(monkeypatch):
    from app.pipelines.ops import wfs

    seen = {}

    class S:
        def get(self, url, params=None, **kw):
            seen["url"], seen["params"] = url, params
            return _Resp(_FC)

    monkeypatch.setattr(wfs, "build_guarded_session", lambda: S())
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    srid = _read_wfs(c, {"url": "https://wfs.example.org/ows", "typeName": "ns:roads"})
    assert srid == 4326
    assert seen["params"]["request"] == "GetFeature" and seen["params"]["typeNames"] == "ns:roads"
    assert c.execute("SELECT name, n, ST_AsText(geometry) FROM node_n ORDER BY n").fetchall() == [
        ("a", 1, "POINT (3 45)"),
        ("b", 2, "POINT (4 46)"),
    ]


def test_wfs_reader_egress_blocked():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    with pytest.raises(PipelineRuntimeError, match="egress"):
        _read_wfs(c, {"url": "http://127.0.0.1/ows", "typeName": "x"})


def test_wfs_reader_refuses_non_http_scheme():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    with pytest.raises(PipelineRuntimeError):
        _read_wfs(c, {"url": "file:///etc/passwd", "typeName": "x"})


def test_sql_executor_allows_cte_but_not_qualified_tables(conn):
    _run(
        conn,
        "transform.sqlExecutor",
        {"sql": "WITH big AS (SELECT * FROM input WHERE id > 8) SELECT id FROM big"},
    )
    assert _ids(conn) == [9, 10]
    with pytest.raises(SqlSandboxError):
        _run(conn, "transform.sqlExecutor", {"sql": "SELECT * FROM main.src"}, "o2")


def test_wfs_reader_registered_in_readers():
    from app.pipelines.registries import READERS

    assert "reader.wfs" in READERS

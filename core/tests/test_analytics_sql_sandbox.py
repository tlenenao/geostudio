# SPDX-License-Identifier: Apache-2.0
import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.sql_sandbox import (
    SqlSandboxError,
    collect_table_refs,
    parse_ast,
    run_analyst_sql,
    validate_select_only,
)
from app.collections.introspection import ColumnInfo, TableInfo


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


def test_select_only_accepts_select(conn):
    validate_select_only(parse_ast(conn, "SELECT 1"))  # ne lève pas


def test_select_only_rejects_non_select(conn):
    for sql in [
        "CREATE TABLE x(i int)",
        "COPY (SELECT 1) TO 'x'",
        "ATTACH 'y.db'",
        "PRAGMA version",
    ]:
        with pytest.raises(SqlSandboxError):
            validate_select_only(parse_ast(conn, sql))


def test_select_only_rejects_multiple_statements(conn):
    with pytest.raises(SqlSandboxError):
        validate_select_only(parse_ast(conn, "SELECT 1; SELECT 2"))


def test_parse_ast_rejects_syntax_error(conn):
    with pytest.raises(SqlSandboxError):
        parse_ast(conn, "SELECT FROM WHERE")


def test_collect_table_refs_finds_base_tables(conn):
    refs = collect_table_refs(
        parse_ast(conn, "SELECT * FROM villes v JOIN routes r ON r.id = v.id")
    )
    assert {"villes", "routes"} <= refs


INFO = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


def _write(base_dir, rows, *, tenant_id="default", collection_id="villes"):
    part = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    part.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(part / "part-1.parquet")


def _spatial_conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    return c


def test_run_reduces_to_current_state(tmp_path):
    _write(
        tmp_path,
        [
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            },
            {
                "id": 1,
                "region": "Nord",
                "pop": 99,
                "_op": "insert",
                "_lsn": 2,
                "_ts": 2.0,
                "geometry": Point(0, 0),
            },  # version + récente
            {
                "id": 2,
                "region": "Sud",
                "pop": 5,
                "_op": "delete",
                "_lsn": 3,
                "_ts": 3.0,
                "geometry": Point(1, 1),
            },  # tombstone
        ],
    )
    conn = _spatial_conn()
    try:
        cols, rows, trunc = run_analyst_sql(
            conn,
            sql="SELECT region, sum(pop) AS total FROM villes GROUP BY region",
            allowed={"villes": INFO},
            base_uri=str(tmp_path),
            tenant_id="default",
        )
    finally:
        conn.close()
    assert trunc is False
    assert cols == ["region", "total"]
    assert rows == [["Nord", 99]]  # version max(_lsn) gagne, tombstone exclue


def test_isolation_blocks_arbitrary_read_parquet(tmp_path):
    _write(
        tmp_path,
        [
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
    )
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):
            run_analyst_sql(
                conn,
                sql=f"SELECT * FROM read_parquet('{tmp_path}/**/*.parquet')",
                allowed={"villes": INFO},
                base_uri=str(tmp_path),
                tenant_id="default",
            )
    finally:
        conn.close()


def test_unauthorized_view_is_not_materialized(tmp_path):
    _write(
        tmp_path,
        [
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
        collection_id="secret",
    )
    conn = _spatial_conn()
    try:
        with pytest.raises(SqlSandboxError):  # "secret" absent de allowed → table introuvable
            run_analyst_sql(
                conn,
                sql="SELECT * FROM secret",
                allowed={"villes": INFO},
                base_uri=str(tmp_path),
                tenant_id="default",
            )
    finally:
        conn.close()


def test_row_cap_truncates(tmp_path):
    _write(
        tmp_path,
        [
            {
                "id": i,
                "region": "N",
                "pop": i,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
            for i in range(1, 12)
        ],
    )
    conn = _spatial_conn()
    try:
        # Forcer un plafond bas via monkeypatch de ROW_CAP serait fragile ; à la place,
        # vérifier la sémantique de troncature avec un cap réduit passé par la constante.
        import app.analytics.sql_sandbox as sandbox

        old = sandbox.ROW_CAP
        sandbox.ROW_CAP = 5
        try:
            cols, rows, trunc = run_analyst_sql(
                conn,
                sql="SELECT id FROM villes ORDER BY id",
                allowed={"villes": INFO},
                base_uri=str(tmp_path),
                tenant_id="default",
            )
        finally:
            sandbox.ROW_CAP = old
    finally:
        conn.close()
    assert trunc is True
    assert len(rows) == 5


def test_materialization_is_bounded_by_the_statement_timeout(tmp_path, monkeypatch):
    """REV-028 : le budget de temps (STATEMENT_TIMEOUT_S) doit couvrir la
    phase de matérialisation, pas seulement la requête finale — sans quoi
    une collection lente/volumineuse à matérialiser (dedup CTE coûteuse)
    peut épuiser un worker indéfiniment sans jamais être interrompue.
    `_materialize` est remplacé par un calcul authentiquement compute-bound
    et non borné (même patron que
    test_evaluate_condition_bounds_a_compute_bound_table_function côté
    app.configs.alert_condition) — DuckDB doit être interrompu bien avant
    de le terminer, pas seulement une fois la requête finale atteinte."""
    _write(
        tmp_path,
        [
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(0, 0),
            }
        ],
    )
    conn = _spatial_conn()
    monkeypatch.setattr("app.analytics.sql_sandbox.STATEMENT_TIMEOUT_S", 0.2)

    def _slow_materialize(conn, *, name, table_info, base_uri, tenant_id):
        conn.execute("SELECT count(*) FROM range(100000000000) t1, range(100000) t2")

    import app.analytics.sql_sandbox as sandbox

    monkeypatch.setattr(sandbox, "_materialize", _slow_materialize)

    try:
        with pytest.raises(SqlSandboxError):
            run_analyst_sql(
                conn,
                sql="SELECT * FROM villes",
                allowed={"villes": INFO},
                base_uri=str(tmp_path),
                tenant_id="default",
            )
    finally:
        conn.close()


def test_geometry_cell_is_json_safe(tmp_path):
    _write(
        tmp_path,
        [
            {
                "id": 1,
                "region": "N",
                "pop": 1,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(3, 4),
            }
        ],
    )
    conn = _spatial_conn()
    try:
        cols, rows, _ = run_analyst_sql(
            conn,
            sql="SELECT ST_AsText(geometry) AS g FROM villes",
            allowed={"villes": INFO},
            base_uri=str(tmp_path),
            tenant_id="default",
        )
    finally:
        conn.close()
    assert rows == [["POINT (3 4)"]]

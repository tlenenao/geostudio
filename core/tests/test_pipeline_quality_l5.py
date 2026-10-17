# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 4 (AUD-080) : collisions de colonnes de sortie, clé NULL/doublon de
detectChanges, validateAttributes enrichi, message d'erreur lisible."""

import duckdb
import pytest

from app.pipelines import compiler
from app.pipelines.errors import PipelineRuntimeError


@pytest.fixture()
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def _cols(conn, v):
    return [d[0] for d in conn.execute(f'DESCRIBE "{v}"').fetchall()]


def _sql(conn, op, params, join=True):
    return compiler.compile_transform_sql(
        op,
        params,
        input_view="a",
        join_view="b" if join else None,
        input_srid=None,
        input_columns=_cols(conn, "a"),
        join_columns=_cols(conn, "b") if join else None,
    )


def test_detect_changes_null_key_is_invalid_not_inserted_and_deleted(conn):
    conn.execute("CREATE TABLE a AS SELECT NULL::INT AS k, 'x' AS v")
    conn.execute("CREATE TABLE b AS SELECT NULL::INT AS k, 'x' AS v")
    rows = conn.execute(
        _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})
    ).fetchall()
    assert sorted(r[-1] for r in rows) == ["invalid", "invalid"]


def test_detect_changes_duplicate_key_fails(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, 'x' AS v UNION ALL SELECT 1, 'y'")
    conn.execute("CREATE TABLE b AS SELECT 1 AS k, 'x' AS v")
    sql = _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})
    with pytest.raises(duckdb.InvalidInputException, match="clé dupliquée"):
        conn.execute(sql).fetchall()


def test_detect_changes_refuses_status_column_clash(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, 'x' AS s")
    conn.execute("CREATE TABLE b AS SELECT 1 AS k, 'x' AS s")
    with pytest.raises(PipelineRuntimeError, match="s"):
        _sql(conn, "transform.detectChanges", {"keyColumns": ["k"], "statusColumn": "s"})


def test_validate_attributes_not_blank_and_null_aware_unique(conn):
    conn.execute(
        "CREATE TABLE a AS SELECT * FROM (VALUES (1, 'x'), (2, '  '), (NULL, 'z'), (NULL, 'w')) "
        "t(k, label)"
    )
    conn.execute("CREATE TABLE b AS SELECT 1 AS unused")
    sql = _sql(
        conn,
        "transform.validateAttributes",
        {
            "notBlankColumns": ["label"],
            "notBlankResultColumn": "label_ok",
            "uniqueColumns": ["k"],
            "uniqueResultColumn": "k_unique",
        },
        join=False,
    )
    rows = conn.execute(f"SELECT k, label_ok, k_unique FROM ({sql})").fetchall()
    by_k = {r[0]: r for r in rows if r[0] is not None}
    assert by_k[1][1:] == (True, True)
    assert by_k[2][1] is False  # '  ' est vide après trim
    assert [r[2] for r in rows if r[0] is None] == [None, None]  # clé NULL : indéterminé


def test_validate_attributes_refuses_result_column_clash(conn):
    conn.execute("CREATE TABLE a AS SELECT 1 AS k, true AS ok")
    conn.execute("CREATE TABLE b AS SELECT 1 AS unused")
    with pytest.raises(PipelineRuntimeError, match="ok"):
        _sql(
            conn,
            "transform.validateAttributes",
            {"nonNullColumns": ["k"], "nonNullResultColumn": "ok"},
            join=False,
        )


def test_node_error_strips_multi_word_duckdb_prefix():
    from app.configs.schemas import PipelineNode
    from app.pipelines.runtime import _node_error

    node = PipelineNode(id="n1", kind="transform", op="transform.filter", params={"expr": "1"})
    err = _node_error(node, Exception("Invalid Input Error: clé dupliquée"))
    assert str(err) == "nœud 'n1' (transform.filter) : clé dupliquée"

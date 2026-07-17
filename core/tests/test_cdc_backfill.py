# SPDX-License-Identifier: Apache-2.0
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.cdc.backfill import backfill_table, current_wal_lsn

pytestmark = pytest.mark.postgis


@pytest.fixture()
def seeded_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill"))
        conn.execute(text(
            "CREATE TABLE t_backfill (id serial PRIMARY KEY, v text, "
            "geom geometry(Point, 4326))"
        ))
        conn.execute(text(
            "INSERT INTO t_backfill (v, geom) VALUES "
            "('a', ST_SetSRID(ST_MakePoint(1, 1), 4326)), "
            "('b', ST_SetSRID(ST_MakePoint(2, 2), 4326))"
        ))
    yield "t_backfill"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill"))


def test_current_wal_lsn_returns_positive_int(pg_session_factory):
    with pg_session_factory() as session:
        lsn = current_wal_lsn(session)
    assert isinstance(lsn, int)
    assert lsn > 0


def test_backfill_table_reads_all_rows_as_inserts(seeded_table, pg_session_factory):
    with pg_session_factory() as session:
        boundary = current_wal_lsn(session)
        rows = backfill_table(
            session, table_name=seeded_table, pk_column="id", geometry_column="geom",
            boundary_lsn=boundary, flush_ts=42.0,
        )
    assert len(rows) == 2
    assert all(r.op == "insert" for r in rows)
    assert all(r.lsn == boundary for r in rows)
    assert all(r.ts == 42.0 for r in rows)
    assert all(r.geometry_wkb_hex is not None for r in rows)


def test_backfill_table_with_null_geometry_row(pg_session_factory, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nullgeom"))
        conn.execute(text(
            "CREATE TABLE t_backfill_nullgeom (id serial PRIMARY KEY, v text, "
            "geom geometry(Point, 4326))"
        ))
        conn.execute(text(
            "INSERT INTO t_backfill_nullgeom (v, geom) VALUES "
            "('has_geom', ST_SetSRID(ST_MakePoint(1, 1), 4326)), "
            "('null_geom', NULL)"
        ))
    with pg_session_factory() as session:
        boundary = current_wal_lsn(session)
        rows = backfill_table(
            session, table_name="t_backfill_nullgeom", pk_column="id", geometry_column="geom",
            boundary_lsn=boundary, flush_ts=1.0,
        )
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nullgeom"))

    assert len(rows) == 2
    by_v = {r.columns["v"]: r for r in rows}

    null_row = by_v["null_geom"]
    assert null_row.geometry_wkb_hex is None
    assert "geom" not in null_row.columns

    geom_row = by_v["has_geom"]
    assert geom_row.geometry_wkb_hex is not None
    assert "geom" not in geom_row.columns


def test_backfill_table_normalizes_decimal_numeric_column_to_float(pg_session_factory, pg_engine):
    """Régression Critère 3 (task-11-report.md) : SELECT * brut renvoie une
    colonne NUMERIC comme decimal.Decimal via SQLAlchemy/psycopg — sans
    normalisation, un lot mélangeant une ligne de backfill (Decimal) et une
    ligne rejouée du flux live (float, décodée du JSON wal2json) pour la
    même colonne NUMERIC fait crasher pa.Table.from_pandas. isinstance()
    volontairement utilisé plutôt qu'une égalité numérique : Decimal("1.5")
    == 1.5 est vrai en Python, un test par égalité passerait même si le bug
    n'était pas corrigé."""
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_numeric"))
        conn.execute(text(
            "CREATE TABLE t_backfill_numeric (id serial PRIMARY KEY, score numeric(3,1))"
        ))
        conn.execute(text("INSERT INTO t_backfill_numeric (score) VALUES (1.5)"))
    with pg_session_factory() as session:
        rows = backfill_table(
            session, table_name="t_backfill_numeric", pk_column="id", geometry_column=None,
            boundary_lsn=1, flush_ts=0.0,
        )
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_numeric"))

    assert len(rows) == 1
    score = rows[0].columns["score"]
    assert isinstance(score, float)
    assert not isinstance(score, Decimal)
    assert score == 1.5


def test_backfill_table_without_geometry_column(pg_session_factory, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nogeom"))
        conn.execute(text("CREATE TABLE t_backfill_nogeom (id serial PRIMARY KEY, v text)"))
        conn.execute(text("INSERT INTO t_backfill_nogeom (v) VALUES ('x')"))
    with pg_session_factory() as session:
        rows = backfill_table(
            session, table_name="t_backfill_nogeom", pk_column="id", geometry_column=None,
            boundary_lsn=1, flush_ts=0.0,
        )
    assert len(rows) == 1
    assert rows[0].geometry_wkb_hex is None
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_backfill_nogeom"))

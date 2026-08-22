# SPDX-License-Identifier: Apache-2.0
"""Index GiST par collection (spec SP-24 §3.2). Aucun index spatial n'existait
dans le dépôt avant SP-24 : tout filtre bbox (OGC Features, geom_intersects du
cross-filter, et désormais les tuiles) était un scan complet de table."""

import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl, spatial_index_name

pytestmark = pytest.mark.postgis


def _indexes(conn, table: str) -> set[str]:
    rows = conn.execute(
        text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = :t"),
        {"t": table},
    ).scalars()
    return set(rows)


@pytest.fixture()
def table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))
        conn.execute(
            text("CREATE TABLE idx_probe (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        )
    yield "idx_probe"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_probe"))


def test_apply_collection_ddl_creates_a_gist_index(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name(table) in _indexes(conn, table)
        method = conn.execute(
            text(
                "SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam "
                "WHERE c.relname = :n"
            ),
            {"n": spatial_index_name(table)},
        ).scalar()
        assert method == "gist"


def test_apply_collection_ddl_is_still_idempotent(pg_engine, table):
    from sqlalchemy.orm import Session

    with Session(pg_engine) as s:
        apply_collection_ddl(s, table)
        apply_collection_ddl(s, table)
        s.commit()


def test_a_table_without_geometry_is_left_alone(pg_engine):
    from sqlalchemy.orm import Session

    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))
        conn.execute(text("CREATE TABLE idx_flat (id serial PRIMARY KEY, nom text)"))
    with Session(pg_engine) as s:
        apply_collection_ddl(s, "idx_flat")
        s.commit()
    with pg_engine.begin() as conn:
        assert spatial_index_name("idx_flat") not in _indexes(conn, "idx_flat")
        conn.execute(text("DROP TABLE IF EXISTS idx_flat"))


def test_the_index_name_stays_within_the_postgres_identifier_limit():
    # tableName est plafonné à 50 par CollectionCreate (configs/schemas.py) ;
    # le préfixe doit laisser la marge.
    assert len(spatial_index_name("x" * 50)) <= 63

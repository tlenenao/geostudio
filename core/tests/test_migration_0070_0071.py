# SPDX-License-Identifier: Apache-2.0
"""Migrations 0070 (REV-347) et 0071 (REV-348) sur base NON vide, aller-retour (piège n°8)."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def _seed_collection_and_record(conn) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, is_public, editable, sensitive_fields, created_at, "
            "updated_at) VALUES ('c1','t1','u1','villes','V','','id',false,true,'[]',now(),now())"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO harvest_sources (id, tenant_id, owner_id, type, url, created_at, "
            "updated_at) VALUES ('hs1','t1','u1','stac','http://x',now(),now())"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO harvest_records (id, tenant_id, source_id, external_id, collection_id, "
            "harvested_at) VALUES ('h1','t1','hs1','x','c1',now())"
        )
    )


def test_0070_collection_delete_nulls_harvest_link_both_ways(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0068")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        _seed_collection_and_record(conn)
    # avant 0070 : le défaut (FK sans ON DELETE)
    with pytest.raises(sa.exc.IntegrityError), eng.begin() as conn:
        conn.execute(sa.text("DELETE FROM collections WHERE id = 'c1'"))
    eng.dispose()

    command.upgrade(_cfg(), "0070")
    command.downgrade(_cfg(), "0068")
    assert _scalar(url, "SELECT count(*) FROM harvest_records") == 1
    command.upgrade(_cfg(), "0070")

    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(sa.text("DELETE FROM collections WHERE id = 'c1'"))
    eng.dispose()
    assert _scalar(url, "SELECT collection_id FROM harvest_records WHERE id = 'h1'") is None


def _index_method(url: str, name: str) -> str:
    return _scalar(
        url,
        "SELECT am.amname FROM pg_class c JOIN pg_am am ON am.oid = c.relam "
        f"WHERE c.relname = '{name}'",
    )


def test_0071_embedding_indexes_hnsw_round_trip_with_data(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0070")
    eng = sa.create_engine(url)
    vec = "[" + ",".join(["0.1"] * 1536) + "]"
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at, embedding) "
                "VALUES ('i1','t1','u1','map','M','[]',now(),now(), CAST(:v AS vector))"
            ),
            {"v": vec},
        )
    eng.dispose()
    assert _index_method(url, "ix_items_embedding") == "ivfflat"

    command.upgrade(_cfg(), "0071")
    assert _index_method(url, "ix_items_embedding") == "hnsw"
    assert _index_method(url, "ix_collections_embedding") == "hnsw"

    command.downgrade(_cfg(), "0070")
    assert _index_method(url, "ix_items_embedding") == "ivfflat"
    assert _scalar(url, "SELECT count(*) FROM items WHERE embedding IS NOT NULL") == 1
    command.upgrade(_cfg(), "0071")
    assert _index_method(url, "ix_items_embedding") == "hnsw"

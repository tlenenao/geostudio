# SPDX-License-Identifier: Apache-2.0
"""Migration 0052 (statut de contenu, ARC-05) sur base NON vide : up, down, ré-up."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0052_defaults_existing_items_and_round_trips(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0051")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('i1','t1','u1','map','A','[]',now(),now())"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0052")
    assert _scalar(url, "SELECT content_status FROM items WHERE id = 'i1'") == "none"
    assert _scalar(url, "SELECT categories::text FROM items WHERE id = 'i1'") == "[]"

    command.downgrade(_cfg(), "0051")
    assert _scalar(url, "SELECT count(*) FROM items") == 1
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'items' AND column_name IN ('content_status','categories')",
        )
        == 0
    )

    command.upgrade(_cfg(), "0052")
    assert _scalar(url, "SELECT content_status FROM items WHERE id = 'i1'") == "none"

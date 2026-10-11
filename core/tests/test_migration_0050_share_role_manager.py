# SPDX-License-Identifier: Apache-2.0
"""Migration 0050 (rôle de partage « manager », REV-270/P14.12) sur base NON
vide, upgrade puis downgrade puis ré-upgrade (piège n°8)."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0050_promotes_editor_to_manager_and_round_trips(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0049")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('i1','t1','u1','app','A','[]',now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, pk_column,"
                " geometry_column, geometry_type, srid, created_at, updated_at) "
                "VALUES ('c1','t1','u1','c1','C','id','geometry','Point',4326,now(),now())"
            )
        )
        for gid in ("g1", "g2"):
            conn.execute(
                sa.text(
                    "INSERT INTO groups (id, tenant_id, name, created_by, created_at) "
                    f"VALUES ('{gid}','t1','{gid}','u1',now())"
                )
            )
        conn.execute(
            sa.text(
                "INSERT INTO item_shares (item_id, group_id, tenant_id, role) VALUES "
                "('i1','g1','t1','editor'), ('i1','g2','t1','viewer')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO collection_shares (collection_id, group_id, tenant_id, role) "
                "VALUES ('c1','g1','t1','editor')"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0050")
    q = "SELECT role FROM item_shares WHERE group_id = '{}'"
    assert _scalar(url, q.format("g1")) == "manager"  # promu : aucun droit retiré
    assert _scalar(url, q.format("g2")) == "viewer"
    assert _scalar(url, "SELECT role FROM collection_shares") == "manager"
    assert (
        _scalar(url, "SELECT count(*) FROM audit_log WHERE action = 'sharing.role_migrated'") == 2
    )
    eng = sa.create_engine(url)
    with eng.begin() as conn, pytest.raises(sa.exc.IntegrityError):
        conn.execute(sa.text("UPDATE item_shares SET role = 'admin' WHERE group_id = 'g2'"))
    eng.dispose()

    command.downgrade(_cfg(), "0049")
    assert _scalar(url, q.format("g1")) == "editor"
    assert _scalar(url, q.format("g2")) == "viewer"
    assert _scalar(url, "SELECT role FROM collection_shares") == "editor"

    command.upgrade(_cfg(), "0050")
    assert _scalar(url, q.format("g1")) == "manager"

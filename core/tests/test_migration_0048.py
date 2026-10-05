# SPDX-License-Identifier: Apache-2.0
"""Migration 0048 (collection_export_jobs, REV-283e) sur base NON vide, upgrade
puis downgrade puis ré-upgrade (piège n°8). Base jetable de test_migrations_p09."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0048_round_trip_on_non_empty_database(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0047")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
    eng.dispose()

    command.upgrade(_cfg(), "0048")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, pk_column,"
                " geometry_column, geometry_type, srid, created_at, updated_at) "
                "VALUES ('c1','t1','u1','c1','C','id','geometry','Point',4326,now(),now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO collection_export_jobs (id, tenant_id, collection_id, requested_by,"
                " format, masked, created_at, expires_at) "
                "VALUES ('j1','t1','c1','u1','csv',true,now(),now())"
            )
        )
    eng.dispose()
    assert _scalar(url, "SELECT status FROM collection_export_jobs") == "pending"

    command.downgrade(_cfg(), "0047")
    assert _scalar(url, "SELECT count(*) FROM tenants WHERE id = 't1'") == 1
    assert _scalar(url, "SELECT to_regclass('collection_export_jobs') IS NULL") is True

    command.upgrade(_cfg(), "0048")
    assert _scalar(url, "SELECT count(*) FROM collection_export_jobs") == 0

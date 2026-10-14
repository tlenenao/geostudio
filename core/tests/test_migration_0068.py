# SPDX-License-Identifier: Apache-2.0
"""Migration 0068 (rate_limit_counters, ARC-32) sur base NON vide, aller-retour (piège n°8)."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0068_round_trip_on_non_empty_database(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0066")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
    eng.dispose()

    command.upgrade(_cfg(), "0068")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(sa.text("INSERT INTO rate_limit_counters VALUES ('h','sql',1,3)"))
    eng.dispose()
    assert _scalar(
        url, "SELECT relpersistence = 'u' FROM pg_class WHERE relname = 'rate_limit_counters'"
    )

    command.downgrade(_cfg(), "0066")
    assert _scalar(url, "SELECT count(*) FROM tenants WHERE id = 't1'") == 1
    assert _scalar(url, "SELECT to_regclass('rate_limit_counters') IS NULL") is True
    command.upgrade(_cfg(), "0068")

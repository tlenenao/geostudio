# SPDX-License-Identifier: Apache-2.0
"""Migration 0066 (outbound_webhooks/outbox/file_triggers, ARC4-F6) sur base NON vide,
upgrade -> downgrade -> ré-upgrade (piège n°8). Base jetable de test_migrations_p09."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0066_round_trip_on_non_empty_database(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0062")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
    eng.dispose()

    command.upgrade(_cfg(), "0066")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO outbound_webhooks (id, tenant_id, url, event_types, secret_name,"
                " created_by, created_at) VALUES ('h1','t1','https://x.example/h',"
                "'[\"item.created\"]','sig','u1',now())"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO outbox (id, tenant_id, webhook_id, event_type, payload, status,"
                " next_attempt_at, created_at) VALUES ('e1','t1','h1','item.created','{}',"
                "'pending',now(),now())"
            )
        )
    eng.dispose()
    assert _scalar(url, "SELECT enabled AND consecutive_failures = 0 FROM outbound_webhooks")
    assert _scalar(url, "SELECT attempts FROM outbox") == 0

    command.downgrade(_cfg(), "0062")
    assert _scalar(url, "SELECT count(*) FROM tenants WHERE id = 't1'") == 1
    assert _scalar(url, "SELECT to_regclass('outbox') IS NULL") is True
    command.upgrade(_cfg(), "0066")
    assert _scalar(url, "SELECT to_regclass('file_trigger_seen') IS NOT NULL") is True

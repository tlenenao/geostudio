# SPDX-License-Identifier: Apache-2.0
"""Migration 0072 (purge_receipts.status/error, REV-344) sur base NON vide, aller-retour
(piège n°8)."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0072_existing_receipts_become_done_and_round_trip(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0071")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO purge_receipts (id, tenant_slug, requested_by_user_id, "
                "requested_at, counts) VALUES ('p1','gone','u1',now(),'{}')"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0072")
    assert _scalar(url, "SELECT status FROM purge_receipts WHERE id = 'p1'") == "done"
    assert _scalar(url, "SELECT error FROM purge_receipts WHERE id = 'p1'") is None

    command.downgrade(_cfg(), "0071")
    assert _scalar(url, "SELECT count(*) FROM purge_receipts") == 1
    command.upgrade(_cfg(), "0072")
    assert _scalar(url, "SELECT status FROM purge_receipts WHERE id = 'p1'") == "done"

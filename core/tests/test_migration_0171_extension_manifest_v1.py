# SPDX-License-Identifier: Apache-2.0
"""Migration 0171 (manifeste v1 des extensions, AUD-109/110) sur base NON vide, aller-retour
(piège n°8)."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_0171_existing_extension_gets_v1_defaults_and_round_trips(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0170")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text(
                "INSERT INTO extensions (id, tenant_id, owner_id, tag, label, module_url, props, "
                "default_size, permissions, enabled, created_at) VALUES ('e1','t1','u1','x-y','L',"
                "'https://c.example.com/w.js','[]','{}','{}',true,now())"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0171")
    assert _scalar(url, "SELECT sdk_version FROM extensions WHERE id='e1'") == 1
    assert _scalar(url, "SELECT integrity FROM extensions WHERE id='e1'") is None
    assert _scalar(url, "SELECT connect_hosts::text FROM extensions WHERE id='e1'") == "[]"
    assert _scalar(url, "SELECT img_hosts::text FROM extensions WHERE id='e1'") == "[]"

    command.downgrade(_cfg(), "0170")
    assert _scalar(url, "SELECT count(*) FROM extensions") == 1
    command.upgrade(_cfg(), "0171")
    assert _scalar(url, "SELECT sdk_version FROM extensions WHERE id='e1'") == 1

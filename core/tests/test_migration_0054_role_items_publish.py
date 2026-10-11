# SPDX-License-Identifier: Apache-2.0
"""Migration 0054 (`items.publish`, ARC-07) sur base NON vide : up, down, ré-up."""

import json

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def _privs(url: str) -> dict[str, list[str]]:
    eng = sa.create_engine(url)
    try:
        with eng.connect() as conn:
            rows = conn.execute(sa.text("SELECT slug, privileges FROM roles")).all()
    finally:
        eng.dispose()
    return {slug: (p if isinstance(p, list) else json.loads(p)) for slug, p in rows}


def test_0054_adds_items_publish_to_admin_and_creator_only(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0051")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1','t1','T',now())")
        )
        for slug, builtin in (("admin", True), ("creator", True), ("reader", True), ("x", False)):
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) VALUES (:s, 't1', :s, :s, :b, "
                    "CAST('[\"maps.manage\"]' AS json), now(), now())"
                ),
                {"s": slug, "b": builtin},
            )
    eng.dispose()

    command.upgrade(_cfg(), "0054")
    after = _privs(url)
    assert "items.publish" in after["admin"] and "items.publish" in after["creator"]
    assert after["admin"][0] == "maps.manage"  # existant préservé
    assert after["reader"] == ["maps.manage"]  # Lecteur inchangé
    assert after["x"] == ["maps.manage"]  # rôle sur mesure non touché
    eng = sa.create_engine(url)
    with eng.connect() as conn:
        n = conn.execute(
            sa.text("SELECT count(*) FROM audit_log WHERE action = 'role.privilege_added'")
        ).scalar_one()
    eng.dispose()
    assert n == 2

    command.downgrade(_cfg(), "0051")
    assert _privs(url)["admin"] == ["maps.manage"]
    assert _privs(url)["creator"] == ["maps.manage"]

    command.upgrade(_cfg(), "0054")
    assert "items.publish" in _privs(url)["creator"]

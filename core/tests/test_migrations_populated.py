# SPDX-License-Identifier: Apache-2.0
"""G3 / AUD-188 à 192 : migrations sur base PEUPLÉE, dans les deux sens (piège n°8).

0005/0007 (backfill avant contrainte), FK `NOT VALID` puis validées (0043/0070), index HNSW
construits sans verrou (0071), gardes de downgrade destructif, aller-retour base→head→base."""

import pytest
import sqlalchemy as sa

from alembic import command
from tests.test_migrations_p09 import _cfg, _scalar, _seed_base
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway
ALLOW = "GEOSTUDIO_ALLOW_DESTRUCTIVE_DOWNGRADE"


def test_0005_0007_backfill_on_non_empty_base(throwaway_database_url, monkeypatch):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0004")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1','t1','T',now())")
        )
        conn.execute(
            sa.text(
                "INSERT INTO users (id, tenant_id, oidc_sub, username, created_at, updated_at) "
                "VALUES ('u1','t1','s','alice',now(),now())"
            )
        )
        for cid, item in (("c1", None), ("c2", "gn-7")):
            conn.execute(
                sa.text(
                    "INSERT INTO configs (id, kind, item_id, current_version, created_at, "
                    "updated_at, tenant_id) VALUES (:i,'map',:it,1,now(),now(),'t1')"
                ),
                {"i": cid, "it": item},
            )
    command.upgrade(_cfg(), "0006")
    with eng.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO groups (id, tenant_id, name, created_at) VALUES ('g1','t1','G',now())"
            )
        )
    eng.dispose()

    command.upgrade(_cfg(), "0007")
    assert _scalar(url, "SELECT item_id FROM configs WHERE id='c1'") == "c1"
    assert _scalar(url, "SELECT item_id FROM configs WHERE id='c2'") == "gn-7"
    assert _scalar(url, "SELECT owner_id FROM items WHERE id='gn-7'") == "u1"
    assert _scalar(url, "SELECT created_by FROM groups WHERE id='g1'") == "u1"
    assert (
        _scalar(
            url,
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name='configs' AND column_name='item_id'",
        )
        == "NO"
    )

    # downgrade : 0005 détruit `items` -> refusé tant qu'il y a des lignes, accepté avec accord
    monkeypatch.delenv(ALLOW, raising=False)
    with pytest.raises(RuntimeError, match="downgrade refusé"):
        command.downgrade(_cfg(), "0004")
    assert _scalar(url, "SELECT count(*) FROM items") == 2  # rien n'a été exécuté
    monkeypatch.setenv(ALLOW, "1")
    command.downgrade(_cfg(), "0004")
    command.upgrade(_cfg(), "0007")
    assert _scalar(url, "SELECT count(*) FROM items") == 2


def test_0005_refuses_config_without_owner(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0004")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        conn.execute(
            sa.text("INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1','t1','T',now())")
        )
        conn.execute(
            sa.text(
                "INSERT INTO configs (id, kind, current_version, created_at, updated_at, "
                "tenant_id) VALUES ('c1','map',1,now(),now(),'t1')"
            )
        )
    eng.dispose()
    with pytest.raises(RuntimeError, match="sans utilisateur"):
        command.upgrade(_cfg(), "0005")
    assert _scalar(url, "SELECT count(*) FROM configs") == 1  # transaction annulée


def test_foreign_keys_validated_and_hnsw_valid_after_upgrade(throwaway_database_url):
    url = throwaway_database_url
    command.upgrade(_cfg(), "0071")
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM pg_constraint WHERE NOT convalidated AND contype = 'f'",
        )
        == 0
    )
    assert (
        _scalar(
            url,
            "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname IN ('ix_items_embedding','ix_collections_embedding') AND i.indisvalid",
        )
        == 2
    )
    assert _scalar(url, "SELECT count(*) FROM pg_class WHERE relname LIKE '%\\_new'") == 0


def test_lock_timeout_applied_by_env(throwaway_database_url, monkeypatch):
    """env.py pose lock_timeout : une migration bloquée derrière un verrou échoue vite."""
    url = throwaway_database_url
    command.upgrade(_cfg(), "0043")
    monkeypatch.setenv("CORE_MIGRATION_LOCK_TIMEOUT", "300ms")
    eng = sa.create_engine(url)
    holder = eng.connect()
    holder.execute(sa.text("LOCK TABLE pipeline_runs IN ACCESS EXCLUSIVE MODE"))
    try:
        with pytest.raises(sa.exc.DBAPIError, match="lock timeout"):
            command.downgrade(_cfg(), "0042")
    finally:
        holder.rollback()
        holder.close()
        eng.dispose()


def test_full_round_trip_on_populated_base(throwaway_database_url, monkeypatch):
    url = throwaway_database_url
    command.upgrade(_cfg(), "head")
    eng = sa.create_engine(url)
    with eng.begin() as conn:
        _seed_base(conn)
        conn.execute(
            sa.text("UPDATE roles SET slug = 'admin' WHERE id = 'r1'")
        )  # downgrade 0030 : slug connu
        conn.execute(
            sa.text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, keywords, "
                "created_at, updated_at) VALUES ('i1','t1','u1','map','M','[]',now(),now())"
            )
        )
    eng.dispose()

    monkeypatch.delenv(ALLOW, raising=False)
    with pytest.raises(RuntimeError, match="downgrade refusé"):
        command.downgrade(_cfg(), "base")
    assert _scalar(url, "SELECT count(*) FROM items") == 1

    monkeypatch.setenv(ALLOW, "1")
    command.downgrade(_cfg(), "base")
    command.upgrade(_cfg(), "head")
    assert _scalar(url, "SELECT count(*) FROM alembic_version") == 1

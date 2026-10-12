# SPDX-License-Identifier: Apache-2.0
"""Migration 0053 (ARC-06) : table api_keys.

Base jetable, upgrade puis downgrade sur base NON vide (piège n°8) : la ligne
tenants préexiste, la table est créée (puis remplie) puis supprimée sans toucher au reste."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

CORE_DIR = Path(__file__).resolve().parent.parent
TABLE = "api_keys"


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"apikeys_{uuid.uuid4().hex[:8]}"
    with admin.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", test_db_url)
    eng = sa.create_engine(url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        for ext in ("postgis", "vector", "pg_trgm"):
            conn.execute(sa.text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    eng.dispose()
    try:
        yield url
    finally:
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin.dispose()


@pytest.mark.postgis
def test_0053_table_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0051")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
        assert TABLE not in sa.inspect(engine).get_table_names()
        command.upgrade(cfg, "0053")
        insp = sa.inspect(engine)
        assert TABLE in insp.get_table_names()
        assert "ix_api_keys_tenant_created_by" in {i["name"] for i in insp.get_indexes(TABLE)}
        # le préfixe est unique (et seul le condensat est stocké : pas de colonne secret)
        assert "key_hash" in {c["name"] for c in insp.get_columns(TABLE)}
        assert "token" not in {c["name"] for c in insp.get_columns(TABLE)}
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) "
                    "VALUES ('r1', 't1', 'R', 'reader', true, '[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, oidc_sub, username, role_id, is_admin, "
                    "created_at, updated_at) "
                    "VALUES ('u1', 't1', 's', 'u', 'r1', false, now(), now())"
                )
            )
            ins = sa.text(
                "INSERT INTO api_keys (id, tenant_id, created_by, name, key_prefix, key_hash, "
                "expires_at, created_at) VALUES (:id, 't1', 'u1', 'k', :p, 'h', now(), now())"
            )
            conn.execute(ins, {"id": "k1", "p": "gsk_aaaaaaaaaaaa"})
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as conn:
            conn.execute(ins, {"id": "k2", "p": "gsk_aaaaaaaaaaaa"})
        command.upgrade(cfg, "head")  # rejouable
        command.downgrade(cfg, "0051")
        assert TABLE not in sa.inspect(engine).get_table_names()
        with engine.connect() as conn:  # la base préexistante est intacte
            assert conn.execute(sa.text("SELECT count(*) FROM users WHERE id = 'u1'")).scalar() == 1
        command.upgrade(cfg, "0053")
        assert TABLE in sa.inspect(engine).get_table_names()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

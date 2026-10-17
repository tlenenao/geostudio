# SPDX-License-Identifier: Apache-2.0
"""Migration 0083 (AUD-091) : api_keys.scopes/read_only, sur base NON vide, dans
les deux sens (piège n°8)."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"apikeyscopes_{uuid.uuid4().hex[:8]}"
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


def _columns(engine) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns("api_keys")}


@pytest.mark.postgis
def test_0083_columns_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0082")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            for stmt in (
                "INSERT INTO tenants (id, slug, name, created_at) VALUES ('t1', 't1', 'T', now())",
                "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                "created_at, updated_at) VALUES ('r1', 't1', 'Admin', 'admin', true, '[]', "
                "now(), now())",
                "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, last_name, "
                "is_admin, role_id, created_at, updated_at) "
                "VALUES ('u1', 't1', 's', 'alice', '', '', true, 'r1', now(), now())",
                "INSERT INTO api_keys (id, tenant_id, created_by, name, key_prefix, key_hash, "
                "expires_at, created_at) VALUES ('k1', 't1', 'u1', 'ci', 'gsk_000000000000', "
                "'h', now() + interval '1 day', now())",
            ):
                conn.execute(sa.text(stmt))
        assert not {"scopes", "read_only"} & _columns(engine)
        command.upgrade(cfg, "0083")
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT scopes, read_only FROM api_keys")).one()
        assert row == (None, False)  # clé existante : comportement historique
        command.downgrade(cfg, "-1")
        assert not {"scopes", "read_only"} & _columns(engine)
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM api_keys")).scalar() == 1
        command.upgrade(cfg, "0083")
        assert {"scopes", "read_only"} <= _columns(engine)
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

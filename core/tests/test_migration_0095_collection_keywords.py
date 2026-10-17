# SPDX-License-Identifier: Apache-2.0
"""Migration 0095 (AUD-047) : collections.keywords + inspire_theme, sur base NON vide, dans les
deux sens (piège n°8)."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"kw_{uuid.uuid4().hex[:8]}"
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
def test_0095_columns_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_rev = ScriptDirectory.from_config(cfg).get_revision("0095").down_revision
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, previous_rev)
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, slug, privileges, created_at, "
                    "updated_at) VALUES ('ro1', 't1', 'R', 'r', '[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, last_name, "
                    "is_admin, role_id, created_at, updated_at) "
                    "VALUES ('u1', 't1', 'u', 'u', '', '', false, 'ro1', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "pk_column, created_at, updated_at) "
                    "VALUES ('c1', 't1', 'u1', 'c1', 'C', 'id', now(), now())"
                )
            )
        cols = lambda: {c["name"] for c in sa.inspect(engine).get_columns("collections")}  # noqa: E731
        assert {"keywords", "inspire_theme"}.isdisjoint(cols())
        command.upgrade(cfg, "0095")
        with engine.connect() as conn:
            row = conn.execute(sa.text("SELECT keywords, inspire_theme FROM collections")).one()
        assert (row[0], row[1]) == ([], "")
        command.downgrade(cfg, previous_rev)
        assert {"keywords", "inspire_theme"}.isdisjoint(cols())
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM collections")).scalar() == 1
        command.upgrade(cfg, "0095")
        assert {"keywords", "inspire_theme"} <= cols()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

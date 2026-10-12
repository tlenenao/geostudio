# SPDX-License-Identifier: Apache-2.0
"""Migration 0055 (ARC-15) : table entity_history.

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
TABLE = "entity_history"


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"hist_{uuid.uuid4().hex[:8]}"
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
def test_0055_table_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0054")
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
            conn.execute(
                sa.text(
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "pk_column, created_at, updated_at) "
                    "VALUES ('c1', 't1', 'u1', 'c1', 'C', 'id', now(), now())"
                )
            )
        assert TABLE not in sa.inspect(engine).get_table_names()
        command.upgrade(cfg, "0055")
        insp = sa.inspect(engine)
        assert TABLE in insp.get_table_names()
        assert {"ix_entity_history_entity", "ix_entity_history_tenant_at"} <= {
            i["name"] for i in insp.get_indexes(TABLE)
        }
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO entity_history (tenant_id, collection_id, fid, op, before, "
                    "after, actor_id, created_at) VALUES ('t1', 'c1', '1', 'create', NULL, "
                    "'{}', 'u1', now())"
                )
            )
        # ON DELETE CASCADE : supprimer la collection emporte son journal
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM collections WHERE id = 'c1'"))
            assert conn.execute(sa.text("SELECT count(*) FROM entity_history")).scalar() == 0
        command.upgrade(cfg, "head")  # rejouable
        command.downgrade(cfg, "0054")
        assert TABLE not in sa.inspect(engine).get_table_names()
        with engine.connect() as conn:  # la base préexistante est intacte
            assert conn.execute(sa.text("SELECT count(*) FROM users WHERE id = 'u1'")).scalar() == 1
        command.upgrade(cfg, "0055")
        assert TABLE in sa.inspect(engine).get_table_names()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

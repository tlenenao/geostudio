# SPDX-License-Identifier: Apache-2.0
"""Migration 0060 (ARC-21) : table collection_relations.

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
TABLE = "collection_relations"


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"rel_{uuid.uuid4().hex[:8]}"
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
def test_0060_table_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0059")
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
        command.upgrade(cfg, "0060")
        insp = sa.inspect(engine)
        assert TABLE in insp.get_table_names()
        assert {
            "ix_collection_relations_tenant",
            "ix_collection_relations_parent",
            "ix_collection_relations_child",
            "ix_collection_relations_link",
        } <= {i["name"] for i in insp.get_indexes(TABLE)}
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO collection_relations (id, tenant_id, name, cardinality, "
                    "parent_collection_id, child_collection_id, parent_key, child_key, "
                    "on_delete, created_at) VALUES ('r1', 't1', 'n', 'one_to_many', 'c1', "
                    "'c1', 'id', 'fk', 'restrict', now())"
                )
            )
        # ON DELETE CASCADE : supprimer la collection emporte ses relations
        with engine.begin() as conn:
            conn.execute(sa.text("DELETE FROM collections WHERE id = 'c1'"))
            assert conn.execute(sa.text("SELECT count(*) FROM collection_relations")).scalar() == 0
        command.upgrade(cfg, "head")  # rejouable
        command.downgrade(cfg, "0059")
        assert TABLE not in sa.inspect(engine).get_table_names()
        with engine.connect() as conn:  # la base préexistante est intacte
            assert conn.execute(sa.text("SELECT count(*) FROM users WHERE id = 'u1'")).scalar() == 1
        command.upgrade(cfg, "0060")
        assert TABLE in sa.inspect(engine).get_table_names()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

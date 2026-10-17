# SPDX-License-Identifier: Apache-2.0
"""Migration 0088 (AUD-087) : pipeline_runs.failed_node_id, sur base NON vide, dans les deux sens
(piège n°8)."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

CORE_DIR = Path(__file__).resolve().parent.parent
TABLE = "pipeline_runs"


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"failednode_{uuid.uuid4().hex[:8]}"
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
def test_0088_column_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0087")
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
                    "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, abstract, "
                    "is_published, is_public, keywords, created_at, updated_at) "
                    "VALUES ('i1', 't1', 'u1', 'pipeline', 'P', '', false, false, '[]', "
                    "now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO pipeline_runs (id, tenant_id, pipeline_item_id, status, "
                    "created_at) VALUES ('r1', 't1', 'i1', 'running', now())"
                )
            )
        cols = lambda: {c["name"] for c in sa.inspect(engine).get_columns(TABLE)}  # noqa: E731
        assert "failed_node_id" not in cols()
        command.upgrade(cfg, "0088")
        assert "failed_node_id" in cols()
        with engine.connect() as conn:  # lignes existantes : NULL
            row = conn.execute(sa.text("SELECT failed_node_id FROM pipeline_runs")).scalar()
            assert row is None
        command.downgrade(cfg, "-1")
        assert "failed_node_id" not in cols()
        with engine.connect() as conn:
            assert conn.execute(sa.text("SELECT count(*) FROM pipeline_runs")).scalar() == 1
        command.upgrade(cfg, "0088")
        assert "failed_node_id" in cols()
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

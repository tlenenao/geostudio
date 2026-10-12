# SPDX-License-Identifier: Apache-2.0
"""Migration 0061 (ARC-24) : group_members.origin + group_claim_mappings,
base non vide, deux sens (piège n°8)."""

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
    db_name = f"gcm_{uuid.uuid4().hex[:8]}"
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
def test_0061_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0059")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(sa.text("SET session_replication_role = replica"))  # FK hors sujet
            conn.execute(
                sa.text(
                    "INSERT INTO group_members (group_id, user_id, tenant_id) "
                    "VALUES ('g1', 'u1', 't1')"
                )
            )
        command.upgrade(cfg, "0061")
        with engine.begin() as conn:
            conn.execute(sa.text("SET session_replication_role = replica"))
            origin = conn.execute(sa.text("SELECT origin FROM group_members")).scalar()
            assert origin == "manual"  # l'existant est humain, jamais retiré
            conn.execute(
                sa.text(
                    "INSERT INTO group_claim_mappings "
                    "(id, tenant_id, group_id, claim_value, created_by, created_at) "
                    "VALUES ('m', 't1', 'g1', 'SIG', 'u1', now())"
                )
            )
        command.downgrade(cfg, "0059")
        with engine.connect() as conn:
            insp = sa.inspect(conn)
            assert "origin" not in {c["name"] for c in insp.get_columns("group_members")}
            assert "group_claim_mappings" not in insp.get_table_names()
            assert conn.execute(sa.text("SELECT count(*) FROM group_members")).scalar() == 1
        command.upgrade(cfg, "0061")
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

# SPDX-License-Identifier: Apache-2.0
"""Migration 0049 (REV-279 c, trouvé au rejeu) : index sur group_members(user_id).

La PK est (group_id, user_id) : `WHERE user_id = ?` (can(), catalogue) faisait
un Seq Scan. Base jetable, upgrade puis downgrade sur base non vide (piège n°8).
"""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.sharing.models import GroupMember

CORE_DIR = Path(__file__).resolve().parent.parent
NAME = "ix_group_members_user_id"


def test_model_declares_the_index():
    assert NAME in {i.name for i in GroupMember.__table__.indexes}


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"gm_idx_{uuid.uuid4().hex[:8]}"
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


def _valid(conn):
    return conn.execute(
        sa.text(
            "SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = :n"
        ),
        {"n": NAME},
    ).scalar()


@pytest.mark.postgis
def test_0049_index_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0048")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
        with engine.connect() as conn:
            assert _valid(conn) is None
        command.upgrade(cfg, "0049")
        with engine.connect() as conn:
            assert _valid(conn) is True
        command.upgrade(cfg, "head")  # rejouable
        command.downgrade(cfg, "0048")
        with engine.connect() as conn:
            assert _valid(conn) is None
        command.upgrade(cfg, "0049")
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

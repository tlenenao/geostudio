# SPDX-License-Identifier: Apache-2.0
"""Migration 0051 (REV-121/GAP-27) : table collection_geo_limits.

Base jetable, upgrade puis downgrade sur base NON vide (piège n°8) : la ligne
tenants préexiste, la table est créée puis supprimée sans toucher au reste."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.sharing.models import CollectionGeoLimit

CORE_DIR = Path(__file__).resolve().parent.parent
TABLE = "collection_geo_limits"


def test_model_declares_table_and_unique_target():
    t = CollectionGeoLimit.__table__
    assert t.name == TABLE
    assert "tenant_id" in t.c
    assert any(
        {c.name for c in u.columns} == {"collection_id", "target_type", "target_id"}
        for u in t.constraints
        if isinstance(u, sa.UniqueConstraint)
    )


@pytest.fixture()
def throwaway_database_url(test_db_url):
    admin = sa.create_engine(test_db_url, isolation_level="AUTOCOMMIT")
    db_name = f"geolim_{uuid.uuid4().hex[:8]}"
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
def test_0051_table_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0050")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'T', now())"
                )
            )
        assert TABLE not in sa.inspect(engine).get_table_names()
        command.upgrade(cfg, "0051")
        insp = sa.inspect(engine)
        assert TABLE in insp.get_table_names()
        assert "ix_geo_limits_tenant_collection" in {i["name"] for i in insp.get_indexes(TABLE)}
        command.upgrade(cfg, "head")  # rejouable
        command.downgrade(cfg, "0050")
        assert TABLE not in sa.inspect(engine).get_table_names()
        with engine.connect() as conn:  # la base préexistante est intacte
            assert (
                conn.execute(sa.text("SELECT count(*) FROM tenants WHERE id = 't1'")).scalar() == 1
            )
        command.upgrade(cfg, "0051")
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

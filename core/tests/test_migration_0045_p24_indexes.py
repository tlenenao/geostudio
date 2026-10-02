# SPDX-License-Identifier: Apache-2.0
"""Migration 0045 (P24.01-04) : index CONCURRENTLY sur base NON vide, upgrade
puis downgrade (piège n°8). Base jetable, jamais postgis-test partagé."""

import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

pytestmark = pytest.mark.postgis

CORE_DIR = Path(__file__).resolve().parent.parent
NAMES = {
    "ix_audit_log_tenant_created",
    "ix_audit_log_tenant_actor_created",
    "ix_configs_item_id",
    "ix_configs_kind_tenant_id",
    "ix_config_revisions_config_version",
    "ix_report_runs_report",
}


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"p24_idx_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    throwaway_url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", base_url)
    throwaway_engine = sa.create_engine(throwaway_url, isolation_level="AUTOCOMMIT")
    with throwaway_engine.connect() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    throwaway_engine.dispose()
    try:
        yield throwaway_url
    finally:
        with admin_engine.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": db_name},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def _present(conn):
    rows = conn.execute(
        sa.text(
            "SELECT c.relname, i.indisvalid FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = ANY(:n)"
        ),
        {"n": list(NAMES)},
    ).all()
    return {r[0]: r[1] for r in rows}


def test_0045_indexes_on_non_empty_base_both_ways(throwaway_database_url):
    cfg = Config()
    cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(cfg, "0044")
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
                    "INSERT INTO audit_log (tenant_id, actor_id, actor_kind, action, "
                    "object_type, object_id, payload, created_at) "
                    "VALUES ('t1', 'u', 'user', 'a', 'item', 'i', '{}', now())"
                )
            )
        with engine.connect() as conn:
            assert _present(conn) == {}

        command.upgrade(cfg, "0045")
        with engine.connect() as conn:
            assert _present(conn) == {n: True for n in NAMES}  # tous valides
            conn.execute(sa.text("SET enable_seqscan = off"))
            plan = " ".join(
                r[0]
                for r in conn.execute(
                    sa.text(
                        "EXPLAIN SELECT * FROM audit_log WHERE tenant_id='t1' "
                        "AND created_at >= now() - interval '1 day'"
                    )
                )
            )
            assert "Index Scan" in plan and "ix_audit_log_tenant" in plan
        command.upgrade(cfg, "head")  # rejouable

        command.downgrade(cfg, "0044")
        with engine.connect() as conn:
            assert _present(conn) == {}
            assert conn.execute(sa.text("SELECT count(*) FROM audit_log")).scalar() == 1
        command.upgrade(cfg, "0045")
        with engine.connect() as conn:
            assert set(_present(conn)) == NAMES
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous

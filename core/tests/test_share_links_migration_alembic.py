# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration Alembic 0035 (upgrade/downgrade/upgrade) sur
une base Postgres non vide — piège n°8 (CLAUDE.md). Patron identique à
test_attachments_migration_alembic.py (0032) : base jetable, créée et
détruite par ce test, jamais le schéma partagé `postgis-test`."""

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


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"sp54_migration_{uuid.uuid4().hex[:8]}"
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


def test_share_link_migration_upgrade_downgrade_upgrade_on_non_empty_db(
    throwaway_database_url,
):
    # Config() SANS chemin de fichier ini — même raison que
    # test_attachments_migration_alembic.py (fileConfig désactiverait des
    # loggers d'autres modules utilisés par des tests caplog plus loin dans
    # la même session pytest).
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        # 0034 : juste avant 0035, pour insérer tenant/user/item RÉELS avant
        # que la migration testée ne s'applique — preuve que create_table
        # fonctionne sur une base déjà peuplée (pas seulement une base
        # fraîche), et que les FK vers tenants/items/users résolvent bien.
        command.upgrade(alembic_cfg, "0034")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "INSERT INTO tenants (id, slug, name, created_at) "
                    "VALUES ('t1', 't1', 'Tenant', now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO roles (id, tenant_id, name, slug, is_built_in, privileges, "
                    "created_at, updated_at) "
                    "VALUES ('r1', 't1', 'Admin', 'admin', true, '[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, tenant_id, oidc_sub, username, first_name, "
                    "last_name, is_admin, role_id, created_at, updated_at) "
                    "VALUES ('u1', 't1', 'sub1', 'alice', '', '', true, 'r1', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, "
                    "abstract, keywords, is_published, created_at, updated_at) "
                    "VALUES ('it1', 't1', 'u1', 'app', 'Item 1', '', '[]', false, now(), now())"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            assert "share_link" in tables
            conn.execute(
                sa.text(
                    "INSERT INTO share_link (id, tenant_id, item_id, created_by, "
                    "expires_at, created_at) "
                    "VALUES ('sl1', 't1', 'it1', 'u1', now() + interval '7 days', now())"
                )
            )
            value = conn.execute(
                sa.text("SELECT revoked_at FROM share_link WHERE id = 'sl1'")
            ).scalar()
            assert value is None
        engine.dispose()

        command.downgrade(alembic_cfg, "0034")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            assert "share_link" not in tables
        engine.dispose()

        # Rejoue upgrade une seconde fois — la migration doit être
        # idempotente dans les deux sens, pas seulement la première fois.
        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            assert "share_link" in tables
        engine.dispose()
    finally:
        if previous_database_url is not None:
            os.environ["DATABASE_URL"] = previous_database_url
        else:
            os.environ.pop("DATABASE_URL", None)

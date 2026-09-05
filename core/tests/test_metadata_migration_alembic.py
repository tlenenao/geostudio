# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration Alembic 0033 (upgrade/downgrade/upgrade) sur
une base Postgres non vide — piège n°8 (CLAUDE.md). Patron identique à
test_attachments_migration_alembic.py (SP-40) : base jetable créée et
détruite par ce test, jamais le schéma partagé postgis-test."""

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
    db_name = f"sp41_migration_{uuid.uuid4().hex[:8]}"
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


def test_migration_0033_upgrades_and_downgrades_on_a_real_non_empty_base(
    throwaway_database_url,
):
    # Config() SANS chemin de fichier ini : cf. test_attachments_migration_alembic.py
    # (SP-40) pour l'explication complète (fileConfig désactiverait les
    # loggers d'autres modules cœur pour toute la session pytest).
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        # 0032 : juste avant 0033, pour insérer des lignes collections/items
        # RÉELLES avant que la migration testée ne s'applique.
        command.upgrade(alembic_cfg, "0032")
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
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "description, pk_column, is_public, editable, attachment_fields, "
                    "created_at, updated_at) "
                    "VALUES ('col1', 't1', 'u1', 'col1', 'Col 1', '', 'id', false, true, "
                    "'[]', now(), now())"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, "
                    "abstract, keywords, is_published, is_public, created_at, updated_at) "
                    "VALUES ('item1', 't1', 'u1', 'map', 'Item 1', '', '[]', false, false, "
                    "now(), now())"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            for name in (
                "license",
                "license_uri",
                "producer",
                "contact",
                "update_frequency",
                "lineage",
                "language",
                "version",
                "temporal_start",
                "temporal_end",
            ):
                assert name in col_columns
            item_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'items'"
                    )
                )
            }
            assert "license" in item_columns
            assert "language" in item_columns
            # La ligne insérée AVANT 0033 a bien été backfillée par les
            # server_default de la migration, pas laissée NULL/en échec.
            col_row = conn.execute(
                sa.text(
                    "SELECT license, language, temporal_start FROM collections WHERE id = 'col1'"
                )
            ).one()
            assert col_row == ("", "fr", None)
            item_row = conn.execute(
                sa.text("SELECT license, language FROM items WHERE id = 'item1'")
            ).one()
            assert item_row == ("", "fr")
        engine.dispose()

        command.downgrade(alembic_cfg, "0032")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            assert "license" not in col_columns
            assert "temporal_start" not in col_columns
            item_columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'items'"
                    )
                )
            }
            assert "license" not in item_columns
            # Les lignes survivent au downgrade (seules les colonnes ajoutées
            # par 0033 sont retirées).
            assert (
                conn.execute(sa.text("SELECT 1 FROM collections WHERE id = 'col1'")).scalar() == 1
            )
            assert conn.execute(sa.text("SELECT 1 FROM items WHERE id = 'item1'")).scalar() == 1
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            col_row = conn.execute(
                sa.text("SELECT license, language FROM collections WHERE id = 'col1'")
            ).one()
            assert col_row == ("", "fr")
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

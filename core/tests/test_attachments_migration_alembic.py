# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration Alembic 0032 (upgrade/downgrade/upgrade) sur
une base Postgres non vide — piège n°8 (CLAUDE.md) : le test existant
`test_attachments_migration.py` ne couvre que `Base.metadata.create_all()`,
jamais le chemin réel de production (`alembic upgrade`), et jamais une base
non vide (revue finale de branche, I7).

Base jetable, créée et détruite par ce test — JAMAIS le schéma partagé
`postgis-test` (un `downgrade` y serait destructif pour les autres tests
postgis concurrents, cf. le conteneur non tracké par Alembic documenté dans
CLAUDE.md/SP-39)."""

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
    db_name = f"sp40_migration_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f'CREATE DATABASE "{db_name}"'))
    throwaway_url = re.sub(r"/[^/?]+(\?.*)?$", rf"/{db_name}\1", base_url)
    # Les migrations réelles (0028 notamment, backfill géométrie) lisent
    # geometry_columns/pg_trgm : une base fraîchement créée n'a aucune
    # extension activée, contrairement à gis_test — les répliquer ici.
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


def test_migration_0032_upgrades_and_downgrades_on_a_real_non_empty_base(
    throwaway_database_url,
):
    # Config() SANS chemin de fichier ini, plutôt que Config("alembic.ini") :
    # alembic/env.py fait fileConfig(config.config_file_name) dès que
    # config_file_name est renseigné — logging.config.fileConfig désactive
    # par défaut (disable_existing_loggers=True) TOUS les loggers du process
    # non listés dans alembic.ini, y compris ceux d'autres modules cœur
    # utilisés par des tests caplog sans rapport plus loin dans la même
    # session pytest. Falsifié : avec Config("alembic.ini"), la suite
    # complète perd 3 tests caplog (test_ogc_discovery.py,
    # test_repository.py) ; sans fichier ini, script_location posé à la
    # main suffit et aucun logger n'est jamais touché.
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        # 0031 : juste avant 0032, pour insérer une ligne `collections`
        # RÉELLE avant que la migration testée ne s'applique — preuve que
        # l'ALTER TABLE ADD COLUMN backfille correctement une ligne déjà
        # existante (server_default='[]'), pas seulement une base fraîche.
        command.upgrade(alembic_cfg, "0031")
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
                    "description, pk_column, is_public, editable, created_at, updated_at) "
                    "VALUES ('col1', 't1', 'u1', 'col1', 'Col 1', '', 'id', false, true, "
                    "now(), now())"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            assert "attachment_fields" in columns
            # La ligne insérée AVANT 0032 a bien été backfillée par le
            # server_default de la migration, pas laissée NULL/en échec.
            value = conn.execute(
                sa.text("SELECT attachment_fields FROM collections WHERE id = 'col1'")
            ).scalar()
            assert value == []
            tables = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            assert "attachments" in tables
        engine.dispose()

        command.downgrade(alembic_cfg, "-1")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            columns = {
                row[0]
                for row in conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
            }
            assert "attachment_fields" not in columns
            tables = {
                row[0]
                for row in conn.execute(
                    sa.text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
                )
            }
            assert "attachments" not in tables
            # La ligne `collections` insérée avant 0032 survit au downgrade
            # (seule la colonne ajoutée par 0032 est retirée).
            still_there = conn.execute(
                sa.text("SELECT 1 FROM collections WHERE id = 'col1'")
            ).scalar()
            assert still_there == 1
        engine.dispose()

        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            value = conn.execute(
                sa.text("SELECT attachment_fields FROM collections WHERE id = 'col1'")
            ).scalar()
            assert value == []
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration Alembic 0042 (upgrade/downgrade/upgrade) sur
une base Postgres non vide — piège n°8 (CLAUDE.md). Patron identique à
test_attachments_migration_alembic.py (0032)/test_share_links_migration_
alembic.py (0040) : base jetable, créée et détruite par ce test, jamais le
schéma partagé `postgis-test`.

Vérifie en plus le point le plus critique du chantier GAP-22 (masquage par
colonne) : le rôle `gis_rls_masked` ne reçoit JAMAIS de GRANT SELECT au
niveau table — uniquement des GRANT SELECT (col) colonne par colonne, y
compris via le backfill qui doit s'appliquer à une collection déjà
enregistrée AVEC des lignes réelles avant l'upgrade."""

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
    db_name = f"gap22_migration_{uuid.uuid4().hex[:8]}"
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


def test_0042_upgrade_downgrade_upgrade_on_non_empty_db_column_level_only(
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
        # 0041 : juste avant 0042, pour enregistrer une collection RÉELLE
        # (avec sa table physique et des lignes) avant que la migration
        # testée ne s'applique — preuve que le backfill grante bien les
        # colonnes réelles d'une collection déjà enregistrée, pas seulement
        # une base fraîche.
        command.upgrade(alembic_cfg, "0041")
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
            # Table physique réelle derrière la collection, avec des lignes
            # AVANT l'upgrade testé.
            conn.execute(
                sa.text(
                    "CREATE TABLE villes_gap22 "
                    "(id serial PRIMARY KEY, tenant_id text NOT NULL DEFAULT 't1', "
                    "name text, population integer)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO villes_gap22 (tenant_id, name, population) "
                    "VALUES ('t1', 'Paris', 2100000), ('t1', 'Lyon', 500000)"
                )
            )
            conn.execute(
                sa.text(
                    "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                    "description, pk_column, is_public, editable, created_at, updated_at) "
                    "VALUES ('col1', 't1', 'u1', 'villes_gap22', 'Villes', '', 'id', false, "
                    "true, now(), now())"
                )
            )
        engine.dispose()

        command.upgrade(alembic_cfg, "0042")
        engine = sa.create_engine(throwaway_database_url)
        with engine.connect() as conn:
            columns = set(
                conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
                .scalars()
                .all()
            )
            assert "sensitive_fields" in columns
            # Backfill : la ligne insérée avant 0042 a bien sensitive_fields=[]
            # (server_default), pas NULL/échec.
            value = conn.execute(
                sa.text("SELECT sensitive_fields FROM collections WHERE id = 'col1'")
            ).scalar()
            assert value == []

            role_exists = conn.execute(
                sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'gis_rls_masked'")
            ).scalar()
            assert role_exists == 1

            # --- Le point le plus critique du chantier : AUCUN GRANT SELECT
            # au niveau table pour gis_rls_masked, jamais.
            table_level_grants = conn.execute(
                sa.text(
                    "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                    "WHERE grantee = 'gis_rls_masked'"
                )
            ).all()
            assert table_level_grants == [], (
                "gis_rls_masked a reçu un GRANT au niveau table — interdit "
                f"par GAP-22, trouvé : {table_level_grants}"
            )

            # Le backfill a bien grante colonne par colonne TOUTES les
            # colonnes réelles de la table physique de la collection
            # préexistante (sensitive_fields=[] => aucune colonne masquée).
            granted_columns = set(
                conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.column_privileges "
                        "WHERE grantee = 'gis_rls_masked' AND table_name = 'villes_gap22' "
                        "AND privilege_type = 'SELECT'"
                    )
                )
                .scalars()
                .all()
            )
            real_columns = set(
                conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'villes_gap22'"
                    )
                )
                .scalars()
                .all()
            )
            assert real_columns == {"id", "tenant_id", "name", "population"}
            assert granted_columns == real_columns

            # Le rôle voit effectivement les données via ces GRANTs
            # colonne-par-colonne (SET ROLE, pas SET LOCAL ROLE : la
            # connexion se referme à la fin du `with`).
            conn.execute(sa.text("SET ROLE gis_rls_masked"))
            rows = conn.execute(
                sa.text("SELECT name, population FROM villes_gap22 ORDER BY name")
            ).all()
            assert rows == [("Lyon", 500000), ("Paris", 2100000)]
            conn.execute(sa.text("RESET ROLE"))
        engine.dispose()

        command.downgrade(alembic_cfg, "0041")
        engine = sa.create_engine(throwaway_database_url)
        with engine.connect() as conn:
            columns = set(
                conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'collections'"
                    )
                )
                .scalars()
                .all()
            )
            assert "sensitive_fields" not in columns
            role_exists = conn.execute(
                sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'gis_rls_masked'")
            ).scalar()
            assert role_exists is None
            # La ligne `collections`/la table physique insérées avant 0042
            # survivent au downgrade (seuls la colonne et le rôle ajoutés
            # par 0042 sont retirés).
            still_there = conn.execute(
                sa.text("SELECT 1 FROM collections WHERE id = 'col1'")
            ).scalar()
            assert still_there == 1
        engine.dispose()

        # Rejoue upgrade une seconde fois — idempotent dans les deux sens :
        # CREATE ROLE IF NOT EXISTS + re-backfill sans erreur.
        command.upgrade(alembic_cfg, "0042")
        engine = sa.create_engine(throwaway_database_url)
        with engine.connect() as conn:
            role_exists = conn.execute(
                sa.text("SELECT 1 FROM pg_roles WHERE rolname = 'gis_rls_masked'")
            ).scalar()
            assert role_exists == 1
            table_level_grants = conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.role_table_grants "
                    "WHERE grantee = 'gis_rls_masked'"
                )
            ).all()
            assert table_level_grants == []
            granted_columns = set(
                conn.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.column_privileges "
                        "WHERE grantee = 'gis_rls_masked' AND table_name = 'villes_gap22' "
                        "AND privilege_type = 'SELECT'"
                    )
                )
                .scalars()
                .all()
            )
            assert granted_columns == {"id", "tenant_id", "name", "population"}
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

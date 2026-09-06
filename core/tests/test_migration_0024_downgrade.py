# SPDX-License-Identifier: Apache-2.0
"""Teste réellement `downgrade()` de la migration 0024 sur une base Postgres
non vide (GAP-63.1, SP-49) — piège CLAUDE.md n°8 : `upgrade()` relâche
`report_runs.export_job_id` en nullable pour permettre qu'un déclenchement de
rapport en échec crée quand même une ligne (cf. commentaire de la migration
et `app/reports/models.py`) ; une telle ligne est une situation normale de
fonctionnement, pas un cas limite artificiel. Avant correction,
`downgrade()` retendait la contrainte NOT NULL et levait `NotNullViolation`
dès qu'une seule ligne de ce type existait.

Base jetable, créée et détruite par ce test — jamais le schéma partagé
`postgis-test` (cf. test_attachments_migration_alembic.py, même patron)."""

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
    db_name = f"sp49_migration_{uuid.uuid4().hex[:8]}"
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


def test_downgrade_0024_succeeds_with_existing_null_export_job_id(
    throwaway_database_url,
):
    # Config() SANS chemin de fichier ini — cf. test_attachments_migration_alembic.py :
    # Config("alembic.ini") désactive silencieusement des loggers d'autres
    # modules via fileConfig(disable_existing_loggers=True).
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    # core/alembic/env.py lit inconditionnellement DATABASE_URL, jamais
    # l'option sqlalchemy.url de Config.
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(alembic_cfg, "head")

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
                    "keywords, created_at, updated_at) "
                    "VALUES ('i1', 't1', 'u1', 'report', 'Rapport 1', '[]', now(), now())"
                )
            )
            # Situation normale de fonctionnement (pas un cas artificiel) :
            # un déclenchement de rapport en échec crée une ligne report_runs
            # SANS export_job_id — propriétaire ayant perdu l'accès, capacité
            # export coupée, etc. Cf. commentaire de app/reports/models.py.
            conn.execute(
                sa.text(
                    "INSERT INTO report_runs (id, tenant_id, report_item_id, export_job_id, "
                    "created_at) "
                    "VALUES ('rr1', 't1', 'i1', NULL, now())"
                )
            )
        engine.dispose()

        # Avant la correction de la migration 0024, cette ligne échoue en
        # NotNullViolation (l'ALTER TABLE ... SET NOT NULL rejette la ligne
        # NULL insérée ci-dessus). Après correction, downgrade() jusqu'à
        # 0023 est un no-op documenté pour cette colonne : il réussit
        # inconditionnellement, y compris sur cette base non vide.
        command.downgrade(alembic_cfg, "0023")

        engine = sa.create_engine(throwaway_database_url)
        with engine.begin() as conn:
            # La ligne report_runs.export_job_id NULL survit intacte au
            # downgrade — aucune donnée perdue ni altérée.
            value = conn.execute(
                sa.text("SELECT export_job_id FROM report_runs WHERE id = 'rr1'")
            ).scalar()
            assert value is None
        engine.dispose()

        # Ré-upgrade : le no-op ne casse pas non plus le chemin retour.
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

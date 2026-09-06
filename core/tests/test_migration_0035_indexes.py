# SPDX-License-Identifier: Apache-2.0
"""Teste réellement la migration 0035 (index manquants sur
alert_evaluations/pipeline_runs, GAP-63.2, SP-49) sur une base Postgres non
vide, dans les deux sens (piège CLAUDE.md n°8) : upgrade jusqu'à head,
insertion de plusieurs lignes pour un même (tenant_id, item_id) avec des
created_at différents (même jeu de données que celui utilisé pour falsifier
le batching de la Tâche 3), downgrade jusqu'à 0034 (les deux
`op.drop_index` doivent réussir sans erreur — contrairement au downgrade de
la migration 0024, celui-ci ne retend aucune contrainte), puis ré-upgrade et
vérification que les deux index existent de nouveau.

Base jetable, créée et détruite par ce test — jamais le schéma partagé
`postgis-test` (même patron que test_migration_0024_downgrade.py /
test_attachments_migration_alembic.py)."""

import os
import re
import uuid
from datetime import UTC, datetime, timedelta
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
    db_name = f"sp49_idx_{uuid.uuid4().hex[:8]}"
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


def test_migration_0035_creates_and_drops_indexes_on_a_real_non_empty_base(
    throwaway_database_url,
):
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        command.upgrade(alembic_cfg, "head")

        engine = sa.create_engine(throwaway_database_url)
        now = datetime.now(UTC)
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
                    "VALUES ('pipe1', 't1', 'u1', 'pipeline', 'Pipeline 1', '[]', now(), now()), "
                    "('rule1', 't1', 'u1', 'alertRule', 'Alerte 1', '[]', now(), now())"
                )
            )
            # Plusieurs lignes pour le même item, created_at PAS dans l'ordre
            # d'insertion (falsifie un tri/ordre mal géré — même jeu de
            # données que la Tâche 3, réutilisé ici pour vérifier que
            # l'index existe et que les requêtes fonctionnent toujours
            # après upgrade/downgrade/upgrade).
            for i, delta in enumerate([30, 10, 20]):
                created_at = now - timedelta(minutes=delta)
                conn.execute(
                    sa.text(
                        "INSERT INTO pipeline_runs (id, tenant_id, pipeline_item_id, status, "
                        "created_at) VALUES (:id, 't1', 'pipe1', 'success', :created_at)"
                    ),
                    {"id": f"run{i}", "created_at": created_at},
                )
                conn.execute(
                    sa.text(
                        "INSERT INTO alert_evaluations (id, tenant_id, alert_rule_item_id, "
                        "state, created_at) VALUES (:id, 't1', 'rule1', 'ok', :created_at)"
                    ),
                    {"id": f"eval{i}", "created_at": created_at},
                )
        engine.dispose()

        engine = sa.create_engine(throwaway_database_url)
        inspector = sa.inspect(engine)
        pipeline_indexes = {ix["name"]: ix for ix in inspector.get_indexes("pipeline_runs")}
        alert_indexes = {ix["name"]: ix for ix in inspector.get_indexes("alert_evaluations")}
        # <item>_id EN TÊTE (pas tenant_id) : corrigé en revue finale de
        # branche — cf. docstring de la migration 0035 pour la mesure
        # EXPLAIN qui motive cet ordre (get_latest_runs_for_items/
        # get_latest_evaluations_for_items, Tâche 3, filtrent SANS
        # tenant_id).
        assert pipeline_indexes["ix_pipeline_runs_pipeline"]["column_names"] == [
            "pipeline_item_id",
            "tenant_id",
            "created_at",
        ]
        assert alert_indexes["ix_alert_evaluations_rule"]["column_names"] == [
            "alert_rule_item_id",
            "tenant_id",
            "created_at",
        ]
        engine.dispose()

        # downgrade : les deux op.drop_index doivent réussir sans erreur —
        # contrairement à la migration 0024, aucune contrainte n'est
        # retendue ici, donc pas d'asymétrie possible.
        command.downgrade(alembic_cfg, "0034")

        engine = sa.create_engine(throwaway_database_url)
        inspector = sa.inspect(engine)
        pipeline_index_names = {ix["name"] for ix in inspector.get_indexes("pipeline_runs")}
        alert_index_names = {ix["name"] for ix in inspector.get_indexes("alert_evaluations")}
        assert "ix_pipeline_runs_pipeline" not in pipeline_index_names
        assert "ix_alert_evaluations_rule" not in alert_index_names
        # Les données survivent intactes à la suppression des index.
        with engine.begin() as conn:
            count = conn.execute(
                sa.text("SELECT count(*) FROM pipeline_runs WHERE pipeline_item_id = 'pipe1'")
            ).scalar()
            assert count == 3
        engine.dispose()

        # ré-upgrade : les deux index existent de nouveau.
        command.upgrade(alembic_cfg, "head")
        engine = sa.create_engine(throwaway_database_url)
        inspector = sa.inspect(engine)
        pipeline_index_names = {ix["name"] for ix in inspector.get_indexes("pipeline_runs")}
        alert_index_names = {ix["name"] for ix in inspector.get_indexes("alert_evaluations")}
        assert "ix_pipeline_runs_pipeline" in pipeline_index_names
        assert "ix_alert_evaluations_rule" in alert_index_names
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

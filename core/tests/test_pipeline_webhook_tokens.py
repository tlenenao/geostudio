# SPDX-License-Identifier: Apache-2.0
"""Service de déclenchement de pipeline par webhook entrant (GAP-24,
SP-53). Teste `create_webhook_token_service`/`revoke_webhook_token_service`/
`trigger_pipeline_by_webhook_service` directement (sans passer par HTTP,
comme le fait déjà tests/test_pipeline_routes.py pour la séquence
run_pipeline_service — les tests HTTP des 4 routes REST elles-mêmes vivent
dans tests/test_pipeline_routes.py, étendu par cette même tâche).

Base sqlite en mémoire (Base.metadata.create_all() via init_db(), pas
Alembic) : suffisant pour exercer modèle/repository/service — la parité
modèle<->migration elle-même reste couverte par le test global
tests/test_model_alembic_parity.py (déjà existant, SP-43), qui itère sur
TOUT Base.metadata — pas dupliquée ici par une 2e base jetable Postgres
dédiée à cette seule table (piège CLAUDE.md n°3 : le texte littéral du plan
suggérait une fixture `throwaway_database_url` par table, plus lourde que
nécessaire et redondante avec le test global)."""

import hashlib
import os
import re
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from fastapi import HTTPException

from alembic import command
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.pipelines.service import (
    create_webhook_token_service,
    revoke_webhook_token_service,
    trigger_pipeline_by_webhook_service,
)
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def db():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed(Session):
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="owner-sub",
            username="owner",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="pipeline",
            title="Pipeline",
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "r1",
                                "kind": "reader",
                                "op": "reader.collection",
                                "params": {"collectionId": "x"},
                            },
                            {
                                "id": "w1",
                                "kind": "writer",
                                "op": "writer.export",
                                "params": {"format": "csv", "key": "o.csv"},
                            },
                        ],
                        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                    },
                }
            ),
            item_id=item.id,
            tenant_id=tenant.id,
        )
        s.commit()
        return tenant.id, owner.id, item.id


def _noop_defer(run_id: str, tenant_id: str) -> None:
    pass


def test_create_webhook_token_returns_cleartext_once_and_persists_only_hash(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)

    assert token_row.token_hash != raw_token
    assert hashlib.sha256(raw_token.encode()).hexdigest() == token_row.token_hash
    with db() as s:
        persisted = pipelines_repo.get_webhook_token(s, tenant_id=tenant_id, token_id=token_row.id)
        assert persisted is not None
        assert persisted.token_hash == token_row.token_hash


def test_create_webhook_token_requires_automation_secrets_manage_privilege(db):
    # SP-47 (déjà fusionné sur dev) a donné automation.secrets.manage au rôle
    # Creator — reader (zéro privilège) est désormais le témoin correct pour
    # « ne porte pas ce privilège », même patron que test_roles_guards.py et
    # test_secrets_routes.py après ce même correctif SP-47.
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant_id)
        set_user_role(
            s,
            tenant_id=tenant_id,
            user_id=owner_id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        s.commit()

    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        with pytest.raises(HTTPException) as excinfo:
            create_webhook_token_service(s, user=owner, item_id=item_id)
        assert excinfo.value.status_code == 403


def test_trigger_by_webhook_calls_run_pipeline_service_not_a_parallel_path(db, monkeypatch):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        _token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)

    calls = []

    def fake_run_pipeline_service(session, *, user, item_id, defer_task, actor_kind="user"):
        calls.append({"user": user, "item_id": item_id, "actor_kind": actor_kind})
        return "run-1"

    monkeypatch.setattr("app.pipelines.service.run_pipeline_service", fake_run_pipeline_service)

    with db() as s:
        run_id = trigger_pipeline_by_webhook_service(
            s, item_id=item_id, raw_token=raw_token, defer_task=_noop_defer
        )

    assert run_id == "run-1"
    assert len(calls) == 1
    assert calls[0]["actor_kind"] == "webhook"
    assert calls[0]["item_id"] == item_id


def test_trigger_with_unknown_token_raises_404_never_leaks_existence(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        with pytest.raises(HTTPException) as excinfo:
            trigger_pipeline_by_webhook_service(
                s, item_id=item_id, raw_token="does-not-exist", defer_task=_noop_defer
            )
        assert excinfo.value.status_code == 404


def test_trigger_with_token_for_a_different_pipeline_id_raises_404(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        _token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)

    with db() as s:
        with pytest.raises(HTTPException) as excinfo:
            trigger_pipeline_by_webhook_service(
                s, item_id="a-different-pipeline-id", raw_token=raw_token, defer_task=_noop_defer
            )
        assert excinfo.value.status_code == 404


def test_trigger_by_webhook_actually_runs_the_pipeline_end_to_end(db):
    # Contrairement au test ci-dessus (run_pipeline_service mocké), celui-ci
    # laisse le vrai run_pipeline_service s'exécuter : preuve que le
    # déclenchement webhook produit bien un PipelineRun réel, pas
    # seulement un appel de fonction observé.
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        _token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)

    deferred = []
    with db() as s:
        run_id = trigger_pipeline_by_webhook_service(
            s,
            item_id=item_id,
            raw_token=raw_token,
            defer_task=lambda run_id, tid: deferred.append((run_id, tid)),
        )

    assert deferred == [(run_id, tenant_id)]
    with db() as s:
        run = pipelines_repo.get_run(s, tenant_id=tenant_id, run_id=run_id)
        assert run is not None
        assert run.pipeline_item_id == item_id


def test_touch_webhook_token_updates_last_used_at(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)

    with db() as s:
        trigger_pipeline_by_webhook_service(
            s, item_id=item_id, raw_token=raw_token, defer_task=_noop_defer
        )

    with db() as s:
        persisted = pipelines_repo.get_webhook_token(s, tenant_id=tenant_id, token_id=token_row.id)
        assert persisted is not None
        assert persisted.last_used_at is not None


def test_revoke_webhook_token_deletes_it(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        token_row, _raw = create_webhook_token_service(s, user=owner, item_id=item_id)

    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        revoke_webhook_token_service(s, user=owner, item_id=item_id, token_id=token_row.id)

    with db() as s:
        found = pipelines_repo.get_webhook_token(s, tenant_id=tenant_id, token_id=token_row.id)
        assert found is None


def test_revoked_token_no_longer_triggers(db):
    tenant_id, owner_id, item_id = _seed(db)
    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        token_row, raw_token = create_webhook_token_service(s, user=owner, item_id=item_id)
        revoke_webhook_token_service(s, user=owner, item_id=item_id, token_id=token_row.id)

    with db() as s:
        with pytest.raises(HTTPException) as excinfo:
            trigger_pipeline_by_webhook_service(
                s, item_id=item_id, raw_token=raw_token, defer_task=_noop_defer
            )
        assert excinfo.value.status_code == 404


def test_token_hash_is_unique_across_pipelines(db, monkeypatch):
    # Le hash étant dérivé de secrets.token_urlsafe(32), une collision
    # naturelle est virtuellement impossible — on force la collision en
    # figeant token_urlsafe pour prouver que la contrainte unique existe
    # réellement en base (et n'est pas seulement une intention de commentaire).
    tenant_id, owner_id, item_id = _seed(db)
    monkeypatch.setattr("app.pipelines.service.py_secrets.token_urlsafe", lambda n: "fixed-token")

    with db() as s:
        from app.users.models import User

        owner = s.get(User, owner_id)
        create_webhook_token_service(s, user=owner, item_id=item_id)

    with db() as s:
        from sqlalchemy.exc import IntegrityError

        from app.users.models import User

        owner = s.get(User, owner_id)
        with pytest.raises(IntegrityError):
            create_webhook_token_service(s, user=owner, item_id=item_id)


# --- Migration 0036 sur base Postgres réelle, non vide (piège CLAUDE.md n°8) ---
# Patron identique à test_attachments_migration_alembic.py : base jetable
# créée/détruite par CE test, jamais le schéma partagé postgis-test (un
# downgrade y serait destructif pour les autres tests postgis concurrents).
# @pytest.mark.postgis SUR CE SEUL TEST (pas un `pytestmark` de module) : les
# tests ci-dessus (sqlite en mémoire) doivent rester rapides et tourner sans
# CORE_TEST_DATABASE_URL, contrairement à celui-ci.

CORE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def throwaway_database_url():
    base_url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not base_url:
        pytest.skip("CORE_TEST_DATABASE_URL non défini — test postgis skippé")
    admin_engine = sa.create_engine(base_url, isolation_level="AUTOCOMMIT")
    db_name = f"sp53_migration_{uuid.uuid4().hex[:8]}"
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


@pytest.mark.postgis
def test_migration_0036_upgrades_and_downgrades_on_a_real_non_empty_base(
    throwaway_database_url,
):
    alembic_cfg = Config()
    alembic_cfg.set_main_option("script_location", str(CORE_DIR / "alembic"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = throwaway_database_url
    try:
        # 0034 : juste avant 0036, pour seeder tenant/role/user/item RÉELS
        # avant que la migration testée ne s'applique — preuve qu'elle
        # s'applique correctement sur une base déjà peuplée, pas seulement
        # une base fraîche.
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
                    "abstract, keywords, is_published, license, language, created_at, "
                    "updated_at) "
                    "VALUES ('p1', 't1', 'u1', 'pipeline', 'Pipeline', '', '[]', false, '', "
                    "'fr', now(), now())"
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
            assert "pipeline_webhook_tokens" in tables
            conn.execute(
                sa.text(
                    "INSERT INTO pipeline_webhook_tokens (id, tenant_id, pipeline_item_id, "
                    "token_hash, created_by, created_at) "
                    "VALUES ('tok1', 't1', 'p1', 'abc123', 'u1', now())"
                )
            )
            # La contrainte unique sur token_hash existe réellement en base,
            # pas seulement côté modèle Python.
            with pytest.raises(sa.exc.IntegrityError):
                conn.execute(
                    sa.text(
                        "INSERT INTO pipeline_webhook_tokens (id, tenant_id, "
                        "pipeline_item_id, token_hash, created_by, created_at) "
                        "VALUES ('tok2', 't1', 'p1', 'abc123', 'u1', now())"
                    )
                )
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
            assert "pipeline_webhook_tokens" not in tables
            # La ligne `items` insérée avant 0036 survit au downgrade (seule
            # la table ajoutée par 0036 est retirée).
            still_there = conn.execute(sa.text("SELECT 1 FROM items WHERE id = 'p1'")).scalar()
            assert still_there == 1
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
            assert "pipeline_webhook_tokens" in tables
        engine.dispose()
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

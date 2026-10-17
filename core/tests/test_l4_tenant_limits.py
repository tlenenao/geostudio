# SPDX-License-Identifier: Apache-2.0
"""AUD-098 : plafonds par tenant (tenant_limits), plafond d'utilisateurs et de runs actifs."""

import pytest
from fastapi import HTTPException

from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.pipelines import repository as pipelines_repo
from app.quotas.models import TenantLimits
from app.quotas.service import (
    QuotaExceededError,
    check_quota_or_raise,
    max_items_per_tenant,
    max_users_per_tenant,
)
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        s.add_all([Tenant(id="a", slug="a", name="A"), Tenant(id="b", slug="b", name="B")])
        s.commit()
        yield s


def _user(s, tenant_id, sub):
    return get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
    )


def test_override_wins_over_instance_limit_and_is_per_tenant(session, monkeypatch):
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "100")
    session.add(TenantLimits(tenant_id="a", max_items=3))
    session.commit()
    assert max_items_per_tenant(session, "a") == 3
    assert max_items_per_tenant(session, "b") == 100  # pas de surcharge : limite d'instance
    assert max_items_per_tenant() == 100


def test_user_quota_blocks_jit_creation_only_in_the_capped_tenant(session):
    session.add(TenantLimits(tenant_id="a", max_users=1))
    session.commit()
    _user(session, "a", "u1")
    session.commit()
    with pytest.raises(QuotaExceededError):
        _user(session, "a", "u2")
    session.rollback()
    _user(session, "a", "u1")  # un utilisateur existant se reconnecte toujours
    _user(session, "b", "u2")  # l'autre tenant n'est pas touché
    assert max_users_per_tenant(session, "a") == 1


def test_no_override_and_no_env_means_no_limit(session):
    for i in range(3):
        _user(session, "a", f"u{i}")
    check_quota_or_raise(session, tenant_id="a", kind="users")


def test_active_run_cap_is_per_tenant_across_pipelines(session):
    session.add(TenantLimits(tenant_id="a", max_active_runs=1))
    owner = {t: _user(session, t, "o") for t in ("a", "b")}
    for pid, t in (("p1", "a"), ("p2", "a"), ("p3", "b")):
        session.add(
            Item(id=pid, tenant_id=t, owner_id=owner[t].id, resource_type="pipeline", title=pid)
        )
    session.commit()
    pipelines_repo.create_run_unless_active(session, tenant_id="a", pipeline_item_id="p1")
    with pytest.raises(pipelines_repo.PipelineRunActive):
        pipelines_repo.create_run_unless_active(session, tenant_id="a", pipeline_item_id="p2")
    pipelines_repo.create_run_unless_active(session, tenant_id="b", pipeline_item_id="p3")


def test_unknown_kind_still_rejected(session):
    with pytest.raises((ValueError, HTTPException)):
        check_quota_or_raise(session, tenant_id="a", kind="nope")

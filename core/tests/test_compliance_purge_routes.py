# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 10 : POST /compliance/tenants/{tenant_id}/purge (déclenche
le job asynchrone) + GET /compliance/purges/{purge_id} (statut)."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.compliance import routes as compliance_routes
from app.compliance.models import PurgeReceipt
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles, update_role
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-sub",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="regular-sub",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        other_tenant = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        s.add(other_tenant)
        s.flush()
        ensure_built_in_roles(s, tenant_id=other_tenant.id)
        # compliance.manage n'est porté par aucun rôle prédéfini (Tâche 8)
        # — attribué explicitement au rôle admin de CE test, comme le
        # ferait un admin de tenant créant un rôle sur mesure. DOIT venir
        # APRÈS tout appel à get_or_create_user/ensure_built_in_roles :
        # ensure_built_in_roles() RÉCONCILIE les privilèges des rôles
        # prédéfinis existants vers BUILT_IN_ROLE_PRIVILEGES à chaque appel
        # (cf. test_roles_repository.py::…_reconciles_drifted_privileges…)
        # — get_or_create_user() l'appelle lui-même en interne, donc tout
        # update_role() antérieur à ces appels serait écrasé silencieusement.
        update_role(
            s,
            tenant_id=tenant.id,
            role_id=roles["admin"].id,
            name=None,
            privileges=[*roles["admin"].privileges, Privilege.COMPLIANCE_MANAGE.value],
        )
        s.commit()
        tenant_id, tenant_slug = tenant.id, tenant.slug
        admin_id, regular_id = admin.id, regular.id

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    deferred_jobs: list[tuple[str, str, str]] = []
    app.dependency_overrides[compliance_routes.get_purge_task_deferrer] = lambda: (
        lambda purge_id, tenant_id, requested_by_user_id: deferred_jobs.append(
            (purge_id, tenant_id, requested_by_user_id)
        )
    )
    client = TestClient(app)
    return {
        "app": app,
        "client": client,
        "Session": Session,
        "tenant_id": tenant_id,
        "tenant_slug": tenant_slug,
        "admin_id": admin_id,
        "regular_id": regular_id,
        "deferred": deferred_jobs,
    }


def _as_user_id(app, Session, user_id: str) -> None:
    def _get_current_user():
        with Session() as s:
            user = s.get(User, user_id)
            s.expunge(user)
            return user

    app.dependency_overrides[get_current_user] = _get_current_user


def test_purge_route_requires_compliance_manage_privilege(env):
    _as_user_id(env["app"], env["Session"], env["regular_id"])
    resp = env["client"].post(
        f"/compliance/tenants/{env['tenant_id']}/purge",
        json={"confirmSlug": env["tenant_slug"]},
    )
    assert resp.status_code == 403


def test_purge_route_rejects_wrong_slug_for_privileged_admin(env):
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    resp = env["client"].post(
        f"/compliance/tenants/{env['tenant_id']}/purge",
        json={"confirmSlug": "mauvais-slug"},
    )
    assert resp.status_code == 400
    assert env["deferred"] == []


def test_purge_route_accepts_correct_slug_and_defers_job(env):
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    resp = env["client"].post(
        f"/compliance/tenants/{env['tenant_id']}/purge",
        json={"confirmSlug": env["tenant_slug"]},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert "jobId" in body
    assert len(env["deferred"]) == 1
    assert env["deferred"][0][1] == env["tenant_id"]
    assert env["deferred"][0][2] == env["admin_id"]


def test_purge_route_rejects_cross_tenant_purge(env):
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    resp = env["client"].post(
        "/compliance/tenants/tenant-b/purge", json={"confirmSlug": "tenant-b"}
    )
    assert resp.status_code == 403
    assert env["deferred"] == []


def test_get_purge_status_returns_202_while_pending_and_200_once_receipt_exists(env):
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    created = (
        env["client"]
        .post(
            f"/compliance/tenants/{env['tenant_id']}/purge",
            json={"confirmSlug": env["tenant_slug"]},
        )
        .json()
    )
    purge_id = created["jobId"]

    pending = env["client"].get(f"/compliance/purges/{purge_id}")
    assert pending.status_code == 202

    # Simule la fin du job (écrite normalement par purge_tenant_task — le
    # déferrement lui-même est stubé dans ce test, cf. fixture `env`).
    with env["Session"]() as s:
        s.add(
            PurgeReceipt(
                id=purge_id,
                tenant_slug=env["tenant_slug"],
                requested_by_user_id=env["admin_id"],
                requested_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                counts={"items": 0},
            )
        )
        s.commit()

    done = env["client"].get(f"/compliance/purges/{purge_id}")
    assert done.status_code == 200
    assert done.json()["tenantSlug"] == env["tenant_slug"]


def test_get_purge_status_returns_202_for_an_unknown_purge_id(env):
    # Aucune ligne de statut intermédiaire propre à la purge (purge_receipts
    # n'existe qu'une fois le job TERMINÉ, spec §3.3) : impossible de
    # distinguer "jamais déclenché" de "encore en cours" sans table dédiée
    # — décision de portée assumée pour cette tâche (documentée dans le
    # commit), même comportement que pour un id réel encore en cours.
    _as_user_id(env["app"], env["Session"], env["admin_id"])
    resp = env["client"].get("/compliance/purges/does-not-exist")
    assert resp.status_code == 202

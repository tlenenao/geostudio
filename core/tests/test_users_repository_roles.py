# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.roles.repository import ensure_built_in_roles, get_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_new_user_without_bootstrap_gets_the_creator_role():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
        )
        role = get_role(s, tenant_id=tenant.id, role_id=user.role_id)
        assert role is not None and role.slug == "creator"
        assert user.is_admin is False


def test_bootstrap_admin_assigns_the_admin_role_and_never_demotes():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=user.role_id)
        assert role is not None and role.slug == "admin"
        assert user.is_admin is True
        # Un appel ultérieur sans bootstrap ne rétrograde pas (retirer un sub
        # de CORE_ADMIN_SUBS ne doit pas destituer silencieusement).
        again = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        assert again.id == user.id and again.is_admin is True


def test_bootstrap_analyst_assigns_the_analyst_role_but_never_demotes_an_admin():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        still_admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_analyst=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=still_admin.role_id)
        assert still_admin.id == admin.id and role is not None and role.slug == "admin"

        analyst = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="b",
            email=None,
            first_name="",
            last_name="",
            bootstrap_analyst=True,
        )
        role = get_role(s, tenant_id=tenant.id, role_id=analyst.role_id)
        assert role is not None and role.slug == "analyst"


def test_set_user_role_updates_role_id_and_synced_is_admin():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
        )
        updated = set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=roles["admin"].id,
            role_slug="admin",
        )
        assert updated is not None and updated.role_id == roles["admin"].id
        assert updated.is_admin is True
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        assert user.is_admin is False
        assert (
            set_user_role(
                s,
                tenant_id=tenant.id,
                user_id="nope",
                role_id=roles["admin"].id,
                role_slug="admin",
            )
            is None
        )

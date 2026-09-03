# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.db import init_db, make_engine, make_session_factory
from app.roles.guards import has_privilege, require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_require_privilege_allows_a_holder_and_rejects_the_rest():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="r",
            email=None,
            first_name="",
            last_name="",
        )
        s.flush()

        require_privilege(s, admin, Privilege.ADMIN_ROLES_MANAGE.value)  # ne lève pas

        with pytest.raises(HTTPException) as exc_info:
            require_privilege(s, reader, Privilege.ADMIN_ROLES_MANAGE.value)
        assert exc_info.value.status_code == 403


def test_has_privilege_returns_a_plain_bool_without_raising():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a2",
            username="a2",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r2",
            username="r2",
            email=None,
            first_name="",
            last_name="",
        )
        s.flush()

        assert has_privilege(s, admin, Privilege.ADMIN_ROLES_MANAGE.value) is True
        assert has_privilege(s, reader, Privilege.ADMIN_ROLES_MANAGE.value) is False

# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.db import init_db, make_engine, make_session_factory
from app.roles.guards import has_privilege, require_any_privilege, require_privilege
from app.roles.privileges import Privilege
from app.roles.repository import create_role, ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
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

        # role_id bidon (get_role() renvoie None) : ne lève pas, retourne False.
        # Objet transitoire, jamais ajouté/flushé à la session — role_id est une
        # FK réelle (app/users/models.py), la persister violerait la contrainte.
        # has_privilege() ne lit que les attributs Python de `user`, jamais la
        # ligne `users` elle-même.
        bogus_role_user = User(
            id="bogus",
            tenant_id=reader.tenant_id,
            oidc_sub="bogus",
            username="bogus",
            role_id="does-not-exist",
        )
        assert has_privilege(s, bogus_role_user, Privilege.ADMIN_ROLES_MANAGE.value) is False


def test_require_any_privilege_allows_holder_of_at_least_one():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        built_in_roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        # rôle sur mesure ne portant QUE automation.secrets.manage
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Secrets pipeline",
            privileges=[Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )
        holder = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="h",
            username="h",
            email=None,
            first_name="",
            last_name="",
        )
        holder.role_id = custom.id
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r2",
            username="r2",
            email=None,
            first_name="",
            last_name="",
        )
        # Rôle "reader" (zéro privilège) plutôt que le "creator" par défaut :
        # depuis SP-47 §2.2, le Créateur porte automation.secrets.manage — un
        # "creator" par défaut ne serait plus un témoin valide de "ne porte ni
        # l'un ni l'autre" ci-dessous.
        reader.role_id = built_in_roles["reader"].id
        s.flush()

        # ne lève pas : porte automation.secrets.manage, un des deux acceptés
        require_any_privilege(
            s,
            holder,
            [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )

        # lève : rôle "reader", ne porte ni l'un ni l'autre
        with pytest.raises(HTTPException) as exc_info:
            require_any_privilege(
                s,
                reader,
                [Privilege.ADMIN_SECRETS_MANAGE.value, Privilege.AUTOMATION_SECRETS_MANAGE.value],
            )
        assert exc_info.value.status_code == 403
        # le message cite les DEUX privilèges acceptés, pas un seul —
        # sinon un rôle sur mesure ne sait pas lequel des deux cocher
        assert "admin.secrets.manage" in str(exc_info.value.detail)
        assert "automation.secrets.manage" in str(exc_info.value.detail)


def test_require_any_privilege_rejects_when_privilege_list_is_empty():
    # garde-fou : une liste vide ne doit jamais autoriser par défaut
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
        s.flush()
        with pytest.raises(HTTPException):
            require_any_privilege(s, admin, [])

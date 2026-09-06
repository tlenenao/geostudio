# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import event

from app.db import init_db, make_engine, make_session_factory
from app.roles.privileges import BUILT_IN_ROLE_NAMES, BUILT_IN_ROLE_PRIVILEGES, Privilege
from app.roles.repository import (
    count_role_holders,
    count_users_with_privileges,
    create_role,
    delete_role,
    ensure_built_in_roles,
    get_privilege_catalog,
    get_role,
    list_roles,
    roles_for_ids,
    update_role,
    would_orphan_privilege_holders,
)
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_ensure_built_in_roles_is_idempotent_and_covers_the_four_profiles():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert set(roles) == {"admin", "creator", "analyst", "reader"}
        # compliance.manage exclu même de l'Administrateur (SP-58 Tâche 8,
        # spec §3.3, décision explicite : purge de tenant, irréversible —
        # jamais glissé silencieusement dans un rôle prédéfini).
        assert roles["admin"].privileges == [
            p.value for p in Privilege if p != Privilege.COMPLIANCE_MANAGE
        ]
        assert roles["reader"].privileges == []
        assert all(r.is_built_in for r in roles.values())
        again = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert {r.id for r in again.values()} == {r.id for r in roles.values()}


def test_ensure_built_in_roles_reconciles_drifted_privileges_on_existing_roles():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        # Simule une dérive : un déploiement plus ancien avait un jeu de
        # privilèges différent pour "creator" (ex. avant l'ajout d'un
        # privilège à BUILT_IN_ROLE_PRIVILEGES dans une future release).
        roles["creator"].privileges = [Privilege.DATA_VIEW.value]
        roles["creator"].name = "Ancien nom"
        s.flush()
        s.commit()
        reconciled = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert reconciled["creator"].privileges == BUILT_IN_ROLE_PRIVILEGES["creator"]
        assert reconciled["creator"].name == BUILT_IN_ROLE_NAMES["creator"]
        assert reconciled["creator"].id == roles["creator"].id


def test_create_update_delete_a_custom_role():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        role = create_role(
            s,
            tenant_id=tenant.id,
            name="Contributeur moissonnage",
            privileges=[Privilege.ADMIN_HARVEST_MANAGE.value],
        )
        assert role.is_built_in is False
        fetched = get_role(s, tenant_id=tenant.id, role_id=role.id)
        assert fetched is not None and fetched.name == "Contributeur moissonnage"
        updated = update_role(
            s,
            tenant_id=tenant.id,
            role_id=role.id,
            name="Moissonnage+",
            privileges=[
                Privilege.ADMIN_HARVEST_MANAGE.value,
                Privilege.ADMIN_COLLECTIONS_MANAGE.value,
            ],
        )
        assert updated is not None and len(updated.privileges) == 2
        assert {r.id for r in list_roles(s, tenant_id=tenant.id)} >= {role.id}
        delete_role(s, tenant_id=tenant.id, role_id=role.id)
        assert get_role(s, tenant_id=tenant.id, role_id=role.id) is None


def test_count_role_holders():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        u = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
        )
        s.flush()
        assert count_role_holders(s, tenant_id=tenant.id, role_id=roles["creator"].id) >= 1
        assert count_role_holders(s, tenant_id=tenant.id, role_id=roles["admin"].id) == 0
        assert u.role_id == roles["creator"].id


def test_count_users_with_privileges_and_orphan_detection():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        needed = [Privilege.ADMIN_USERS_MANAGE.value, Privilege.ADMIN_ROLES_MANAGE.value]
        assert count_users_with_privileges(s, tenant_id=tenant.id, privileges=needed) == 1
        # Retirer ces deux privilèges du rôle admin lui-même (hypothèse) laisserait
        # le tenant sans personne capable de gérer utilisateurs/rôles.
        assert would_orphan_privilege_holders(
            s,
            tenant_id=tenant.id,
            privileges=needed,
            role_id=roles["admin"].id,
            new_privileges=[],
        )
        # Ne rien changer d'autre ne l'orpheline pas.
        assert not would_orphan_privilege_holders(
            s,
            tenant_id=tenant.id,
            privileges=needed,
            role_id=roles["reader"].id,
            new_privileges=[],
        )


def test_privilege_catalog_covers_every_privilege_with_domain_and_label_key():
    catalog = get_privilege_catalog()
    assert len(catalog) == len(list(Privilege))
    for entry in catalog:
        assert set(entry) == {"privilege", "domain", "labelKey"}


def test_roles_for_ids_empty_list_returns_empty_dict():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        assert roles_for_ids(s, tenant_id=tenant.id, role_ids=[]) == {}


def test_roles_for_ids_returns_the_matching_roles_keyed_by_id():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        got = roles_for_ids(
            s, tenant_id=tenant.id, role_ids=[roles["admin"].id, roles["reader"].id]
        )
        assert set(got) == {roles["admin"].id, roles["reader"].id}
        assert got[roles["admin"].id].slug == "admin"
        assert got[roles["reader"].id].slug == "reader"
        # Un role_id inconnu est absent du résultat, jamais une KeyError/None
        # explicite — même contrat que roles_for_items.
        assert "does-not-exist" not in roles_for_ids(
            s, tenant_id=tenant.id, role_ids=["does-not-exist"]
        )


def test_roles_for_ids_filters_by_tenant():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        other = Tenant(id="other", slug="other", name="Other")
        s.add(other)
        s.flush()
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        other_roles = ensure_built_in_roles(s, tenant_id=other.id)
        # Un role_id d'un AUTRE tenant, même si l'id existe bien en base,
        # doit rester invisible quand on interroge sous tenant.id.
        got = roles_for_ids(s, tenant_id=tenant.id, role_ids=[other_roles["admin"].id])
        assert got == {}
        assert roles_for_ids(s, tenant_id=tenant.id, role_ids=[roles["admin"].id])


def test_roles_for_ids_is_a_single_query():
    Session = _session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        role_ids = [r.id for r in roles.values()]

        seen = 0

        def bump(conn, cursor, statement, params, context, executemany):
            nonlocal seen
            seen += 1

        event.listen(s.get_bind(), "before_cursor_execute", bump)
        try:
            roles_for_ids(s, tenant_id=tenant.id, role_ids=role_ids)
        finally:
            event.remove(s.get_bind(), "before_cursor_execute", bump)
        assert seen == 1

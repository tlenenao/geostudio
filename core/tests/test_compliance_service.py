# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 7 : anonymisation d'un utilisateur (RGPD Art. 17).

Ce que l'anonymisation doit préserver : les objets qu'il possède (items,
collections, pièces jointes) restent intacts, attribués au compte anonymisé
— aucune fuite nouvelle (ces objets étaient déjà visibles avant). Ce qu'elle
doit supprimer : les notifications qui lui sont adressées, son appartenance
aux groupes. Ce qu'elle doit garantir : idempotence (un second appel est un
échec explicite), unicité de oidc_sub malgré l'anonymisation, et un
garde-fou anti-lockout (le dernier titulaire d'un privilège anti-lockout
— admin.users.manage/admin.roles.manage — ne peut pas s'auto-effacer)."""

import pytest

from app.attachments.models import Attachment
from app.collections.models import Collection
from app.compliance.service import (
    AnonymizationLockoutError,
    UserAlreadyErasedError,
    anonymize_user,
)
from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.notifications.models import Notification
from app.roles.repository import ensure_built_in_roles
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        # bootstrap_admin=True donne le rôle admin — seul titulaire de
        # admin.users.manage/admin.roles.manage dans ce tenant.
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-sub",
            username="admin",
            email="admin@example.test",
            first_name="Ada",
            last_name="Min",
            bootstrap_admin=True,
        )
        # target : un utilisateur "creator" ordinaire, PAS admin — celui
        # qu'on anonymise dans le scénario nominal (pas de risque de
        # lockout, admin reste disponible).
        target = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="target-sub",
            username="target",
            email="target@example.test",
            first_name="Tar",
            last_name="Get",
        )
        item = Item(
            id="item1",
            tenant_id=tenant.id,
            owner_id=target.id,
            resource_type="map",
            title="Carte de target",
        )
        s.add(item)
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=target.id,
            table_name="col1",
            title="Collection de target",
            description="",
            pk_column="id",
        )
        s.add(col)
        s.flush()
        attachment = Attachment(
            id="att1",
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=100,
            s3_key=f"{tenant.id}/col1/f1/a.jpg",
            created_by=target.id,
        )
        s.add(attachment)
        notification = Notification(
            id="notif1",
            tenant_id=tenant.id,
            recipient_user_id=target.id,
            kind="ingestion",
            status="success",
            item_id=None,
            item_resource_type=None,
            item_title="Import terminé",
        )
        s.add(notification)
        group = Group(id="grp1", tenant_id=tenant.id, name="Groupe test", created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id="grp1", user_id=target.id, tenant_id=tenant.id))
        s.commit()
        target_id = target.id
        admin_id = admin.id
        tenant_id = tenant.id
        role_ids = {slug: role.id for slug, role in roles.items()}
    yield Session, tenant_id, target_id, admin_id, role_ids


def test_anonymize_user_erases_identity_and_sets_erased_at(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    with Session() as s:
        from app.users.models import User

        user = s.get(User, target_id)
        assert user.username != "target"
        assert user.username.startswith("utilisateur-efface-")
        assert user.email is None
        assert user.first_name == ""
        assert user.last_name == ""
        assert user.oidc_sub != "target-sub"
        assert user.oidc_sub.startswith("erased:")
        assert user.erased_at is not None


def test_anonymize_user_preserves_owned_objects(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    with Session() as s:
        item = s.get(Item, "item1")
        assert item is not None
        assert item.owner_id == target_id  # inchangé — pointe vers la ligne anonymisée

        col = s.get(Collection, "col1")
        assert col is not None
        assert col.owner_id == target_id

        attachment = s.get(Attachment, "att1")
        assert attachment is not None
        assert attachment.created_by == target_id


def test_anonymize_user_deletes_notifications(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    with Session() as s:
        assert s.get(Notification, "notif1") is None


def test_anonymize_user_removes_group_membership(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    with Session() as s:
        remaining = s.get(GroupMember, {"group_id": "grp1", "user_id": target_id})
        assert remaining is None


def test_anonymize_user_oidc_sub_stays_unique_across_a_second_user(env):
    Session, tenant_id, target_id, admin_id, roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    # Un second utilisateur du même tenant, anonymisé à son tour : aucune
    # collision possible sur oidc_sub (uq_users_tenant_oidc_sub) — chaque
    # appel génère un uuid4 distinct.
    with Session() as s:
        second = get_or_create_user(
            s,
            tenant_id=tenant_id,
            oidc_sub="second-sub",
            username="second",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        second_id = second.id

    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=second_id)  # ne lève pas
        s.commit()


def test_anonymize_user_is_idempotent_second_call_fails_explicitly(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    with Session() as s, pytest.raises(UserAlreadyErasedError):
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)


def test_anonymize_user_rejects_cross_tenant_target(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    with Session() as s, pytest.raises(LookupError):
        anonymize_user(s, tenant_id="autre-tenant", user_id=target_id)


def test_anonymize_user_audit_payload_never_contains_old_identity(env, monkeypatch):
    Session, tenant_id, target_id, _admin_id, _roles = env
    captured_payloads = []
    import app.compliance.service as service_module

    original_write_audit = service_module.write_audit

    def _spy_write_audit(session, **kwargs):
        captured_payloads.append(kwargs.get("payload"))
        return original_write_audit(session, **kwargs)

    monkeypatch.setattr(service_module, "write_audit", _spy_write_audit)

    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)
        s.commit()

    assert captured_payloads, "write_audit jamais appelé"
    for payload in captured_payloads:
        assert "target" not in str(payload)
        assert "target@example.test" not in str(payload)


# --- garde anti-lockout ---------------------------------------------------


def test_anonymize_user_refuses_to_erase_the_last_admin_users_manage_holder(env):
    Session, tenant_id, _target_id, admin_id, _roles = env
    # admin_id est le SEUL titulaire de admin.users.manage dans ce tenant
    # (rôle "admin", cf. fixture) — l'anonymiser locquerait le tenant hors
    # de toute gestion d'utilisateurs/rôles.
    with Session() as s, pytest.raises(AnonymizationLockoutError):
        anonymize_user(s, tenant_id=tenant_id, user_id=admin_id)


def test_anonymize_user_allows_erasing_an_admin_when_another_admin_remains(env):
    Session, tenant_id, _target_id, admin_id, roles = env
    with Session() as s:
        second_admin = get_or_create_user(
            s,
            tenant_id=tenant_id,
            oidc_sub="second-admin-sub",
            username="second-admin",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=tenant_id,
            user_id=second_admin.id,
            role_id=roles["admin"],
            role_slug="admin",
        )
        s.commit()

    # Deux admins désormais : anonymiser le premier ne locque plus rien.
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=admin_id)  # ne lève pas
        s.commit()


def test_anonymize_user_allows_erasing_a_non_privileged_user(env):
    Session, tenant_id, target_id, _admin_id, _roles = env
    # target n'a aucun privilège anti-lockout (rôle "creator" par défaut) —
    # jamais bloqué par ce garde-fou.
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=target_id)  # ne lève pas
        s.commit()

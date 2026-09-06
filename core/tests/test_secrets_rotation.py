# SPDX-License-Identifier: Apache-2.0
"""Rotation atomique de la clé maître des secrets (GAP-75, design SP-59
§3.1). Le risque principal de ce module est un échec partiel qui laisserait
certaines lignes rechiffrées avec la nouvelle clé et d'autres non — le test
d'atomicité (ci-dessous) est le plus important de ce fichier."""

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from app.audit.models import AuditLog
from app.db import init_db, make_engine, make_session_factory
from app.secrets import crypto
from app.secrets import repository as repo
from app.secrets.rotation import rotate_all_secrets
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

OLD_KEY = bytes(range(0, 32))
NEW_KEY = bytes(range(31, 63))
WRONG_KEY = bytes(range(1, 33))


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def two_tenants(session):
    tenant_a = get_or_create_default_tenant(session)
    tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
    session.add(tenant_b)
    session.flush()
    user_a = get_or_create_user(
        session,
        tenant_id=tenant_a.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    user_b = get_or_create_user(
        session,
        tenant_id=tenant_b.id,
        oidc_sub="b",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant_a, user_a, tenant_b, user_b


def _make_secret(session, *, tenant_id, created_by, name, key):
    ciphertext, nonce = crypto.encrypt({"kind": "bearer_token", "token": name}, key=key)
    return repo.create_secret(
        session,
        tenant_id=tenant_id,
        created_by=created_by,
        name=name,
        kind="bearer_token",
        ciphertext=ciphertext,
        nonce=nonce,
    )


def test_rotate_all_secrets_reencrypts_every_secret_with_new_key(session, two_tenants):
    tenant_a, user_a, tenant_b, user_b = two_tenants
    _make_secret(session, tenant_id=tenant_a.id, created_by=user_a.id, name="a1", key=OLD_KEY)
    _make_secret(session, tenant_id=tenant_a.id, created_by=user_a.id, name="a2", key=OLD_KEY)
    _make_secret(session, tenant_id=tenant_b.id, created_by=user_b.id, name="b1", key=OLD_KEY)

    result = rotate_all_secrets(session, old_key=OLD_KEY, new_key=NEW_KEY)

    for secret in repo.list_all_secrets(session):
        # déchiffre avec la nouvelle clé
        assert crypto.decrypt(secret.ciphertext, secret.nonce, key=NEW_KEY)
        # l'ancienne clé ne fonctionne plus
        with pytest.raises(InvalidTag):
            crypto.decrypt(secret.ciphertext, secret.nonce, key=OLD_KEY)

    assert result.total == 3
    assert result.rotated_by_tenant == {tenant_a.id: 2, tenant_b.id: 1}

    audit_rows = session.scalars(
        select(AuditLog).where(AuditLog.action == "secret.rotate_master_key")
    ).all()
    assert {r.tenant_id for r in audit_rows} == {tenant_a.id, tenant_b.id}
    assert all(r.actor_kind == "system" for r in audit_rows)


def test_rotate_all_secrets_aborts_entirely_if_any_secret_fails_to_decrypt(session, two_tenants):
    tenant_a, user_a, tenant_b, user_b = two_tenants
    _make_secret(session, tenant_id=tenant_a.id, created_by=user_a.id, name="a1", key=OLD_KEY)
    _make_secret(session, tenant_id=tenant_b.id, created_by=user_b.id, name="b1", key=OLD_KEY)
    # 3e secret corrompu : chiffré avec une clé différente, jamais OLD_KEY.
    _make_secret(
        session, tenant_id=tenant_a.id, created_by=user_a.id, name="corrupt", key=WRONG_KEY
    )

    before = {s.id: (s.ciphertext, s.nonce) for s in repo.list_all_secrets(session)}

    with pytest.raises(InvalidTag):
        rotate_all_secrets(session, old_key=OLD_KEY, new_key=NEW_KEY)

    # Relecture directe depuis la session — pas depuis un objet Python
    # potentiellement déjà muté en mémoire.
    session.expire_all()
    after = {s.id: (s.ciphertext, s.nonce) for s in repo.list_all_secrets(session)}
    assert after == before
    assert session.scalars(select(AuditLog)).all() == []

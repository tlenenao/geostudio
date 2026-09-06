# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 6 : schéma additif pour l'anonymisation d'utilisateur
(users.erased_at) et la preuve de purge de tenant (purge_receipts)."""

from datetime import UTC, datetime

from app.compliance.models import PurgeReceipt
from app.db import init_db, make_engine, make_session_factory
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_user_erased_at_defaults_to_none():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        assert user.erased_at is None


def test_purge_receipt_has_no_foreign_key_to_tenants_and_survives_independently():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        # Aucun tenant créé du tout — la ligne doit pouvoir exister sans
        # qu'aucun tenant référencé n'existe (preuve qu'il n'y a pas de FK).
        receipt = PurgeReceipt(
            id="pr1",
            tenant_slug="tenant-disparu",
            requested_by_user_id="user-disparu",
            requested_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            counts={"items": 3, "collections": 1},
        )
        s.add(receipt)
        s.commit()

    with Session() as s:
        reloaded = s.get(PurgeReceipt, "pr1")
        assert reloaded is not None
        assert reloaded.tenant_slug == "tenant-disparu"
        assert reloaded.counts == {"items": 3, "collections": 1}

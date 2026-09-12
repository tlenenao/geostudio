# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.collections.models import Collection
from app.collections.routes import get_readable_collection
from app.configs.guest_access import GuestActor
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _create_private_collection(session, *, tenant_id, owner_id, collection_id):
    col = Collection(
        id=collection_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=collection_id,
        title=collection_id,
        description="",
        pk_column="id",
        editable=True,
        is_public=False,
    )
    session.add(col)
    session.flush()
    return col


def _guest(tenant_id, *, allowed=("incidents",)) -> GuestActor:
    return GuestActor(
        tenant_id=tenant_id,
        item_id="app-1",
        share_link_id="link-1",
        allowed_item_ids=frozenset({"app-1"}),
        allowed_collection_ids=frozenset(allowed),
    )


def test_guest_with_allowed_collection_bypasses_can(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        col = get_readable_collection(session, None, "incidents", guest=_guest(tenant.id))

        assert col.id == "incidents"


def test_guest_without_the_collection_in_scope_still_gets_404(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="secret"
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session, None, "secret", guest=_guest(tenant.id, allowed=("incidents",))
            )
        assert exc_info.value.status_code == 404


def test_guest_uses_its_own_tenant_not_the_default_tenant(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        # guest.tenant_id volontairement erroné : la collection n'existe pas
        # dans ce tenant-là, même si "incidents" existe ailleurs.
        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session,
                None,
                "incidents",
                guest=GuestActor(
                    tenant_id="wrong-tenant",
                    item_id="app-1",
                    share_link_id="link-1",
                    allowed_item_ids=frozenset({"app-1"}),
                    allowed_collection_ids=frozenset({"incidents"}),
                ),
            )
        assert exc_info.value.status_code == 404

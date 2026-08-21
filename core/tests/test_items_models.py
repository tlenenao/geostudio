# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select

from app.db import Base, init_db, make_engine, make_session_factory
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_can_persist_and_load_item():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            user = get_or_create_user(
                session,
                tenant_id=tenant.id,
                oidc_sub="sub-1",
                username="alice",
                email=None,
                first_name="",
                last_name="",
            )
            item = Item(
                id="item-1",
                tenant_id=tenant.id,
                owner_id=user.id,
                resource_type="app",
                title="My App",
            )
            session.add(item)
            session.commit()

        with Session() as session:
            loaded = session.scalar(select(Item).where(Item.id == "item-1"))
            assert loaded is not None
            assert loaded.title == "My App"
            assert loaded.abstract == ""
            assert loaded.keywords == []
            assert loaded.is_published is False
            assert loaded.thumbnail_key is None
    finally:
        engine.dispose()


def test_base_metadata_has_items_table():
    assert "items" in Base.metadata.tables

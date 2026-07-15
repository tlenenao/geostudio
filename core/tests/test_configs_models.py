# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory, init_db
from app.configs.models import Config, ConfigRevision
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_can_persist_config_and_revision():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    try:
        init_db(engine)
        Session = make_session_factory(engine)

        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            user = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice", email=None, first_name="", last_name="",
            )
            session.add(Item(
                id="item-1", tenant_id=tenant.id, owner_id=user.id,
                resource_type="app", title="My App",
            ))
            # Explicit flush: Item and Config aren't linked by an ORM
            # relationship (just a raw FK column), so the unit of work isn't
            # guaranteed to insert `items` before `configs` in the same
            # flush; force it so the now-enforced FK doesn't fail.
            session.flush()
            config = Config(
                id="c1", tenant_id=tenant.id, kind="app", item_id="item-1", current_version=1
            )
            session.add(config)
            session.add(ConfigRevision(
                tenant_id=tenant.id, config_id="c1", version=1, data={"kind": "app"}
            ))
            session.commit()

        with Session() as session:
            loaded = session.scalar(select(Config).where(Config.id == "c1"))
            assert loaded is not None
            assert loaded.kind == "app"
            assert loaded.current_version == 1
            rev = session.scalar(select(ConfigRevision).where(ConfigRevision.config_id == "c1"))
            assert rev.data == {"kind": "app"}
    finally:
        engine.dispose()


def test_base_metadata_has_both_tables():
    assert "configs" in Base.metadata.tables
    assert "config_revisions" in Base.metadata.tables

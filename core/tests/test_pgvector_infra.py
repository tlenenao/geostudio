"""Colonnes embedding (SP-7 Task 2) : la colonne existe, un vecteur écrit se
relit identique, NULL par défaut (dégradation gracieuse tant que le job
d'embedding n'est pas passé — voir Task 5/7)."""
import pytest
from sqlalchemy import select

from app.collections.models import Collection
from app.db import Base, make_session_factory
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("TRUNCATE items, collections, users, tenants CASCADE"))


def test_item_embedding_defaults_to_null(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    item = Item(
        id="i1", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="X",
    )
    session.add(item)
    session.flush()
    assert session.scalar(select(Item.embedding).where(Item.id == "i1")) is None


def test_item_embedding_roundtrips(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    item = Item(
        id="i2", tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="X",
    )
    session.add(item)
    session.flush()
    vector = [0.1] * 1536
    item.embedding = vector
    session.flush()
    session.expire(item)
    reloaded = session.get(Item, "i2")
    assert reloaded.embedding == pytest.approx(vector)


def test_collection_embedding_roundtrips(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    col = Collection(
        id="c1", tenant_id=tenant.id, owner_id=user.id, table_name="c1",
        title="Collection", pk_column="id",
    )
    session.add(col)
    session.flush()
    vector = [0.2] * 1536
    col.embedding = vector
    session.flush()
    session.expire(col)
    reloaded = session.get(Collection, "c1")
    assert reloaded.embedding == pytest.approx(vector)

# SPDX-License-Identifier: Apache-2.0
"""AUD-097 : un partage à échéance dépassée est inerte sur TOUS les lecteurs (parité)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.collections import repository as col_repo
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.items.models import Item
from app.public_submit.service import moderator_ids
from app.sharing import repository as sharing_repo
from app.sharing.models import CollectionShare, Group, GroupMember, ItemShare
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user

PAST = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)
FUTURE = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1)


@pytest.fixture()
def world():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        s.add(Tenant(id="t", slug="t", name="T"))
        s.commit()
        users = {
            n: get_or_create_user(
                s,
                tenant_id="t",
                oidc_sub=n,
                username=n,
                email=None,
                first_name="",
                last_name="",
            )
            for n in ("owner", "bob")
        }
        s.add(Group(id="g", tenant_id="t", name="G", created_by=users["owner"].id))
        s.flush()
        s.add(GroupMember(group_id="g", user_id=users["bob"].id, tenant_id="t"))
        for i in ("it-past", "it-future", "it-none"):
            s.add(
                Item(id=i, tenant_id="t", owner_id=users["owner"].id, resource_type="map", title=i)
            )
            s.add(
                Collection(
                    id=f"c-{i}",
                    tenant_id="t",
                    owner_id=users["owner"].id,
                    table_name=f"tbl_{i.replace('-', '_')}",
                    title=i,
                    description="",
                    pk_column="id",
                )
            )
        s.flush()
        for i, exp in (("it-past", PAST), ("it-future", FUTURE), ("it-none", None)):
            s.add(ItemShare(item_id=i, group_id="g", tenant_id="t", role="viewer", expires_at=exp))
            s.add(
                CollectionShare(
                    collection_id=f"c-{i}",
                    group_id="g",
                    tenant_id="t",
                    role="editor",
                    expires_at=exp,
                )
            )
        s.commit()
        yield s, users


def test_roles_for_items_and_collections_ignore_expired_shares(world):
    s, users = world
    bob = users["bob"].id
    items = sharing_repo.roles_for_items(
        s, tenant_id="t", user_id=bob, item_ids=["it-past", "it-future", "it-none"]
    )
    assert set(items) == {"it-future", "it-none"}
    cols = sharing_repo.roles_for_collections(
        s,
        tenant_id="t",
        user_id=bob,
        collection_ids=["c-it-past", "c-it-future", "c-it-none"],
    )
    assert set(cols) == {"c-it-future", "c-it-none"}


def test_visible_collections_catalogue_and_recipients_ignore_expired_shares(world):
    s, users = world
    stmt = col_repo._visible_collections_stmt(
        tenant_id="t", user_id=users["bob"].id, can_see_all=False
    )
    assert {c.id for c in s.scalars(stmt)} == {"c-it-future", "c-it-none"}
    assert sharing_repo.share_recipient_ids(s, tenant_id="t", item_id="it-past") == []
    assert sharing_repo.share_recipient_ids(s, tenant_id="t", item_id="it-future") == [
        users["bob"].id
    ]
    col_past = s.get(Collection, "c-it-past")
    col_future = s.get(Collection, "c-it-future")
    assert users["bob"].id not in moderator_ids(s, col_past)
    assert users["bob"].id in moderator_ids(s, col_future)


def test_item_listing_ignores_expired_shares(world):
    s, users = world
    page = items_repo.list_items(
        s,
        tenant_id="t",
        current_user_id=users["bob"].id,
        q=None,
        resource_type=None,
        scope="shared",
        page=1,
        page_size=50,
    )
    assert {i.pk for i in page.items} == {"it-future", "it-none"}


def test_replace_shares_stores_the_expiry(world):
    s, _ = world
    assert sharing_repo.replace_shares(
        s, tenant_id="t", item_id="it-none", shares=[("g", "viewer", FUTURE)]
    )
    assert s.get(ItemShare, ("it-none", "g")).expires_at == FUTURE
    aware = FUTURE.replace(tzinfo=UTC)
    assert sharing_repo.to_naive_utc(aware) == FUTURE


def test_listing_sharing_hides_expired_shares(world):
    s, _ = world
    assert sharing_repo.list_shares(s, item_id="it-past") == []
    assert len(sharing_repo.list_shares(s, item_id="it-future")) == 1
    assert len(sharing_repo.list_shares(s, item_id="it-none")) == 1
    assert col_repo.get_collection_sharing(s, tenant_id="t", collection_id="c-it-past") == []
    assert len(col_repo.get_collection_sharing(s, tenant_id="t", collection_id="c-it-none")) == 1

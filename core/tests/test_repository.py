# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import make_engine, make_session_factory, init_db
from app.configs import repository as repo
from app.configs.schemas import BuilderConfig
from app.items.models import Item
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def _config(kind: str = "app", widget: str = "map") -> BuilderConfig:
    return BuilderConfig.model_validate({
        "kind": kind,
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    })


def _make_item(session, item_id: str) -> str:
    # Config.item_id is now a real, non-null FK to items.id (Step 6): tests
    # that create a Config must first insert a matching Item row, or SQLite's
    # now-enforced FK (Step 5) raises IntegrityError on the Config insert.
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="sub-1",
        username="alice", email=None, first_name="", last_name="",
    )
    session.add(Item(
        id=item_id, tenant_id=tenant.id, owner_id=user.id,
        resource_type="app", title="placeholder",
    ))
    session.commit()
    return tenant.id


def test_create_then_get(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(), item_id="item-1", tenant_id=tenant_id)
    assert created.version == 1
    assert created.itemId == "item-1"

    loaded = repo.get_config(session, created.id)
    assert loaded is not None
    assert loaded.config.kind == "app"
    assert loaded.config.layout.items[0].widget == "map"


def test_get_missing_returns_none(session):
    assert repo.get_config(session, "nope") is None


def test_update_creates_new_revision(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(widget="map"), item_id="item-1", tenant_id=tenant_id)
    updated = repo.update_config(session, created.id, _config(widget="table"), tenant_id=tenant_id)
    assert updated is not None
    assert updated.version == 2
    assert updated.config.layout.items[0].widget == "table"

    revisions = repo.list_revisions(session, created.id)
    assert [r.version for r in revisions] == [1, 2]


def test_update_missing_returns_none(session):
    assert repo.update_config(session, "nope", _config(), tenant_id="default") is None


def test_rollback_restores_old_revision_as_new(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(widget="map"), item_id="item-1", tenant_id=tenant_id)
    repo.update_config(session, created.id, _config(widget="table"), tenant_id=tenant_id)

    rolled = repo.rollback_config(session, created.id, version=1, tenant_id=tenant_id)
    assert rolled is not None
    assert rolled.version == 3
    assert rolled.config.layout.items[0].widget == "map"
    assert [r.version for r in repo.list_revisions(session, created.id)] == [1, 2, 3]


def test_rollback_missing_version_returns_none(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(), item_id="item-1", tenant_id=tenant_id)
    assert repo.rollback_config(session, created.id, version=99, tenant_id=tenant_id) is None


def test_delete_config_removes_config_and_revisions(session):
    tenant_id = _make_item(session, "item-1")
    created = repo.create_config(session, _config(widget="map"), item_id="item-1", tenant_id=tenant_id)
    repo.update_config(session, created.id, _config(widget="table"), tenant_id=tenant_id)

    assert repo.delete_config(session, created.id) is True
    assert repo.get_config(session, created.id) is None
    assert repo.list_revisions(session, created.id) == []


def test_delete_missing_config_returns_false(session):
    assert repo.delete_config(session, "nope") is False


def test_get_config_by_item_returns_latest(session):
    tenant_id = _make_item(session, "item-7")
    created = repo.create_config(session, _config(widget="map"), item_id="item-7", tenant_id=tenant_id)
    repo.update_config(session, created.id, _config(widget="table"), tenant_id=tenant_id)
    found = repo.get_config_by_item(session, "item-7")
    assert found is not None
    assert found.id == created.id
    assert found.itemId == "item-7"
    assert found.config.layout.items[0].widget == "table"


def test_get_config_by_item_missing_returns_none(session):
    assert repo.get_config_by_item(session, "nope") is None

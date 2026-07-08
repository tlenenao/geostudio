import io

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.items import repository as items_repo
from app.items import routes as items_routes
from app.items.storage import InMemoryThumbnailStore
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email=None, first_name="", last_name="",
        )
        # Repository functions only flush now; commit here to stand in for
        # "a prior successful request that provisioned this tenant/user".
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _seed_item(client, title="My App") -> str:
    # No linked Config/ConfigRevision needed here: these routes never look up
    # configId (see plan Architecture — app.items must not import app.configs).
    with client.session_factory() as session:
        item = items_repo.create_item(
            session, tenant_id=client.tenant.id, owner_id=client.user.id,
            resource_type="app", title=title,
        )
        # create_item only flushes now; this block bypasses the request
        # boundary, so commit explicitly to persist the seed row.
        session.commit()
        return item.id


def test_get_item_returns_it(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "My App"
    assert body["owner"] == "alice"


def test_get_item_missing_returns_404(client):
    assert client.get("/items/nope").status_code == 404


def test_list_items_default_scope_all(client):
    _seed_item(client, title="One")
    _seed_item(client, title="Two")
    response = client.get("/items")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["pageSize"] == 12


def test_patch_item_updates_title(client):
    item_id = _seed_item(client)
    response = client.patch(f"/items/{item_id}", json={"title": "Renamed"})
    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


def test_patch_item_missing_returns_404(client):
    assert client.patch("/items/nope", json={"title": "x"}).status_code == 404


def test_upload_and_read_thumbnail(client):
    item_id = _seed_item(client)
    store = InMemoryThumbnailStore()
    client.app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: store

    upload = client.post(
        f"/items/{item_id}/thumbnail",
        files={"file": ("thumb.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
    )
    assert upload.status_code == 204

    read = client.get(f"/items/{item_id}/thumbnail")
    assert read.status_code == 200
    assert read.content == b"fake-png-bytes"
    assert read.headers["content-type"] == "image/png"


def test_upload_thumbnail_rejects_non_image(client):
    item_id = _seed_item(client)
    store = InMemoryThumbnailStore()
    client.app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: store

    response = client.post(
        f"/items/{item_id}/thumbnail",
        files={"file": ("doc.pdf", io.BytesIO(b"not-an-image"), "application/pdf")},
    )
    assert response.status_code == 400


def test_read_thumbnail_missing_returns_404(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}/thumbnail")
    assert response.status_code == 404


def _other_user(client, username="mallory"):
    with client.session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session, tenant_id=tenant.id, oidc_sub=f"sub-{username}",
            username=username, email=None, first_name="", last_name="",
        )
        session.commit()
        session.refresh(user)
    return user


def test_get_item_invisible_to_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.get(f"/items/{item_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_patch_item_by_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.patch(f"/items/{item_id}", json={"title": "hijacked"})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_patch_item_by_group_viewer_returns_403(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    item_id = _seed_item(client)
    bob = _other_user(client, "bob")
    with client.session_factory() as session:
        group = Group(id="g1", tenant_id=client.tenant.id, name="Reviewers")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: bob
    try:
        get_response = client.get(f"/items/{item_id}")
        patch_response = client.patch(f"/items/{item_id}", json={"title": "hijacked"})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert get_response.status_code == 200
    assert patch_response.status_code == 403


def test_upload_thumbnail_by_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    store = InMemoryThumbnailStore()
    client.app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: store
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.post(
            f"/items/{item_id}/thumbnail",
            files={"file": ("thumb.png", io.BytesIO(b"x"), "image/png")},
        )
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_get_sharing_defaults_to_private(client):
    item_id = _seed_item(client)
    response = client.get(f"/items/{item_id}/sharing")
    assert response.status_code == 200
    assert response.json() == {"public": False, "groups": []}


def test_put_then_get_sharing_round_trips(client):
    from app.sharing.models import Group

    item_id = _seed_item(client)
    with client.session_factory() as session:
        session.add(Group(id="g1", tenant_id=client.tenant.id, name="Reviewers"))
        session.commit()

    put_response = client.put(
        f"/items/{item_id}/sharing",
        json={"public": True, "groups": [{"groupId": "g1", "role": "viewer"}]},
    )
    assert put_response.status_code == 204

    get_response = client.get(f"/items/{item_id}/sharing")
    assert get_response.status_code == 200
    assert get_response.json() == {
        "public": True, "groups": [{"groupId": "g1", "role": "viewer"}],
    }


def test_put_sharing_with_unknown_group_returns_404(client):
    item_id = _seed_item(client)
    response = client.put(
        f"/items/{item_id}/sharing",
        json={"public": False, "groups": [{"groupId": "nope", "role": "viewer"}]},
    )
    assert response.status_code == 404


def test_put_sharing_writes_audit_log(client):
    from sqlalchemy import select
    from app.audit.models import AuditLog

    item_id = _seed_item(client)
    client.put(f"/items/{item_id}/sharing", json={"public": True, "groups": []})
    with client.session_factory() as session:
        actions = {r.action for r in session.scalars(select(AuditLog)).all()}
        assert "item.share" in actions


def test_get_sharing_invisible_to_non_owner_returns_404(client):
    item_id = _seed_item(client)
    mallory = _other_user(client)
    client.app.dependency_overrides[get_current_user] = lambda: mallory
    try:
        response = client.get(f"/items/{item_id}/sharing")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404


def test_put_sharing_by_group_viewer_returns_403(client):
    from app.sharing.models import Group, GroupMember, ItemShare

    item_id = _seed_item(client)
    bob = _other_user(client, "bob")
    with client.session_factory() as session:
        group = Group(id="g1", tenant_id=client.tenant.id, name="Reviewers")
        session.add(group)
        session.flush()
        session.add(GroupMember(group_id=group.id, user_id=bob.id, tenant_id=client.tenant.id))
        session.add(ItemShare(item_id=item_id, group_id=group.id, tenant_id=client.tenant.id, role="viewer"))
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: bob
    try:
        response = client.put(f"/items/{item_id}/sharing", json={"public": True, "groups": []})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 403

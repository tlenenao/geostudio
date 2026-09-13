# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import repository as attachments_repo
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-attachments-guest-access-secret0"


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {"key-1": b"contenu"}

    def get_object(self, *, Bucket, Key):
        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="incidents",
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="incidents",
            title="incidents",
            description="",
            pk_column="id",
            editable=True,
            is_public=False,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        s.add(col)
        # Flush requis avant create_attachment : Attachment.collection_id a
        # une ForeignKey brute vers collections.id (pas de relationship()
        # ORM), donc l'unit-of-work de SQLAlchemy ne réordonne pas les deux
        # INSERT correctement dans un même flush — sans ce flush explicite,
        # l'INSERT de la pièce jointe précède celui de la collection et lève
        # IntegrityError (FOREIGN KEY constraint failed), écart trouvé en
        # exécutant le texte du brief tel quel (piège CLAUDE.md n°3). Même
        # ordre que test_attachments_read_routes.py, qui commit la
        # collection séparément avant de créer la pièce jointe.
        s.flush()
        attachment = attachments_repo.create_attachment(
            s,
            tenant_id=tenant.id,
            collection_id="incidents",
            fid="1",
            field_key="photos",
            filename="photo.jpg",
            content_type="image/jpeg",
            byte_size=7,
            s3_key="key-1",
            created_by=owner.id,
        )
        s.commit()
        attachment_id = attachment.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    body = {
        "kind": "app",
        "dataSources": [
            {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}}
        ],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    return app, client, token, attachment_id


def test_guest_token_lists_and_downloads_an_attachment(env):
    app, client, token, attachment_id = env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/incidents/items/1/attachments", headers={"X-Share-Link-Token": token}
    )
    assert r.status_code == 200
    assert len(r.json()["attachments"]) == 1

    r2 = client.get(
        f"/v1/collections/incidents/items/1/attachments/{attachment_id}/file",
        headers={"X-Share-Link-Token": token},
    )
    assert r2.status_code == 200
    assert r2.content == b"contenu"

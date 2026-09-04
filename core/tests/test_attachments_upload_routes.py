# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.put_urls: dict[str, str] = {}
        self.heads: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.cors_set = False

    def generate_presigned_url(self, op, *, Params, ExpiresIn):
        key = Params["Key"]
        url = f"https://minio.example/{Params['Bucket']}/{key}"
        self.put_urls[key] = url
        return url

    def create_bucket(self, *, Bucket):
        pass

    def put_bucket_cors(self, *, Bucket, CORSConfiguration):
        self.cors_set = True

    def head_object(self, *, Bucket, Key):
        if Key not in self.heads:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "HeadObject")
        return self.heads[Key]

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)


def _make_client(s3=None):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    if s3 is not None:
        app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    return TestClient(app), Session, tenant, user


@pytest.fixture()
def client():
    s3 = _FakeS3Client()
    api, Session, tenant, user = _make_client(s3)
    return api, Session, tenant, user, s3


def test_presign_returns_an_upload_url_and_tenant_prefixed_key(client):
    api, _Session, tenant, _user, s3 = client
    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["key"].startswith(f"{tenant.id}/col1/f1/")
    assert body["key"] in s3.put_urls
    assert s3.cors_set is True


def test_presign_rejects_undeclared_field_key(client):
    api, *_ = client
    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "not-declared", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 400


def test_presign_requires_write_access(client):
    api, Session, tenant, _user, _s3 = client
    with Session() as session:
        col = session.get(Collection, "col1")
        col.is_public = True
        session.commit()
    with Session() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
    api.app.dependency_overrides[get_current_user] = lambda: stranger

    res = api.post(
        "/collections/col1/items/f1/attachments/presign",
        json={"fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 403


def test_confirm_persists_the_row_after_a_successful_upload(client):
    api, _Session, tenant, user, s3 = client
    key = f"{tenant.id}/col1/f1/abc-a.jpg"
    s3.heads[key] = {"ContentLength": 512}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={"key": key, "fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["filename"] == "a.jpg"
    assert body["byteSize"] == 512
    assert body["fieldKey"] == "photos"


def test_confirm_rejects_a_key_outside_the_caller_s_tenant_prefix(client):
    api, *_ = client
    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": "other-tenant/col1/f1/abc-a.jpg",
            "fieldKey": "photos",
            "filename": "a.jpg",
            "contentType": "image/jpeg",
        },
    )
    assert res.status_code == 400


def test_confirm_rejects_and_deletes_an_oversized_object(client):
    api, _Session, tenant, _user, s3 = client
    key = f"{tenant.id}/col1/f1/abc-big.bin"
    s3.heads[key] = {"ContentLength": attachments_routes.MAX_ATTACHMENT_BYTES + 1}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": key,
            "fieldKey": "photos",
            "filename": "big.bin",
            "contentType": "application/octet-stream",
        },
    )
    assert res.status_code == 400
    assert key in s3.deleted


def test_confirm_returns_404_when_the_object_was_never_uploaded(client):
    api, _Session, tenant, _user, _s3 = client
    key = f"{tenant.id}/col1/f1/never-uploaded.jpg"
    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={"key": key, "fieldKey": "photos", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert res.status_code == 404

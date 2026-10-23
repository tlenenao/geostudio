# SPDX-License-Identifier: Apache-2.0
"""L8 T3 : confirm de pièce jointe idempotent, fid vérifié, unicité s3_key, types par contenu
(PostGIS réel : le contrôle d'existence passe par la vraie porte de lecture de features)."""

import io

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

OP = "22222222-2222-4222-8222-222222222222"
JPEG = b"\xff\xd8\xff\xe0" + bytes(28)
MP3 = b"ID3\x04\x00" + bytes(27)
EXE = b"MZ\x90\x00" + bytes(28)


class _S3:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    def put(self, key, body, ctype="application/octet-stream"):
        self.objects[key] = (body, ctype)

    def _get(self, key, op):
        if key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, op)
        return self.objects[key]

    def head_object(self, *, Bucket, Key):
        body, ctype = self._get(Key, "HeadObject")
        return {"ContentLength": len(body), "ContentType": ctype}

    def get_object(self, *, Bucket, Key, Range=None):
        return {"Body": io.BytesIO(self._get(Key, "GetObject")[0][:32])}

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def __getattr__(self, _name):
        return lambda *a, **k: {}


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_att"))
        conn.execute(
            text(
                "CREATE TABLE demo_att (id serial PRIMARY KEY, titre text, "
                "geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    s3 = _S3()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    c = TestClient(app)
    r0 = c.post("/v1/collections", json={"tableName": "demo_att"})
    assert r0.status_code == 201, r0.text
    r = c.patch(
        "/v1/collections/demo_att",
        json={
            "attachmentFields": [
                {"key": "photo", "label": "Photo", "kind": "image"},
                {"key": "son", "label": "Son", "kind": "audio"},
                {"key": "any", "label": "Pièce"},
            ]
        },
    )
    assert r.status_code == 200, r.text
    fid = c.post(
        "/v1/collections/demo_att/items",
        json={"type": "Feature", "properties": {"titre": "a"}, "geometry": None},
    ).json()["id"]
    yield c, s3, tenant_id, fid, pg_engine
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_att"))
        conn.execute(
            text(
                "TRUNCATE attachments, collection_shares, collections, audit_log, users, "
                "tenants CASCADE"
            )
        )


def _confirm(c, tenant_id, fid, key_suffix, field="photo", name="a.jpg", ctype="image/jpeg", **h):
    key = f"{tenant_id}/demo_att/{fid}/{key_suffix}"
    return key, lambda: c.post(
        f"/v1/collections/demo_att/items/{fid}/attachments",
        json={"key": key, "fieldKey": field, "filename": name, "contentType": ctype},
        headers=h,
    )


def _count(engine):
    with engine.connect() as conn:
        return conn.scalar(text("SELECT count(*) FROM attachments"))


def test_confirm_replay_with_same_key_returns_the_same_row(env):
    c, s3, tenant_id, fid, engine = env
    key, post = _confirm(c, tenant_id, fid, "abc-a.jpg", **{"Idempotency-Key": OP})
    s3.put(key, JPEG, "image/jpeg")
    first = post()
    assert first.status_code == 201
    again = post()
    assert again.status_code == 200
    assert again.headers["Idempotent-Replay"] == "true"
    assert again.json()["id"] == first.json()["id"]
    assert _count(engine) == 1


def test_second_confirm_of_the_same_s3_key_without_header_is_409(env):
    c, s3, tenant_id, fid, engine = env
    key, post = _confirm(c, tenant_id, fid, "abc-a.jpg")
    s3.put(key, JPEG, "image/jpeg")
    assert post().status_code == 201
    assert post().status_code == 409
    assert _count(engine) == 1


def test_unknown_fid_is_404_for_presign_and_confirm(env):
    c, s3, tenant_id, _fid, engine = env
    key, post = _confirm(c, tenant_id, 9999, "abc-a.jpg")
    s3.put(key, JPEG, "image/jpeg")
    assert post().status_code == 404
    presign = c.post(
        "/v1/collections/demo_att/items/9999/attachments/presign",
        json={"size": 10, "fieldKey": "photo", "filename": "a.jpg", "contentType": "image/jpeg"},
    )
    assert presign.status_code == 404
    assert _count(engine) == 0


def test_content_type_comes_from_the_object_not_the_request(env):
    c, s3, tenant_id, fid, _e = env
    key, post = _confirm(c, tenant_id, fid, "abc-a.jpg", ctype="image/png")
    s3.put(key, JPEG, "image/jpeg")
    res = post()
    assert res.status_code == 201
    assert res.json()["contentType"] == "image/jpeg"


def test_audio_field_accepts_mp3_and_image_field_refuses_it(env):
    c, s3, tenant_id, fid, _e = env
    key, post = _confirm(
        c, tenant_id, fid, "abc-s.mp3", field="son", name="s.mp3", ctype="audio/mpeg"
    )
    s3.put(key, MP3, "audio/mpeg")
    assert post().status_code == 201
    key2, post2 = _confirm(
        c, tenant_id, fid, "abc-t.mp3", field="photo", name="t.mp3", ctype="audio/mpeg"
    )
    s3.put(key2, MP3, "audio/mpeg")
    assert post2().status_code == 415
    assert key2 in s3.deleted


def test_disguised_executable_is_415_even_on_an_untyped_field(env):
    c, s3, tenant_id, fid, engine = env
    key, post = _confirm(
        c, tenant_id, fid, "abc-x.dat", field="any", name="x.dat", ctype="image/png"
    )
    s3.put(key, EXE, "image/png")
    assert post().status_code == 415
    assert key in s3.deleted
    assert _count(engine) == 0


def test_untyped_field_still_accepts_other_documents(env):
    c, s3, tenant_id, fid, _e = env
    key, post = _confirm(
        c, tenant_id, fid, "abc-d.csv", field="any", name="d.csv", ctype="text/csv"
    )
    s3.put(key, b"a,b\n1,2\n", "text/csv")
    res = post()
    assert res.status_code == 201
    assert res.json()["contentType"] == "text/csv"

# SPDX-License-Identifier: Apache-2.0
"""Bibliothèque d'icônes personnalisées, tenant-scoped (SP-27 §3.4, D7)."""

import uuid

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
LEGIT_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    b'viewBox="0 0 24 24"><path d="M4 4 L20 20"/></svg>'
)
HOSTILE_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" onload="alert(1)">'
    b'<script>alert(2)</script><path d="M4 4"/></svg>'
)
# Prologue d'export SVG 1.1 par défaut d'Adobe Illustrator : commentaire de
# générateur + DOCTYPE PUBLIC. Mesuré : accepté (forbid_dtd=False), et la DTD
# externe n'est jamais récupérée sur le réseau.
ILLUSTRATOR_SVG = (
    b'<?xml version="1.0" encoding="utf-8"?>\n'
    b"<!-- Generator: Adobe Illustrator 27.0 -->\n"
    b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" '
    b'"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n'
    b'<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    b'<path d="M0 0 L4 4"/></svg>'
)


class _FakeS3Client:
    """Assez de S3 pour ce module : put, get, delete. Volontairement distinct du
    _FakeS3Client de test_tileset3d_routes.py, qui n'implémente ni put_object ni
    delete_object (multipart uniquement). Pas de generate_presigned_url ni de
    head_object : D7 supprime la présignation, et le cœur connaît la taille des
    octets qu'il écrit lui-même."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "nope"}}, "GetObject")

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(self.objects[Key])}

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.objects[Key] = Body

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    fake_s3 = _FakeS3Client()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    client = TestClient(app)
    return app, client, Session, tenant, alice, fake_s3


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _second_tenant_user(Session):
    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="o",
            username="other",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        return other


def _upload(
    client,
    payload=PNG_BYTES,
    *,
    filename="logo.png",
    content_type="image/png",
    title="Logo",
    category="generic",
):
    """Un seul POST multipart : le cœur reçoit les octets (D7)."""
    return client.post(
        "/map-icons",
        files={"file": (filename, payload, content_type)},
        data={"title": title, "category": category},
    )


def test_upload_then_list_then_delete(env):
    app, client, _Session, tenant, alice, fake_s3 = env
    _as(app, alice)
    created = _upload(client)
    assert created.status_code == 201
    icon_id = created.json()["id"]

    listed = client.get("/map-icons")
    assert [i["id"] for i in listed.json()] == [icon_id]

    # La clé S3 est CHOISIE PAR LE CŒUR et préfixée du tenant : le client n'en
    # a jamais eu la main (D7). Un seul objet écrit.
    assert len(fake_s3.objects) == 1
    key = next(iter(fake_s3.objects))
    assert key.startswith(f"{tenant.id}/")
    assert key.endswith("logo.png")

    deleted = client.delete(f"/map-icons/{icon_id}")
    assert deleted.status_code == 204
    assert client.get("/map-icons").json() == []
    assert fake_s3.deleted == [key]


def test_upload_accepts_png_and_svg_and_refuses_everything_else(env):
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    assert _upload(client, PNG_BYTES, filename="a.png", content_type="image/png").status_code == 201
    assert (
        _upload(client, LEGIT_SVG, filename="a.svg", content_type="image/svg+xml").status_code
        == 201
    )
    for content_type in ("text/html", "image/gif", "application/octet-stream"):
        response = _upload(client, PNG_BYTES, filename="a.bin", content_type=content_type)
        assert response.status_code == 422, content_type


def test_upload_refuses_an_oversized_file_without_reading_it_whole(env):
    """MAX_ICON_BYTES = 200 000. La route lit par morceaux et abandonne dès le
    dépassement : rien n'est écrit dans S3, rien n'est enregistré en base."""
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    response = _upload(client, b"\x89PNG\r\n\x1a\n" + b"0" * 300_000, filename="big.png")
    assert response.status_code == 413
    assert fake_s3.objects == {}
    assert client.get("/map-icons").json() == []


def test_upload_refuses_bytes_that_contradict_the_declared_type(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    # Déclaré PNG dans l'en-tête de partie, réellement du SVG.
    response = _upload(client, LEGIT_SVG, filename="fake.png", content_type="image/png")
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["errors"][0]["code"] == "content_type_mismatch"
    assert fake_s3.objects == {}


def test_upload_refuses_a_payload_that_is_neither_png_nor_svg(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    response = _upload(client, b"GIF89a" + b"0" * 32, filename="x.png", content_type="image/png")
    assert response.status_code == 400
    assert fake_s3.objects == {}


def test_an_svg_is_sanitized_before_being_stored_and_served(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    created = _upload(client, HOSTILE_SVG, filename="logo.svg", content_type="image/svg+xml")
    assert created.status_code == 201
    # Les octets STOCKÉS sont la version assainie : la garde est à l'écriture,
    # la lecture ne réassainit pas. Les octets fournis par le client ne sont
    # JAMAIS écrits (D7) — il n'y a qu'un objet, et c'est l'assaini.
    assert len(fake_s3.objects) == 1
    stored = next(iter(fake_s3.objects.values()))
    assert b"script" not in stored
    assert b"onload" not in stored
    assert b'd="M4 4"' in stored

    served = client.get(f"/map-icons/{created.json()['id']}/file")
    assert served.status_code == 200
    assert served.content == stored
    assert served.headers["content-type"].startswith("image/svg+xml")
    assert served.headers["x-content-type-options"] == "nosniff"


def test_an_svg_emptied_by_sanitization_is_refused_and_nothing_is_stored(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    response = _upload(
        client,
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        b"<script>alert(1)</script></svg>",
        filename="vide.svg",
        content_type="image/svg+xml",
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["errors"][0]["code"] == "svg_no_graphics"
    # Contrat explicite de D4+D7 : rien en base, et RIEN dans S3 — l'écriture
    # n'a lieu qu'après un assainissement réussi.
    assert client.get("/map-icons").json() == []
    assert fake_s3.objects == {}


def test_an_svg_declaring_an_entity_is_refused_with_an_actionable_code(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    response = _upload(
        client,
        b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">&a;</svg>',
        filename="xxe.svg",
        content_type="image/svg+xml",
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "svg_entities_forbidden"
    assert fake_s3.objects == {}


def test_an_illustrator_svg_with_a_bare_doctype_is_accepted(env):
    """Mesuré : forbid_dtd=False + forbid_entities=True bloque les trois classes
    d'attaque (bombe d'entités, entité externe, DTD externe réellement
    récupérée) sans refuser la classe de fichiers la plus courante du monde
    réel. Sans ce test, un durcissement futur casserait tous les exports
    Illustrator en silence."""
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    assert (
        _upload(
            client, ILLUSTRATOR_SVG, filename="ai.svg", content_type="image/svg+xml"
        ).status_code
        == 201
    )


def test_a_valid_png_is_stored_byte_for_byte(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    assert _upload(client, PNG_BYTES).status_code == 201
    # Aucun assainissement sur le chemin PNG : les octets sont écrits tels quels.
    assert next(iter(fake_s3.objects.values())) == PNG_BYTES


def test_title_and_category_are_length_bounded(env):
    """Précédent du dépôt : app/tileset3d/schemas.py:5-7
    (Field(min_length=1, max_length=255)). Sans ça, un titre vide ou de 10 Mo
    passe (constat Mineur 19)."""
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    assert _upload(client, title="").status_code == 422
    assert _upload(client, title="x" * 256).status_code == 422
    assert _upload(client, category="").status_code == 422


def test_list_and_read_are_tenant_scoped(env):
    app, client, Session, _tenant, alice, _s3 = env
    _as(app, alice)
    icon_id = _upload(client, title="Mine").json()["id"]

    other = _second_tenant_user(Session)
    _as(app, other)
    assert client.get("/map-icons").json() == []
    assert client.get(f"/map-icons/{icon_id}/file").status_code == 404
    assert client.delete(f"/map-icons/{icon_id}").status_code == 404


def test_read_file_serves_the_bytes_with_hardened_headers(env):
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    icon_id = _upload(client, PNG_BYTES, filename="servi.png", title="Servi").json()["id"]

    response = client.get(f"/map-icons/{icon_id}/file")
    assert response.status_code == 200
    assert response.content == PNG_BYTES
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["x-content-type-options"] == "nosniff"
    # `filename=` est la convention du dépôt : quatre précédents, tous en
    # `attachment; filename="…"` (features/routes.py:331 et :417,
    # harvest/routes.py:444 et :542). Sans lui, le navigateur dérive le nom
    # du dernier segment d'URL, soit « file ».
    assert response.headers["content-disposition"].startswith("attachment; filename=")
    assert response.headers["cache-control"] == "private, max-age=3600"


def test_read_file_is_404_when_the_s3_object_vanished(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    icon_id = _upload(client).json()["id"]
    fake_s3.objects.clear()
    assert client.get(f"/map-icons/{icon_id}/file").status_code == 404


def test_create_and_delete_write_audit_entries(env):
    app, client, Session, _tenant, alice, _s3 = env
    _as(app, alice)
    icon_id = _upload(client, title="Audit").json()["id"]
    client.delete(f"/map-icons/{icon_id}")

    with Session() as s:
        actions = sorted(
            s.scalars(select(AuditLog.action).where(AuditLog.object_id == icon_id)).all()
        )
    assert actions == ["mapicon.create", "mapicon.delete"]


def test_delete_of_a_missing_icon_is_404(env):
    app, client, _Session, _tenant, alice, _s3 = env
    _as(app, alice)
    assert client.delete("/map-icons/does-not-exist").status_code == 404


def test_a_failing_s3_delete_does_not_lose_the_database_delete(env):
    app, client, _Session, _tenant, alice, fake_s3 = env
    _as(app, alice)
    icon_id = _upload(client, title="Orphan").json()["id"]

    def boom(Bucket, Key):  # noqa: N803
        raise ClientError({"Error": {"Code": "500", "Message": "nope"}}, "DeleteObject")

    fake_s3.delete_object = boom
    assert client.delete(f"/map-icons/{icon_id}").status_code == 204
    assert client.get("/map-icons").json() == []


def test_map_icons_cannot_be_registered_as_a_business_collection(env):
    """core_table_names() est la denylist du registre de collections : sans
    l'import paresseux dans app/db.py, un admin pourrait exposer map_icons en
    OGC API Features (constat 2.23 du pré-vol)."""
    from app.db import core_table_names

    assert "map_icons" in core_table_names()

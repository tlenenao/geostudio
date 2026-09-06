# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import repository as attachments_repo
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import CollectionShare, Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "GetObject")

        class _Body:
            def __init__(self, data):
                self._data = data

            def read(self):
                return self._data

        return {"Body": _Body(self.objects[Key])}

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)

    def head_object(self, *, Bucket, Key):
        # Ajouté pour test_accented_french_filename_survives_upload_to_download_intact
        # (revue finale, Important #2) : seul consommateur de confirm_attachment
        # (donc de head_object) dans ce fichier — les autres tests écrivent
        # directement via attachments_repo, jamais via la route HTTP de
        # confirmation.
        if Key not in self.objects:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        owner = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        reader = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        col = Collection(
            id="col1",
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="col1",
            title="Col 1",
            description="",
            pk_column="id",
            editable=True,
            attachment_fields=[{"key": "photos", "label": "Photos"}],
        )
        setup_session.add(col)
        setup_session.commit()
        # Le brief ne donnait à `reader` aucun accès explicite à `col1` — sans
        # ce partage, `get_readable_collection` renvoie 404 pour n'importe
        # quelle action (lecture ou écriture) pour ce non-propriétaire sur une
        # collection non publique (app/sharing/authorization.py::decide) :
        # ni "visible à un lecteur autorisé" (test ci-dessous) ni "403 (pas
        # 404) au refus d'écriture" n'étaient atteignables. Rôle "viewer"
        # (lecture seule, pas "editor") — patron identique à
        # tests/test_collections_authorization.py.
        group = Group(
            id=uuid.uuid4().hex, tenant_id=tenant.id, name="lecteurs", created_by=owner.id
        )
        setup_session.add(group)
        setup_session.flush()
        setup_session.add(GroupMember(group_id=group.id, user_id=reader.id, tenant_id=tenant.id))
        setup_session.add(
            CollectionShare(
                collection_id="col1", group_id=group.id, tenant_id=tenant.id, role="viewer"
            )
        )
        setup_session.commit()
        attachment = attachments_repo.create_attachment(
            setup_session,
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=3,
            s3_key=f"{tenant.id}/col1/f1/abc-a.jpg",
            created_by=owner.id,
        )
        setup_session.commit()
        attachment_id = attachment.id
        s3_key = attachment.s3_key

    s3 = _FakeS3Client()
    s3.objects[s3_key] = b"jpg"

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    api = TestClient(app)
    return api, Session, tenant, owner, reader, attachment_id, s3


def _authenticate_as(api: TestClient, user) -> None:
    """`GET .../attachments` et `GET .../attachments/{id}/file` dépendent de
    `get_current_user_optional`, pas de `get_current_user` — les deux
    fonctions sont des callables FastAPI distincts pour `dependency_overrides`
    (celui-ci n'intercepte que les sous-dépendances déclarées via `Depends`,
    jamais un appel Python direct comme celui que
    `get_current_user_optional` fait vers `get_current_user` en son sein
    quand un en-tête `Bearer` est présent — absent ici, `TestClient` n'en
    envoie jamais). Sans ce second override, ces deux routes résolvent
    toujours `user=None` (anonyme), quel que soit l'override posé sur
    `get_current_user` seul. Même idiome que
    `tests/test_features_routes_read.py`."""
    api.app.dependency_overrides[get_current_user] = lambda: user
    api.app.dependency_overrides[get_current_user_optional] = lambda: user


def test_list_visible_to_the_owner(env):
    api, _Session, _tenant, owner, _reader, _attachment_id, _s3 = env
    _authenticate_as(api, owner)
    res = api.get("/v1/collections/col1/items/f1/attachments")
    assert res.status_code == 200
    assert res.json()["attachments"][0]["filename"] == "a.jpg"


def test_file_visible_to_another_reader_with_read_access(env):
    """Preuve de sortie littérale du chantier 4.12."""
    api, _Session, _tenant, _owner, reader, attachment_id, _s3 = env
    _authenticate_as(api, reader)
    res = api.get(f"/v1/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert res.status_code == 200
    assert res.content == b"jpg"
    assert res.headers["content-type"].startswith("image/jpeg")
    assert 'filename="a.jpg"' in res.headers["content-disposition"]


def test_file_invisible_to_a_stranger_from_another_tenant(env):
    api, Session, _tenant, _owner, _reader, attachment_id, _s3 = env
    with Session() as session:
        other_tenant = get_or_create_default_tenant(session)
        stranger = get_or_create_user(
            session,
            tenant_id=other_tenant.id,
            oidc_sub="c",
            username="carol",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()
    _authenticate_as(api, stranger)
    res = api.get(f"/v1/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert res.status_code == 404


def test_list_and_file_are_readable_anonymously_on_a_public_collection(env):
    api, Session, tenant, owner, _reader, attachment_id, _s3 = env
    with Session() as session:
        col = session.get(Collection, "col1")
        col.is_public = True
        session.commit()
    api.app.dependency_overrides.pop(get_current_user, None)
    api.app.dependency_overrides.pop(get_current_user_optional, None)

    list_res = api.get("/v1/collections/col1/items/f1/attachments")
    assert list_res.status_code == 200
    # Renforcement REV-077/F-tests-05 : une liste vide passait avant ce
    # correctif (seul le code 200 était vérifié) — même patron que
    # test_list_visible_to_the_owner (ligne 166) et
    # test_file_visible_to_another_reader_with_read_access (lignes 175-177).
    assert list_res.json()["attachments"][0]["filename"] == "a.jpg"

    file_res = api.get(f"/v1/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert file_res.status_code == 200
    assert file_res.content == b"jpg"
    assert file_res.headers["content-type"].startswith("image/jpeg")


def test_delete_removes_row_and_object_and_requires_write_access(env):
    api, _Session, _tenant, owner, reader, attachment_id, s3 = env
    _authenticate_as(api, reader)
    forbidden = api.delete(f"/v1/collections/col1/items/f1/attachments/{attachment_id}")
    assert forbidden.status_code == 403

    _authenticate_as(api, owner)
    ok = api.delete(f"/v1/collections/col1/items/f1/attachments/{attachment_id}")
    assert ok.status_code == 204
    assert len(s3.deleted) == 1

    missing = api.get("/v1/collections/col1/items/f1/attachments")
    assert missing.json()["attachments"] == []


def test_file_download_does_not_crash_on_a_non_ascii_filename_already_in_db(env):
    """Preuve directe du défaut I2 (revue finale) : Content-Disposition
    plantait en UnicodeEncodeError sur un nom hors latin-1 déjà en base
    (avant assainissement à la confirmation, ou pour une ligne existante)."""
    api, Session, tenant, owner, _reader, _attachment_id, s3 = env
    with Session() as session:
        a = attachments_repo.create_attachment(
            session,
            tenant_id=tenant.id,
            collection_id="col1",
            fid="f1",
            field_key="photos",
            filename="文件.png",
            content_type="image/png",
            byte_size=3,
            s3_key=f"{tenant.id}/col1/f1/other-非ascii.png",
            created_by=owner.id,
        )
        session.commit()
        attachment_id = a.id
    s3.objects[f"{tenant.id}/col1/f1/other-非ascii.png"] = b"png"
    _authenticate_as(api, owner)
    res = api.get(f"/v1/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert res.status_code == 200


def test_accented_french_filename_survives_upload_to_download_intact(env):
    """Preuve directe du correctif Important #2 (revue finale de branche,
    Task 21) : un nom accentué français, qui fonctionnait déjà avant Task 21
    (encodable en latin-1, ne cassait jamais Content-Disposition), ne doit
    plus être mutilé par la sanitization du nom stocké — corrigée pour ne
    plus s'appliquer qu'au repli ASCII de l'en-tête RFC 6266, jamais au nom
    persisté. Bout en bout : confirm_attachment (stockage) → GET .../file
    (en-tête)."""
    from urllib.parse import quote

    api, Session, tenant, owner, _reader, _attachment_id, s3 = env
    filename = "Relevé été.pdf"
    key = f"{tenant.id}/col1/f1/abc-releve.pdf"
    # Simule l'upload S3 déjà effectué (via le PUT présigné, hors périmètre
    # ici) avant que confirm_attachment ne fasse son head_object.
    s3.objects[key] = b"%PDF"
    _authenticate_as(api, owner)
    confirm_res = api.post(
        "/v1/collections/col1/items/f1/attachments",
        json={
            "key": key,
            "fieldKey": "photos",
            "filename": filename,
            "contentType": "application/pdf",
        },
    )
    assert confirm_res.status_code == 201
    # Stockage : le nom brut n'est jamais mutilé (Important #2).
    assert confirm_res.json()["filename"] == filename
    attachment_id = confirm_res.json()["id"]

    file_res = api.get(f"/v1/collections/col1/items/f1/attachments/{attachment_id}/file")
    assert file_res.status_code == 200
    disposition = file_res.headers["content-disposition"]
    # Repli ASCII non vide (compris par un client qui ignore filename*) —
    # calculé, pas deviné : _SAFE_FILENAME remplace chaque run contigu de
    # caractères non-ASCII par un seul "_" ("é ét" -> "_t_", pas "__t_").
    assert 'filename="Relev_t_.pdf"' in disposition
    # Valeur exacte, RFC 6266, comprise par tous les navigateurs modernes.
    assert f"filename*=UTF-8''{quote(filename, safe='')}" in disposition

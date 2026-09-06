# SPDX-License-Identifier: Apache-2.0
import io
import json
import struct
import zipfile

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import routes as tileset3d_routes
from app.users.repository import get_or_create_user, set_user_role


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self._next_upload_id = 0

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def create_multipart_upload(self, Bucket, Key):  # noqa: N803
        self._next_upload_id += 1
        return {"UploadId": f"mpu-{self._next_upload_id}"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return (
            f"https://minio.test/{Params['Bucket']}/{Params['Key']}?part={Params.get('PartNumber')}"
        )

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):  # noqa: N803
        self.objects[Key] = b"".join(b"part" for _ in MultipartUpload["Parts"])

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")
        data = self.objects[Key]
        if Range is not None:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start) : int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(data)}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
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
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[tileset3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: deferred.append((job_id, tenant_id))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3


def _demote_alice_to_reader(env) -> None:
    # `get_current_user` est surchargé par `lambda: alice` (patron d'origine
    # de la fixture `env` de ce fichier) — le MÊME objet Python à chaque
    # requête, jamais re-résolu depuis la base. On mute donc son role_id en
    # mémoire après avoir committé le changement en base, sans quoi
    # require_privilege lirait encore l'ancien role_id (Créateur).
    client, Session, tenant, alice, *_ = env
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert roles["reader"].privileges == []
        reader_role_id = roles["reader"].id
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=alice.id,
            role_id=reader_role_id,
            role_slug="reader",
        )
        s.commit()
    alice.role_id = reader_role_id


def test_create_upload_refuses_a_reader_with_no_privilege(env):
    # SP-42, revue des lots de correctifs 2/3bis (point 1, Critical) :
    # create_tileset3d_upload ne consultait jusqu'ici que get_current_user —
    # aucun privilège — alors que le job qu'il amorce aboutit (via
    # complete_tileset3d_upload -> convert_tileset3d_task) à
    # configs_repo.create_config(kind="tileset3d"), mappé sur
    # catalog.manage. Un rôle « Lecteur » (0 privilège) obtenait donc 201
    # ici, exactement le trou fermé sur POST /configs par eafb02cc.
    client, *_ = env
    _demote_alice_to_reader(env)
    r = client.post("/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"})
    assert r.status_code == 403, r.text


def test_complete_upload_refuses_a_reader_with_no_privilege(env):
    # Même point, défense en profondeur sur complete_tileset3d_upload — le
    # seul appel qui défère réellement convert_tileset3d_task (celui qui
    # crée la config) : le job est créé pendant qu'alice détient encore le
    # privilège (rôle Créateur par défaut), puis elle est rétrogradée avant
    # d'appeler /complete, pour isoler le garde de cette route de celui de
    # la création ci-dessus.
    client, *_ = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    _demote_alice_to_reader(env)
    r = client.post(
        f"/v1/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": '"abc"'}]},
    )
    assert r.status_code == 403, r.text


def test_create_upload_returns_job_id(env):
    client, *_ = env
    r = client.post("/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"})
    assert r.status_code == 201, r.text
    assert "jobId" in r.json()


def test_presign_part_returns_upload_url(env):
    client, *_ = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    r = client.post(f"/v1/tileset3d/uploads/{job_id}/parts/1/presign")
    assert r.status_code == 200, r.text
    assert "uploadUrl" in r.json()


def test_presign_part_refuses_a_reader_with_no_privilege(env):
    # REV-002 : cette route ne consultait jusqu'ici que get_current_user —
    # aucun privilège — alors que create_tileset3d_upload/
    # complete_tileset3d_upload exigent déjà tous deux ce même privilège. Un
    # Lecteur pouvait donc pousser des octets réels dans un job existant
    # (upload_part) sans jamais pouvoir compléter l'upload.
    client, *_ = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    _demote_alice_to_reader(env)
    r = client.post(f"/v1/tileset3d/uploads/{job_id}/parts/1/presign")
    assert r.status_code == 403, r.text


def test_presign_part_404_for_a_job_owned_by_another_user(env):
    # REV-002 : aucune vérification que l'appelant est le créateur du job —
    # un utilisateur du même tenant pouvait obtenir une URL presignée pour
    # pousser des octets dans le job multipart d'un autre utilisateur.
    client, Session, tenant, _alice, *_ = env
    with Session() as s:
        bob = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    app = client.app
    app.dependency_overrides[get_current_user] = lambda: bob
    r = client.post(f"/v1/tileset3d/uploads/{job_id}/parts/1/presign")
    assert r.status_code == 404, r.text


def test_presign_part_404_for_unknown_job(env):
    client, *_ = env
    r = client.post("/v1/tileset3d/uploads/does-not-exist/parts/1/presign")
    assert r.status_code == 404


def test_presign_part_rejects_part_number_below_one(env):
    client, *_ = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    r = client.post(f"/v1/tileset3d/uploads/{job_id}/parts/0/presign")
    assert r.status_code == 422


def test_complete_upload_marks_finalizing_and_defers_task(env):
    client, Session, tenant, alice, deferred, _fake_s3 = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    r = client.post(
        f"/v1/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": '"abc"'}]},
    )
    assert r.status_code == 204, r.text
    assert deferred == [(job_id, tenant.id)]
    status = client.get(f"/v1/tileset3d/uploads/{job_id}").json()
    assert status["status"] == "finalizing"


def test_complete_upload_rejects_empty_parts_list(env):
    client, *_ = env
    job_id = client.post(
        "/v1/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}
    ).json()["jobId"]
    r = client.post(f"/v1/tileset3d/uploads/{job_id}/complete", json={"parts": []})
    assert r.status_code == 422


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    r = client.get("/v1/tileset3d/uploads/does-not-exist")
    assert r.status_code == 404


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


def _seed_hosted_tileset_item(session, *, tenant_id, owner_id, fake_s3, key="tenant/x/city.zip"):
    fake_s3.objects[key] = _valid_zip_bytes()
    from app.items import repository as items_repo

    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="tileset3d",
        title="Ville",
    )
    config = BuilderConfig(
        kind="tileset3d",
        tileset3d=Tileset3DPayload(
            sourceKey=key, tilesetJsonPath="tileset.json", totalBytes=100, entryCount=2
        ),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_read_tileset3d_entry_returns_tileset_json(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    r = client.get(f"/v1/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert json.loads(r.content)["asset"]["version"] == "1.0"


def test_read_tileset3d_entry_returns_tile_binary(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    r = client.get(f"/v1/tileset3d/{item_id}/tiles/0.b3dm")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.content == b"\x00" * 16


def test_read_tileset3d_entry_sets_content_length_to_the_entry_size(env):
    """Revue finale, round 3, Important : Content-Length permet à tout client/
    proxy HTTP de détecter un corps tronqué (corruption CRC détectée en cours
    de flux) comme un short-read propre plutôt que d'accepter silencieusement
    une réponse incomplète. Doit correspondre exactement à la taille réelle de
    l'entrée décompressée."""
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    r = client.get(f"/v1/tileset3d/{item_id}/tiles/0.b3dm")
    assert r.status_code == 200
    assert r.headers["content-length"] == str(len(b"\x00" * 16))
    assert r.headers["content-length"] == str(len(r.content))


def test_read_tileset3d_entry_404_for_missing_entry(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    r = client.get(f"/v1/tileset3d/{item_id}/does-not-exist.b3dm")
    assert r.status_code == 404
    # Détecté avant que le flux ne commence : corps JSON d'erreur complet, pas
    # une réponse 200 tronquée (revue finale, C2 round 2).
    assert r.json()["detail"] == "entry not found"


def test_read_tileset3d_entry_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/v1/tileset3d/does-not-exist/tileset.json")
    assert r.status_code == 404


def _zip_with_compressible_entry(size: int) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/big.b3dm", b"\x00" * size)
    return buf.getvalue()


def test_read_tileset3d_entry_413_when_the_decompressed_entry_exceeds_the_proxy_cap(
    env, monkeypatch
):
    """Revue finale de branche, C2 round 2 : le plafond de SERVICE est une
    variable distincte de celle de la VALIDATION. L'entrée de 8 Mio construite
    ici passerait la validation (CORE_TILESET3D_MAX_ENTRY_BYTES vaut 2 Gio par
    défaut, et le zip qui la contient fait ~65 Kio) : c'est bien le plafond de
    service, plus bas, qui la refuse — sinon la branche 413 était morte."""
    client, Session, tenant, alice, _deferred, fake_s3 = env
    monkeypatch.setenv("CORE_TILESET3D_MAX_PROXY_READ_BYTES", "1024")
    # Aucune surcharge de CORE_TILESET3D_MAX_ENTRY_BYTES : le défaut de
    # validation (2 Gio) reste actif et laisserait passer cette entrée.
    monkeypatch.delenv("CORE_TILESET3D_MAX_ENTRY_BYTES", raising=False)
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    zip_bytes = _zip_with_compressible_entry(8 * 1024 * 1024)
    assert len(zip_bytes) < 128 * 1024  # zip minuscule, entrée honnêtement déclarée
    fake_s3.objects["tenant/x/city.zip"] = zip_bytes

    r = client.get(f"/v1/tileset3d/{item_id}/tiles/big.b3dm")

    assert r.status_code == 413, r.text
    assert r.json()["detail"] == "entry too large"
    # Une entrée sous le plafond passe toujours par le même chemin.
    assert client.get(f"/v1/tileset3d/{item_id}/tileset.json").status_code == 200


def test_read_tileset3d_entry_413_is_independent_of_the_validation_cap(env, monkeypatch):
    """Le plafond de validation, même très généreux, ne relâche pas le plafond
    de service : preuve que les deux variables sont bien découplées."""
    client, Session, tenant, alice, _deferred, fake_s3 = env
    monkeypatch.setenv("CORE_TILESET3D_MAX_ENTRY_BYTES", str(2 * 1024 * 1024 * 1024))
    monkeypatch.setenv("CORE_TILESET3D_MAX_PROXY_READ_BYTES", "1024")
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    fake_s3.objects["tenant/x/city.zip"] = _zip_with_compressible_entry(8 * 1024 * 1024)

    assert client.get(f"/v1/tileset3d/{item_id}/tiles/big.b3dm").status_code == 413


def test_read_tileset3d_entry_streams_a_multi_chunk_entry_byte_for_byte(env, monkeypatch):
    """Le passage en StreamingResponse ne doit pas altérer le corps : une
    entrée plus grosse qu'une tranche de lecture (donc réellement servie en
    plusieurs morceaux) doit ressortir octet pour octet."""
    client, Session, tenant, alice, _deferred, fake_s3 = env
    monkeypatch.setattr(tileset3d_routes, "_READ_CHUNK_BYTES", 4096)
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    body = bytes(range(256)) * 400  # 102 400 octets, 25 tranches
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/multi.b3dm", body)
    fake_s3.objects["tenant/x/city.zip"] = buf.getvalue()

    r = client.get(f"/v1/tileset3d/{item_id}/tiles/multi.b3dm")

    assert r.status_code == 200, r.text
    assert r.content == body


def _zip_with_understated_entry_size() -> bytes:
    """Zip dont le répertoire central ment sur la taille décompressée d'une
    entrée (8 Mio réels annoncés comme 10 octets). zipfile borne sa
    décompression sur cette métadonnée puis échoue le contrôle CRC —
    BadZipFile, que l'ancien `except KeyError` seul ne rattrapait pas."""
    raw = bytearray(_zip_with_compressible_entry(8 * 1024 * 1024))
    # En-tête de répertoire central : sig(4) ver(2) verneed(2) flag(2)
    # method(2) time(2) date(2) crc(4) csize(4) usize(4) → usize à +24.
    idx = raw.rfind(b"PK\x01\x02")
    raw[idx + 24 : idx + 28] = struct.pack("<I", 10)
    return bytes(raw)


def test_read_tileset3d_entry_422_for_a_corrupt_entry(env):
    """Revue finale de branche, M1 : BadZipFile/RuntimeError (entrée
    chiffrée)/NotImplementedError (compression non supportée) remontaient en
    500 non typé. Réponse propre attendue."""
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3
        )
        s.commit()
    fake_s3.objects["tenant/x/city.zip"] = _zip_with_understated_entry_size()

    r = client.get(f"/v1/tileset3d/{item_id}/tiles/big.b3dm")

    assert r.status_code == 422, r.text
    assert r.json()["detail"] == "cannot read entry"


def test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        bob = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        item_id = _seed_hosted_tileset_item(
            s, tenant_id=tenant.id, owner_id=bob.id, fake_s3=fake_s3
        )
        s.commit()
    r = client.get(f"/v1/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 404

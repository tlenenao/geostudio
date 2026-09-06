# SPDX-License-Identifier: Apache-2.0
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")

        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self.objects[Key])}


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
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: deferred.append((job_id, tenant_id))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3


def test_presign_returns_upload_url_and_key(env):
    client, *_ = env
    r = client.post(
        "/v1/uploads/presign",
        json={"filename": "villes.geojson", "contentType": "application/geo+json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["key"].endswith("-villes.geojson")
    assert body["uploadUrl"].startswith("https://minio.test/")


def test_create_upload_job_defers_task_and_returns_job_id(env):
    client, Session, tenant, alice, deferred, _fake_s3 = env
    r = client.post(
        "/v1/uploads",
        json={
            "key": "default/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    )
    assert r.status_code == 201
    job_id = r.json()["jobId"]
    assert deferred == [(job_id, tenant.id)]

    r2 = client.get(f"/v1/uploads/{job_id}")
    assert r2.status_code == 200
    assert r2.json() == {
        "status": "pending",
        "errorMessage": None,
        "collectionId": None,
        "itemId": None,
    }


def test_create_upload_job_rejects_key_with_foreign_tenant_prefix(env):
    client, *_ = env
    r = client.post(
        "/v1/uploads",
        json={
            "key": "other-tenant/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    )
    assert r.status_code == 400


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    assert client.get("/v1/uploads/does-not-exist").status_code == 404


def test_create_upload_job_rejects_a_reader_without_data_manage(env):
    # SP-42, correctif 1 (F-securite-autorisation-01) : ce job déclenche du DDL
    # (création de table PostGIS) au worker — un Lecteur (aucun privilège) ne
    # doit pas pouvoir le déclencher, alors qu'un Créateur (data.manage) le peut
    # toujours (cf. test_create_upload_job_defers_task_and_returns_job_id).
    from app.roles.repository import ensure_built_in_roles
    from app.users.repository import set_user_role

    client, Session, tenant, alice, _deferred, _fake_s3 = env
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=alice.id,
            role_id=roles["reader"].id,
            role_slug=roles["reader"].slug,
        )
        s.commit()
    # `alice` reste l'objet capturé par le dependency override du fixture
    # (une seule instance detachée, jamais re-fetchée par requête) : le
    # basculer en Lecteur nécessite de muter cette instance-là, pas seulement
    # la ligne SQL sous-jacente.
    alice.role_id = roles["reader"].id
    alice.is_admin = False

    r = client.post(
        "/v1/uploads",
        json={
            "key": "default/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    )
    assert r.status_code == 403


def test_create_upload_job_rejects_data_manage_alone_without_maps_manage(env):
    # SP-42, revue de la dernière passe de correctifs (point 5, Important) :
    # cette route exige data.manage (DDL réel, création de la collection
    # cible) mais app.ingestion.importer::import_job crée AUSSI un
    # Item(resource_type="map") + Config(kind="map") pour afficher le
    # résultat — donc maps.manage selon app.configs.routes::_KIND_PRIVILEGE.
    # Un rôle sur mesure porteur de data.manage SEUL (sans maps.manage,
    # combinaison réelle : les deux rôles prédéfinis qui portent
    # data.manage — Créateur, Admin — portent aussi maps.manage, mais rien
    # n'empêche un rôle sur mesure de séparer les deux) obtenait donc 201 et
    # laissait le worker créer la map sans jamais consulter ce second
    # privilège.
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    client, Session, tenant, alice, _deferred, _fake_s3 = env
    with Session() as s:
        role = create_role(
            s,
            tenant_id=tenant.id,
            name="Data seul",
            privileges=[Privilege.DATA_MANAGE.value],
        )
        set_user_role(
            s, tenant_id=tenant.id, user_id=alice.id, role_id=role.id, role_slug=role.slug
        )
        s.commit()
        role_id = role.id
    alice.role_id = role_id
    alice.is_admin = False

    r = client.post(
        "/v1/uploads",
        json={
            "key": "default/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    )
    assert r.status_code == 403


def test_get_upload_job_cross_tenant_returns_404(env):
    # repo.get_job filters by tenant_id (app/ingestion/repository.py) — a job
    # created under one tenant must be invisible (404, not the job's real
    # status) to a user authenticated in a different tenant. Only the
    # unknown-job-id 404 case was covered before this review.
    import uuid

    from app.tenants.models import Tenant
    from app.users.repository import get_or_create_user

    client, Session, tenant, alice, deferred, _fake_s3 = env
    job_id = client.post(
        "/v1/uploads",
        json={
            "key": f"{tenant.id}/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    ).json()["jobId"]

    with Session() as s:
        other_tenant = Tenant(
            id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other"
        )
        s.add(other_tenant)
        s.flush()
        outsider = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="sub-outsider",
            username="outsider",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(outsider)

    client.app.dependency_overrides[get_current_user] = lambda: outsider
    try:
        response = client.get(f"/v1/uploads/{job_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: alice
    assert response.status_code == 404


def test_get_upload_job_other_user_same_tenant_returns_404(env):
    # REV-010 : `get_upload_job` ne filtrait que par tenant_id — un autre
    # utilisateur du MEME tenant (sans data.manage) pouvait lire le
    # statut/message d'erreur du job d'import d'alice.
    from app.users.repository import get_or_create_user

    client, Session, tenant, alice, _deferred, _fake_s3 = env
    job_id = client.post(
        "/v1/uploads",
        json={
            "key": f"{tenant.id}/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    ).json()["jobId"]

    with Session() as s:
        from app.roles.repository import ensure_built_in_roles
        from app.users.repository import set_user_role

        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        bob = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=bob.id,
            role_id=roles["reader"].id,
            role_slug=roles["reader"].slug,
        )
        s.commit()
        s.refresh(bob)
    bob.role_id = roles["reader"].id
    bob.is_admin = False

    client.app.dependency_overrides[get_current_user] = lambda: bob
    try:
        response = client.get(f"/v1/uploads/{job_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: alice
    assert response.status_code == 404


def test_get_upload_job_readable_by_holder_of_data_manage(env):
    # REV-010 : un porteur de data.manage (ex. un Créateur) doit pouvoir lire
    # le job d'un autre utilisateur du même tenant, même s'il ne l'a pas créé
    # lui-même — c'est l'exception explicitement prévue par le correctif.
    from app.users.repository import get_or_create_user

    client, Session, tenant, alice, _deferred, _fake_s3 = env
    job_id = client.post(
        "/v1/uploads",
        json={
            "key": f"{tenant.id}/abc-villes.geojson",
            "filename": "villes.geojson",
            "collectionTitle": "Villes",
        },
    ).json()["jobId"]

    with Session() as s:
        from app.roles.repository import ensure_built_in_roles
        from app.users.repository import set_user_role

        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        carol = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="c",
            username="carol",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=carol.id,
            role_id=roles["creator"].id,
            role_slug=roles["creator"].slug,
        )
        s.commit()
        s.refresh(carol)
    carol.role_id = roles["creator"].id
    carol.is_admin = False

    client.app.dependency_overrides[get_current_user] = lambda: carol
    try:
        response = client.get(f"/v1/uploads/{job_id}")
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: alice
    assert response.status_code == 200


def test_create_upload_job_is_audited(env):
    client, Session, tenant, alice, _deferred, _fake_s3 = env
    client.post(
        "/v1/uploads",
        json={
            "key": "default/abc.csv",
            "filename": "villes.csv",
            "collectionTitle": "Villes CSV",
            "latField": "y",
            "lonField": "x",
        },
    )
    with Session() as s:
        from sqlalchemy import select

        from app.audit.models import AuditLog

        rows = s.scalars(select(AuditLog).where(AuditLog.action == "ingestion.job_create")).all()
        assert len(rows) == 1
        assert rows[0].payload["collectionTitle"] == "Villes CSV"


def _tiny_gpkg_bytes(tmp_path) -> bytes:
    import numpy as np
    import shapely
    from pyogrio.raw import write as pyogrio_write

    path = tmp_path / "villes.gpkg"
    geometry = shapely.to_wkb(np.array([shapely.geometry.Point(1.0, 2.0)], dtype=object))
    pyogrio_write(
        str(path),
        geometry=geometry,
        field_data=[np.array(["A"], dtype=object)],
        fields=["nom"],
        layer="villes",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    return path.read_bytes()


def test_inspect_upload_returns_layers(env, tmp_path):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.gpkg"] = _tiny_gpkg_bytes(tmp_path)
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 200
    # SP-56 : InspectResponse gagne un champ "fields" optionnel (peuplé pour
    # .xlsx uniquement) — non-régression sur la forme "layers" existante.
    assert r.json() == {
        "layers": [{"name": "villes", "featureCount": 1, "geometryType": "Point"}],
        "fields": None,
    }


def test_inspect_upload_rejects_foreign_tenant_key(env):
    client, *_ = env
    r = client.post(
        "/v1/uploads/inspect", json={"key": "other-tenant/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 400


def test_inspect_upload_rejects_unsupported_format(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.csv"] = b"nom,lat,lon\n"
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.csv", "filename": "villes.csv"}
    )
    assert r.status_code == 400


def test_inspect_upload_404_when_object_missing(env):
    client, Session, tenant, *_ = env
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/absent.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 404


def test_inspect_upload_422_on_corrupt_file(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.gpkg"] = b"not a real gpkg"
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.gpkg", "filename": "villes.gpkg"}
    )
    assert r.status_code == 422


def _xlsx_bytes(headers: list[str]) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    ws.append(["Paris", 48.85, 2.35])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_inspect_upload_xlsx_returns_fields(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.xlsx"] = _xlsx_bytes(["nom", "lat", "lon"])
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.xlsx", "filename": "villes.xlsx"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fields"] == ["nom", "lat", "lon"]
    assert body["layers"] == []


def _kml_multi_layer_bytes() -> bytes:
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        b"<Folder><name>a</name><Placemark><name>Paris</name>"
        b"<Point><coordinates>2.35,48.85,0</coordinates></Point></Placemark></Folder>"
        b"<Folder><name>b</name><Placemark><name>Lyon</name>"
        b"<Point><coordinates>4.83,45.76,0</coordinates></Point></Placemark></Folder>"
        b"</Document></kml>"
    )


def test_inspect_upload_kml_returns_layers(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    fake_s3.objects[f"{tenant.id}/k.kml"] = _kml_multi_layer_bytes()
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.kml", "filename": "villes.kml"}
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["layers"]) == 2
    assert body["fields"] is None


def test_inspect_upload_parquet_returns_400_not_concerned(env, tmp_path):
    import geopandas as gpd
    from shapely.geometry import Point

    client, Session, tenant, alice, _deferred, fake_s3 = env
    gdf = gpd.GeoDataFrame({"nom": ["Paris"]}, geometry=[Point(2.35, 48.85)], crs="EPSG:4326")
    path = tmp_path / "villes.parquet"
    gdf.to_parquet(path)
    fake_s3.objects[f"{tenant.id}/k.parquet"] = path.read_bytes()
    r = client.post(
        "/v1/uploads/inspect", json={"key": f"{tenant.id}/k.parquet", "filename": "villes.parquet"}
    )
    assert r.status_code == 400


def test_create_upload_job_accepts_layer_name(env):
    client, Session, tenant, *_ = env
    r = client.post(
        "/v1/uploads",
        json={
            "key": f"{tenant.id}/abc-villes.gpkg",
            "filename": "villes.gpkg",
            "collectionTitle": "Villes",
            "layerName": "villes",
        },
    )
    assert r.status_code == 201
    job_id = r.json()["jobId"]
    with Session() as s:
        from app.ingestion import repository as ingestion_repo

        job = ingestion_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.layer_name == "villes"

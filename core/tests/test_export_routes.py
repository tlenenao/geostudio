# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.export import repository as export_repo
from app.export import routes as export_routes
from app.ingestion import routes as ingestion_routes
from app.items.repository import create_item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    # Même contrat minimal que tests/test_ingestion_routes.py::_FakeS3Client —
    # seule generate_presigned_url est exercée par app/export/routes.py
    # (via app.ingestion.storage.generate_presigned_get_url).
    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


def _fake_deferrer():
    # Même patron que
    # core/tests/test_pipeline_routes.py::test_run_route_defers_job_and_returns_run_id
    # (client.app.dependency_overrides[routes.get_task_deferrer] = ...) — sans
    # cet override, POST /export appellerait le vrai render_export_task.defer(...)
    # contre le connecteur procrastinate réel (DATABASE_URL non défini dans ces
    # tests sqlite), et échouerait pour une raison sans rapport avec ce qui est testé.
    calls = []

    def deferrer(job_id, tenant_id):
        calls.append((job_id, tenant_id))

    return deferrer, calls


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        stranger = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        item = create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="map", title="Carte"
        )
        configs_repo.create_config(
            s,
            BuilderConfig(
                kind="map",
                map={
                    "basemap": {"style": "https://x.test/s.json"},
                    "view": {"center": [0.0, 0.0], "zoom": 2.0},
                },
            ),
            item.id,
            tenant_id=tenant.id,
        )
        s.commit()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    # GET /export/jobs/{id} déclare désormais s3=Depends(get_s3_client) (au
    # lieu de lire os.environ["S3_*"] en dur) — cette dépendance est résolue
    # par FastAPI pour CHAQUE appel à cette route, quel que soit le statut du
    # job, donc toute la suite a besoin d'un client S3 factice, pas seulement
    # les tests qui atteignent la branche "done" (revue SP-17a, finding
    # Important task 7, fix round 1). app.export.routes réutilise
    # littéralement ingestion_routes.get_s3_client (même objet fonction),
    # donc c'est cette clé qu'il faut overrider ici.
    fake_s3 = _FakeS3Client()

    def make_client():
        app = create_app()
        app.dependency_overrides[db.get_session] = override_session
        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
        deferrer, calls = _fake_deferrer()
        app.dependency_overrides[export_routes.get_task_deferrer] = lambda: deferrer
        return TestClient(app), calls

    return make_client, owner, stranger, item.id, Session


def test_post_export_requires_flag_enabled(env, monkeypatch):
    make_client, _owner, _stranger, item_id, _Session = env
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    client, _calls = (
        make_client()
    )  # le flag est lu à la construction (patron pipelines) : re-créer l'app
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404  # routeur jamais monté quand le flag est off


def test_post_export_creates_job_and_returns_202(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202
    assert "jobId" in response.json()
    assert len(calls) == 1


def test_post_export_denies_user_without_read_access(env):
    make_client, _owner, stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    client.app.dependency_overrides[get_current_user_optional] = lambda: stranger
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404


def test_get_export_job_reports_status(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/export", json={"itemId": item_id, "format": "png"}).json()
    response = client.get(f"/export/jobs/{created['jobId']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["jobId"]
    assert body["status"] == "pending"
    assert body["resultUrl"] is None
    assert body["error"] is None


def test_get_export_job_unknown_id_is_404(env):
    make_client, owner, _stranger, _item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.get("/export/jobs/does-not-exist")
    assert response.status_code == 404


def test_post_export_allowed_in_read_only_demo_mode(env, monkeypatch):
    # Garde démo (core/app/main.py::read_only_guard) : l'export est une
    # action de lecture (aucune écriture de donnée métier), doit rester
    # utilisable en CORE_READ_ONLY_MODE=true — même raisonnement que les
    # routes d'export SP-16a, déjà exemptées via _EXPORT_PATH_RE.
    make_client, owner, _stranger, item_id, _Session = env
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202


def test_post_export_rejects_invalid_format(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "svg"})
    assert response.status_code == 422


def test_get_export_job_done_status_includes_result_url(env):
    # Revue SP-17a, finding Important task 7 : avant ce fix, get_export_job_route
    # construisait son client S3 en lisant os.environ["S3_*"] en dur (KeyError
    # opaque hors env réel) et aucun test ne poussait un job jusqu'à "done" —
    # toute la branche de construction du résultat (client S3 + URL présignée)
    # était donc totalement non exercée malgré resultUrl faisant partie du
    # contrat documenté de cette route. On pousse ici le job à "done" via
    # export_repo.mark_done directement (même patron que
    # tests/test_export_repository.py::test_mark_running_then_done), sans
    # jamais faire tourner le vrai worker Playwright.
    make_client, owner, _stranger, item_id, Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/export", json={"itemId": item_id, "format": "png"}).json()
    job_id = created["jobId"]

    with Session() as s:
        export_repo.mark_running(s, job_id=job_id)
        export_repo.mark_done(s, job_id=job_id, result_key=f"renders/{job_id}.png")
        s.commit()

    response = client.get(f"/export/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["error"] is None
    assert body["resultUrl"] == f"https://minio.test/geostudio-exports/renders/{job_id}.png"

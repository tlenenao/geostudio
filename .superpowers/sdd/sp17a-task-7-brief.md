### Task 7: Routes REST `POST /export` + `GET /export/jobs/{id}`

> **Ne pas oublier le garde démo** : `core/app/main.py:67-81` porte un middleware global `read_only_guard` qui bloque tout `POST`/`PUT`/`PATCH`/`DELETE` en `CORE_READ_ONLY_MODE=true`, sauf chemins déjà exemptés via `_EXPORT_PATH_RE` (ligne 38, qui ne couvre que les exports SP-16a `/collections/{id}/export`/`/datasets/{id}/arcgis/export`). `POST /export` (cette tâche) doit être ajouté à cette exemption — le design dit explicitement que l'export est une action de lecture, « même raisonnement que SP-16a » ; sans cet ajout, l'export serait silencieusement bloqué en 403 dès qu'une instance active le mode démo, alors même que rien dans les tests des tâches précédentes ne l'aurait détecté (ils ne passent jamais par `create_app()` avec `CORE_READ_ONLY_MODE=true`).

**Files:**
- Create: `core/app/export/routes.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_export_routes.py`

**Interfaces:**
- Consumes: `export_repo.*` (Tâche 3), `render_export_task` (Tâche 6), `is_export_enabled` (Tâche 2), `items_repo.get_access_facts`/`can` (existants).
- Produces: `POST /export` body `{"itemId": str, "format": "png"|"pdf"}` → 202 `{"jobId": str}`. `GET /export/jobs/{job_id}` → 200 `{"id": str, "status": str, "resultUrl": str|None, "error": str|None}`.

- [ ] **Step 1: Écrire le test qui échoue**

```python
# core/tests/test_export_routes.py
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
from app.items.repository import create_item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _fake_deferrer():
    # Même patron que core/tests/test_pipeline_routes.py::test_run_route_defers_job_and_returns_run_id
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        stranger = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        item = create_item(s, tenant_id=tenant.id, owner_id=owner.id, resource_type="map", title="Carte")
        configs_repo.create_config(
            s,
            BuilderConfig(kind="map", map={"basemap": {"style": "https://x.test/s.json"}, "view": {"center": [0.0, 0.0], "zoom": 2.0}}),
            item.id, tenant_id=tenant.id,
        )
        s.commit()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    def make_client():
        app = create_app()
        app.dependency_overrides[db.get_session] = override_session
        deferrer, calls = _fake_deferrer()
        app.dependency_overrides[export_routes.get_task_deferrer] = lambda: deferrer
        return TestClient(app), calls

    return make_client, owner, stranger, item.id


def test_post_export_requires_flag_enabled(env, monkeypatch):
    make_client, _owner, _stranger, item_id = env
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    client, _calls = make_client()  # le flag est lu à la construction (patron pipelines) : re-créer l'app
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404  # routeur jamais monté quand le flag est off


def test_post_export_creates_job_and_returns_202(env):
    make_client, owner, _stranger, item_id = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202
    assert "jobId" in response.json()
    assert len(calls) == 1


def test_post_export_denies_user_without_read_access(env):
    make_client, _owner, stranger, item_id = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    client.app.dependency_overrides[get_current_user_optional] = lambda: stranger
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 404


def test_get_export_job_reports_status(env):
    make_client, owner, _stranger, item_id = env
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
    make_client, owner, _stranger, _item_id = env
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
    make_client, owner, _stranger, item_id = env
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/export", json={"itemId": item_id, "format": "png"})
    assert response.status_code == 202
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.routes'`

- [ ] **Step 3: Implémenter les routes**

```python
# core/app/export/routes.py
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'export (SP-17a) — montées uniquement quand
CORE_EXPORT_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête — même patron que app.pipelines.routes)."""
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.export import repository as export_repo
from app.export.jobs import render_export_task
from app.ingestion.storage import generate_presigned_get_url, make_s3_client
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

import os

router = APIRouter()


class CreateExportRequest(BaseModel):
    itemId: str
    format: str


class CreateExportResponse(BaseModel):
    jobId: str


class ExportJobStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None


def _require_export_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        render_export_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/export", response_model=CreateExportResponse, status_code=202)
def create_export_route(
    body: CreateExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> CreateExportResponse:
    if body.format not in ("png", "pdf"):
        raise HTTPException(status_code=422, detail="format must be 'png' or 'pdf'")
    _require_export_read_access(session, user=user, item_id=body.itemId)
    job = export_repo.create_job(session, tenant_id=user.tenant_id, item_id=body.itemId, user_id=user.id, format=body.format)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="export.create", object_type="export_job", object_id=job.id,
        payload={"itemId": body.itemId, "format": body.format},
    )
    # Commit avant de déférer : même raison que run_pipeline_route.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return CreateExportResponse(jobId=job.id)


@router.get("/export/jobs/{job_id}", response_model=ExportJobStatus)
def get_export_job_route(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ExportJobStatus:
    job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="export job not found")
    _require_export_read_access(session, user=user, item_id=job.item_id)
    result_url = None
    if job.status == "done" and job.result_key:
        client = make_s3_client(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"], secret_key=os.environ["S3_SECRET_KEY"],
        )
        result_url = generate_presigned_get_url(
            client, bucket=os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports"), key=job.result_key,
        )
    return ExportJobStatus(id=job.id, status=job.status, resultUrl=result_url, error=job.error)
```

Dans `core/app/main.py`, ajouter l'import (à côté des autres imports de routes, en tête de fichier) :

```python
from app.auth.dependency import is_export_enabled
from app.export import routes as export_routes
```

Et, juste après le bloc `if is_etl_enabled(): app.include_router(pipelines_routes.router)` (ligne 105-106) :

```python
    if is_export_enabled():
        app.include_router(export_routes.router)
```

Enfin, exempter `POST /export` du garde lecture-seule démo (sinon 403 systématique dès `CORE_READ_ONLY_MODE=true`, cf. note en tête de cette tâche). Remplacer, ligne 38 :

```python
_EXPORT_PATH_RE = re.compile(r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$")
```

par :

```python
_EXPORT_PATH_RE = re.compile(r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$|^/export$")
```

(`GET /export/jobs/{id}` n'a pas besoin d'exemption : le middleware ne filtre que `POST`/`PUT`/`PATCH`/`DELETE`.)

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_routes.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Suite complète cœur**

Run: `cd core && uv run pytest tests/ -x -q`
Expected: PASS (aucune régression)

- [ ] **Step 6: Commit**

```bash
git add core/app/export/routes.py core/app/main.py core/tests/test_export_routes.py
git commit -m "feat(core): SP-17a — routes REST POST /export + GET /export/jobs/{id}"
```

---


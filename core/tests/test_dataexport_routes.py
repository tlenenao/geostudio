# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient  # noqa: F401

from app.dataexport import repository as dx_repo
from app.dataexport import routes as dx_routes
from app.dataexport.models import CollectionExportJob
from app.features import routes as features_routes
from app.ingestion.routes import get_s3_client
from app.roles.repository import create_role
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user
from tests.test_features_export_routes import _as, _register
from tests.test_features_export_routes import env as _env

env = _env


class _FakeS3:
    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        cd = Params.get("ResponseContentDisposition")
        return f"https://s3.test/{Params['Bucket']}/{Params['Key']}" + (f"?cd={cd}" if cd else "")


@pytest.fixture()
def starter(env):
    """Starter réel (start_export) avec defer espionné : vérifie « commit puis defer »."""
    app, _client, _a, _r, _p, _t, Session = env
    deferred = []

    def defer(job_id, tenant_id):
        with Session() as other:  # session indépendante : ne voit que le committé
            assert dx_repo.get_job(other, job_id, tenant_id) is not None
        deferred.append((job_id, tenant_id))

    app.dependency_overrides[features_routes.get_export_job_starter] = lambda: (
        lambda session, **kw: dx_routes.start_export(session, defer=defer, **kw)
    )
    app.dependency_overrides[get_s3_client] = lambda: _FakeS3()
    return deferred


def _add_items(client, col_id, n):
    for i in range(n):
        client.post(
            f"/v1/collections/{col_id}/items",
            json={
                "type": "Feature",
                "properties": {"region": f"r{i}", "pop": i},
                "geometry": {"type": "Point", "coordinates": [i, i]},
            },
        )


def test_small_export_stays_synchronous(env, starter):
    app, client, admin, *_ = env
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    resp = client.get(f"/v1/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 200
    assert not starter


def test_over_sync_max_returns_202_and_defers_after_commit(env, starter, monkeypatch):
    app, client, admin, _r, _p, tenant_id, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "2")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 3)
    resp = client.get(f"/v1/collections/{col['id']}/export/items?format=csv&region=r1")
    assert resp.status_code == 202
    job_id = resp.json()["jobId"]
    assert resp.headers["location"] == f"/v1/collections/{col['id']}/export/jobs/{job_id}"
    assert starter == [(job_id, tenant_id)]
    with Session() as s:
        job = s.get(CollectionExportJob, job_id)
        assert (job.status, job.format, job.requested_by) == ("pending", "csv", admin.id)
        assert job.query["filters"] == {"region": "r1"}
        assert job.masked is False  # admin : data.view_sensitive


def test_masked_verdict_is_frozen_at_creation(env, starter, monkeypatch):
    app, client, admin, regular, _p, _t, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    _as(app, regular)
    resp = client.get(f"/v1/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 202
    with Session() as s:
        assert s.get(CollectionExportJob, resp.json()["jobId"]).masked is True


def test_defer_failure_leaves_job_pending(env, monkeypatch):
    app, client, admin, _r, _p, _t, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")

    def boom(job_id, tenant_id):
        raise RuntimeError("queue down")

    app.dependency_overrides[features_routes.get_export_job_starter] = lambda: (
        lambda session, **kw: dx_routes.start_export(session, defer=boom, **kw)
    )
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    resp = client.get(f"/v1/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 202
    with Session() as s:
        assert s.get(CollectionExportJob, resp.json()["jobId"]).status == "pending"


def test_over_job_max_is_413(env, starter, monkeypatch):
    app, client, admin, *_ = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    monkeypatch.setenv("CORE_EXPORT_JOB_MAX", "2")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 3)
    assert client.get(f"/v1/collections/{col['id']}/export/items?format=csv").status_code == 413
    assert not starter


def test_status_returns_presigned_url_when_done(env, starter, monkeypatch):
    app, client, admin, _r, _p, tenant_id, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    job_id = client.get(f"/v1/collections/{col['id']}/export/items?format=csv").json()["jobId"]
    url = f"/v1/collections/{col['id']}/export/jobs/{job_id}"
    body = client.get(url).json()
    assert body["status"] == "pending" and body["resultUrl"] is None
    with Session() as s:
        dx_repo.mark_running(s, job_id)
        dx_repo.mark_done(
            s, job_id, result_key=f"{tenant_id}/data-exports/{job_id}.csv", filename="v.csv"
        )
        s.commit()
    body = client.get(url).json()
    assert body["status"] == "done" and body["filename"] == "v.csv"
    assert (
        body["resultUrl"]
        == f"https://s3.test/geostudio-exports/{tenant_id}/data-exports/{job_id}.csv"
        '?cd=attachment; filename="v.csv"'
    )


def test_status_of_another_user_or_collection_is_404(env, starter, monkeypatch):
    app, client, admin, regular, *_ = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    job_id = client.get(f"/v1/collections/{col['id']}/export/items?format=csv").json()["jobId"]
    assert client.get(f"/v1/collections/other/export/jobs/{job_id}").status_code == 404
    _as(app, regular)  # lecteur de la collection publique, mais pas demandeur
    assert client.get(f"/v1/collections/{col['id']}/export/jobs/{job_id}").status_code == 404


def _done_job_as_admin(env, monkeypatch):
    app, client, admin, regular, _p, tenant_id, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    job_id = client.get(f"/v1/collections/{col['id']}/export/items?format=csv").json()["jobId"]
    with Session() as s:
        dx_repo.mark_running(s, job_id)
        dx_repo.mark_done(s, job_id, result_key=f"{tenant_id}/x/{job_id}.csv", filename="v.csv")
        s.commit()
    return f"/v1/collections/{col['id']}/export/jobs/{job_id}"


def _with_privileges(Session, user, tenant_id, privileges):
    with Session() as s:
        role = create_role(
            s, tenant_id=tenant_id, name="r" + "".join(privileges), privileges=privileges
        )
        s.commit()
        user.role_id = role.id  # l'objet est celui que renvoie get_current_user


def test_tasks_view_all_without_view_sensitive_cannot_get_unmasked_result(
    env, starter, monkeypatch
):
    # GAP-22 : le job a été créé masked=False par l'admin ; le lien présigné
    # contient les colonnes sensibles, un non-demandeur ne le reçoit que s'il
    # pourrait lui-même les lire.
    app, client, admin, regular, _p, tenant_id, Session = env
    url = _done_job_as_admin(env, monkeypatch)
    _with_privileges(Session, regular, tenant_id, ["tasks.view_all", "data.read"])
    _as(app, regular)
    assert client.get(url).status_code == 404


def test_tasks_view_all_with_view_sensitive_gets_unmasked_result(env, starter, monkeypatch):
    app, client, admin, regular, _p, tenant_id, Session = env
    url = _done_job_as_admin(env, monkeypatch)
    _with_privileges(Session, regular, tenant_id, ["tasks.view_all", "data.view_sensitive"])
    _as(app, regular)
    assert client.get(url).json()["resultUrl"]


def test_tasks_view_all_gets_masked_result_without_view_sensitive(env, starter, monkeypatch):
    app, client, admin, regular, _p, tenant_id, Session = env
    monkeypatch.setenv("CORE_EXPORT_SYNC_MAX", "1")
    col = _register(app, client, admin, public=True)
    _add_items(client, col["id"], 2)
    _as(app, regular)
    job_id = client.get(f"/v1/collections/{col['id']}/export/items?format=csv").json()["jobId"]
    requester = _requester_view(client, col["id"], job_id)
    assert requester == 200
    other = admin  # un autre utilisateur, tasks.view_all (admin), lit le job masqué
    _as(app, other)
    assert client.get(f"/v1/collections/{col['id']}/export/jobs/{job_id}").status_code == 200


def _requester_view(client, col_id, job_id):
    return client.get(f"/v1/collections/{col_id}/export/jobs/{job_id}").status_code


def test_status_of_another_tenant_is_404(env, starter, monkeypatch):
    app, client, admin, regular, _p, tenant_id, Session = env
    url = _done_job_as_admin(env, monkeypatch)
    with Session() as s:
        s.add(Tenant(id="t2", slug="t2", name="T2"))
        s.flush()
        stranger = get_or_create_user(
            s,
            tenant_id="t2",
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    _as(app, stranger)
    assert client.get(url).status_code == 404


def test_requester_demoted_without_view_sensitive_cannot_get_unmasked_result(
    env, starter, monkeypatch
):
    app, client, admin, regular, _p, tenant_id, Session = env
    url = _done_job_as_admin(env, monkeypatch)
    job_id = url.rsplit("/", 1)[1]
    with Session() as s:  # le job non masqué appartient désormais à `regular`
        s.get(CollectionExportJob, job_id).requested_by = regular.id
        s.commit()
    _with_privileges(Session, regular, tenant_id, ["data.read"])
    _as(app, regular)
    assert client.get(url).status_code == 404

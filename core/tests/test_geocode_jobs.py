# SPDX-License-Identifier: Apache-2.0
"""Géocodage par lot asynchrone avec reprise (REV-367 j)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.db import init_db, make_engine, make_session_factory
from app.geocoding import jobs
from app.geocoding.models import GeocodeJob, _now
from app.geocoding.provider import GeocodeResult
from app.main import create_app


class FakeGeocoder:
    def __init__(self):
        self.calls: list[str] = []

    def search(self, q, limit):
        self.calls.append(q)
        if q.startswith("zzz"):
            return []
        return [GeocodeResult(label=f"L {q}", lon=2.0, lat=49.0)]


@pytest.fixture
def env(monkeypatch, tmp_path):
    url = f"sqlite+pysqlite:///{tmp_path / 'gj.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    init_db(make_engine(url))
    deferred: list[dict] = []
    monkeypatch.setattr(jobs.run_geocode_job, "defer", lambda **kw: deferred.append(kw))
    geocoder = FakeGeocoder()
    monkeypatch.setattr(jobs, "get_geocoder", lambda: geocoder)
    monkeypatch.setattr(jobs, "CHUNK", 2)
    client = TestClient(create_app())
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, deferred, geocoder, make_session_factory(make_engine(url))


def test_job_runs_to_completion_and_exposes_results(env):
    client, deferred, geocoder, _ = env
    r = client.post("/v1/geocode/jobs", json={"addresses": ["aaa 1", "zzz 2", "ccc 3"]})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    job_id = r.json()["id"]
    assert deferred == [{"job_id": job_id, "tenant_id": deferred[0]["tenant_id"]}]
    jobs.run_geocode_job(**deferred[0])
    out = client.get(f"/v1/geocode/jobs/{job_id}").json()
    assert (out["status"], out["total"], out["processed"]) == ("succeeded", 3, 3)
    assert (out["found"], out["not_found"]) == (2, 1)
    assert [x["status"] for x in out["results"]] == ["trouvé", "non_trouvé", "trouvé"]


def test_batch_and_jobs_require_data_manage(env):
    # REV-398 : coût d'egress -> privilège `data.manage` ; un compte sans rôle créateur est refusé.
    client, deferred, _g, factory = env
    assert client.get("/v1/me").status_code == 200  # provisionne le compte mock
    from sqlalchemy import select

    from app.auth.dependency import get_current_user
    from app.roles.repository import ensure_built_in_roles
    from app.users.models import User

    with factory() as s:
        u = s.scalars(select(User)).one()
        roles = ensure_built_in_roles(s, tenant_id=u.tenant_id)
        u.role_id, u.is_admin = roles["reader"].id, False
        s.commit()
        s.refresh(u)
        s.expunge(u)
    client.app.dependency_overrides[get_current_user] = lambda: u
    for path, body in (
        ("/v1/geocode/jobs", {"addresses": ["aaa 1"]}),
        ("/v1/geocode/batch", {"addresses": ["aaa 1"]}),
    ):
        assert client.post(path, json=body).status_code == 403
    assert deferred == []


def test_resume_does_not_regeocode_done_rows(env):
    client, deferred, geocoder, factory = env
    job_id = client.post("/v1/geocode/jobs", json={"addresses": ["aaa", "bbb", "ccc"]}).json()["id"]
    done = [{"address": "aaa", "status": "trouvé", "label": "L aaa", "lon": 2.0, "lat": 49.0}]
    with factory() as s:
        s.execute(update(GeocodeJob).values(status="running", results=done))
        s.commit()
        # worker tué : battement périmé -> le balayage repasse en pending et redéfère
        s.execute(update(GeocodeJob).values(updated_at=_now() - timedelta(minutes=10)))
        s.commit()
        assert jobs.requeue_stale(s) == [(job_id, deferred[0]["tenant_id"])]
        s.commit()
    jobs.run_geocode_job(**deferred[0])
    assert geocoder.calls == ["bbb", "ccc"]  # "aaa" non rejoué
    assert client.get(f"/v1/geocode/jobs/{job_id}").json()["processed"] == 3


def test_unknown_job_is_404_and_input_is_validated(env):
    client, _, _, _ = env
    assert client.get("/v1/geocode/jobs/nope").status_code == 404
    assert client.post("/v1/geocode/jobs", json={"addresses": ["a"]}).status_code == 422


def test_fourth_active_job_of_a_user_is_429(env):
    # AUD-156 : au plus 3 lots pending|running par utilisateur.
    client, *_ = env
    for _ in range(3):
        assert client.post("/v1/geocode/jobs", json={"addresses": ["aaa"]}).status_code == 202
    r = client.post("/v1/geocode/jobs", json={"addresses": ["aaa"]})
    assert r.status_code == 429


def test_purge_drops_only_old_finished_jobs(env):
    # AUD-156 : rétention de 7 jours des lots terminés ; un lot en cours n'est jamais purgé.
    client, _d, _g, factory = env
    ids = [client.post("/v1/geocode/jobs", json={"addresses": ["aaa"]}).json()["id"] for _ in "abc"]
    now = _now()
    ages = {ids[0]: ("succeeded", 8), ids[1]: ("failed", 2), ids[2]: ("running", 30)}
    with factory() as s:
        for job_id, (status, days) in ages.items():
            s.execute(
                update(GeocodeJob)
                .where(GeocodeJob.id == job_id)
                .values(status=status, updated_at=now - timedelta(days=days))
            )
        s.commit()
        assert jobs.purge_finished_jobs(s, now=now) == 1
        s.commit()
        assert {j.id for j in s.query(GeocodeJob)} == {ids[1], ids[2]}


def test_busy_geocoder_failure_stays_readable_other_errors_do_not(env, monkeypatch):
    # AUD-100 + revue SP-L2 : « géocodeur occupé » est un refus métier lisible ; tout
    # autre échec reste générique (le détail est dans les journaux).
    from app.job_errors import INTERNAL_ERROR_MESSAGE

    client, deferred, _geocoder, _ = env
    monkeypatch.setattr(jobs.time, "sleep", lambda s: None)

    def busy(geocoder, chunk):
        raise jobs.BatchBusy()

    def boom(geocoder, chunk):
        raise RuntimeError("SELECT secret FROM interne")

    errors = []
    for failure in (busy, boom):
        monkeypatch.setattr(jobs, "geocode_batch", failure)
        r = client.post("/v1/geocode/jobs", json={"addresses": ["aaa 1"]})
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        jobs.run_geocode_job(**deferred[-1])
        errors.append(client.get(f"/v1/geocode/jobs/{job_id}").json()["error"])
    assert "occupé" in errors[0]
    assert errors[1] == INTERNAL_ERROR_MESSAGE

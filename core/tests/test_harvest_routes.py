# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.users.repository import get_or_create_user

SOURCE_BODY = {
    "type": "stac",
    "url": "https://stac.example.com/collections",
    "mode": "reference",
    "enabled": True,
    "intervalMinutes": 60,
}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        from app.tenants.repository import get_or_create_default_tenant

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
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_create_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/v1/harvest/sources", json=SOURCE_BODY).status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/v1/harvest/sources", json=SOURCE_BODY)
    assert r.status_code == 201
    assert r.json()["type"] == "stac"
    listed = client.get("/v1/harvest/sources").json()["sources"]
    assert [s["url"] for s in listed] == ["https://stac.example.com/collections"]


def test_create_copy_mode_on_supporting_connector_succeeds(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "mode": "copy"}
    assert client.post("/v1/harvest/sources", json=body).status_code == 201


def test_create_copy_mode_on_unknown_type_is_422(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    body = {**SOURCE_BODY, "type": "arcgis-fs"}
    assert client.post("/v1/harvest/sources", json=body).status_code == 422


def test_create_arcgis_source_is_accepted(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": "arcgis",
            "url": "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            "mode": "reference",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "arcgis"


def test_create_unknown_type_is_rejected(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": "geonode-legacy",
            "url": "https://x",
            "mode": "reference",
        },
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_create_metadata_source_is_accepted(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": type_,
            "url": "https://catalog.example.com/x",
            "mode": "reference",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == type_


@pytest.mark.parametrize("type_", ["csw", "ogc-records"])
def test_copy_mode_rejected_for_metadata_connectors(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": type_,
            "url": "https://catalog.example.com/x",
            "mode": "copy",
        },
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("type_", ["wms", "wfs", "wmts"])
def test_create_ows_source_is_accepted(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": type_,
            "url": "https://ows.example.com/x?request=GetCapabilities",
            "mode": "reference",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == type_


@pytest.mark.parametrize("type_", ["wms", "wmts"])
def test_copy_mode_rejected_for_raster_connectors(env, type_):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": type_,
            "url": "https://ows.example.com/x",
            "mode": "copy",
        },
    )
    assert resp.status_code == 400


def test_copy_mode_accepted_for_wfs(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": "wfs",
            "url": "https://ows.example.com/wfs",
            "mode": "copy",
        },
    )
    assert resp.status_code == 201


def test_patch_requires_admin_and_toggles_enabled(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()
    _as(app, regular)
    assert (
        client.patch(f"/v1/harvest/sources/{created['id']}", json={"enabled": False}).status_code
        == 403
    )
    _as(app, admin)
    r = client.patch(f"/v1/harvest/sources/{created['id']}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_patch_interval_minutes_zero_is_422(env):
    # Parité avec HarvestSourceCreate.intervalMinutes (ge=1) : un intervalle
    # <= 0 rendrait list_due_sources() perpétuellement "due", cf. revue finale.
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()
    r = client.patch(f"/v1/harvest/sources/{created['id']}", json={"intervalMinutes": 0})
    assert r.status_code == 422


def test_get_and_patch_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="oa",
            username="other-admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.get(f"/v1/harvest/sources/{created['id']}").status_code == 404
    assert (
        client.patch(f"/v1/harvest/sources/{created['id']}", json={"enabled": False}).status_code
        == 404
    )


def test_delete_source(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()
    assert client.delete(f"/v1/harvest/sources/{created['id']}").status_code == 204
    assert client.get("/v1/harvest/sources").json()["sources"] == []
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        row = s.scalars(select(AuditLog).where(AuditLog.action == "harvest_source.delete")).one()
    assert row.payload == {"removedItems": 0}


def test_run_defers_a_task_and_is_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()
    deferred = []
    from app.harvest import routes as harvest_routes

    def fake_deferrer():
        def deferrer(source_id, tenant_id):
            deferred.append((source_id, tenant_id))

        return deferrer

    app.dependency_overrides[harvest_routes.get_task_deferrer] = fake_deferrer
    r = client.post(f"/v1/harvest/sources/{created['id']}/run")
    assert r.status_code == 202
    assert deferred == [(created["id"], admin.tenant_id)]

    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "harvest_source.create" in actions
    assert "harvest_source.run" in actions


def test_run_missing_source_is_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/v1/harvest/sources/does-not-exist/run").status_code == 404


def test_mutations_blocked_in_read_only_mode(env, monkeypatch):
    app, client, _, admin, _regular = env
    _as(app, admin)
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    assert client.post("/v1/harvest/sources", json=SOURCE_BODY).status_code == 403


def test_create_ckan_source_is_accepted(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": "ckan",
            "url": "https://demo.data.gouv.fr",
            "mode": "reference",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["type"] == "ckan"


def test_copy_mode_accepted_for_ckan(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    resp = client.post(
        "/v1/harvest/sources",
        json={
            "type": "ckan",
            "url": "https://demo.data.gouv.fr",
            "mode": "copy",
        },
    )
    assert resp.status_code == 201


@pytest.mark.parametrize(
    "url", ["pas une url", "ftp://x.example.com", "file:///etc/passwd", "http://"]
)
def test_create_rejects_non_http_url(env, url):
    # P19.05 / j07-004
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/v1/harvest/sources", json={**SOURCE_BODY, "url": url}).status_code == 422


def test_patch_rejects_non_http_url_but_legacy_stored_url_stays_readable(env):
    # Piège « modèle pydantic relu » : la validation ne vaut qu'à l'écriture ;
    # une source déjà stockée avec une URL invalide reste listable/lisible.
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()
    assert (
        client.patch(f"/v1/harvest/sources/{created['id']}", json={"url": "nope"}).status_code
        == 422
    )
    from app.harvest.models import HarvestSource

    with Session() as s:
        s.get(HarvestSource, created["id"]).url = "pas une url"
        s.commit()
    assert client.get(f"/v1/harvest/sources/{created['id']}").status_code == 200
    assert client.get("/v1/harvest/sources").json()["sources"][0]["url"] == "pas une url"
    # PATCH sans toucher l'URL reste possible.
    assert (
        client.patch(f"/v1/harvest/sources/{created['id']}", json={"enabled": False}).status_code
        == 200
    )


def test_duplicate_source_is_409(env):
    # P19.06 / j07-005
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.post("/v1/harvest/sources", json=SOURCE_BODY).status_code == 201
    assert client.post("/v1/harvest/sources", json=SOURCE_BODY).status_code == 409
    other = client.post("/v1/harvest/sources", json={**SOURCE_BODY, "url": "https://b.example"})
    assert other.status_code == 201
    dup = client.patch(
        f"/v1/harvest/sources/{other.json()['id']}", json={"url": SOURCE_BODY["url"]}
    )
    assert dup.status_code == 409


def test_source_exposes_record_counts_and_records_list(env):
    # P19.16 / j07-020
    app, client, Session, admin, _regular = env
    _as(app, admin)
    sid = client.post("/v1/harvest/sources", json=SOURCE_BODY).json()["id"]
    from app.harvest import repository as repo

    with Session() as s:
        tenant_id = s.get(
            __import__("app.harvest.models", fromlist=["x"]).HarvestSource, sid
        ).tenant_id
        for ext, stale in (("a", False), ("b", True)):
            rec = repo.create_record(
                s,
                tenant_id=tenant_id,
                source_id=sid,
                external_id=ext,
                item_id=None,
                collection_id=None,
                content_hash="h",
            )
            rec.is_stale = stale
        s.commit()
    one = client.get(f"/v1/harvest/sources/{sid}").json()
    assert (one["recordCount"], one["staleCount"]) == (2, 1)
    assert client.get("/v1/harvest/sources").json()["sources"][0]["recordCount"] == 2
    recs = client.get(f"/v1/harvest/sources/{sid}/records").json()
    assert recs["total"] == 2
    assert [(r["externalId"], r["state"]) for r in recs["records"]] == [("a", "ok"), ("b", "stale")]
    assert client.get("/v1/harvest/sources/nope/records").status_code == 404

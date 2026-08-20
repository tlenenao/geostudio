# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.configs.report_validation import validate_report_payload
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _report_config(bookmark_item_id: str) -> BuilderConfig:
    return BuilderConfig.model_validate(
        {
            "kind": "report",
            "report": {
                "bookmarkItemId": bookmark_item_id,
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        }
    )


def test_ignores_non_report_kind():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        config = BuilderConfig.model_validate(
            {
                "kind": "map",
                "map": {
                    "basemap": {"style": "mapbox://styles/mapbox/streets-v12"},
                    "view": {"center": [0, 0], "zoom": 1},
                },
            }
        )
        validate_report_payload(s, config, user=user)  # no raise


def test_rejects_unreadable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        config = _report_config("does-not-exist")
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_rejects_bookmark_item_id_pointing_at_non_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Not a bookmark",
        )
        s.commit()
        config = _report_config(item.id)
        with pytest.raises(HTTPException) as exc:
            validate_report_payload(s, config, user=user)
        assert exc.value.status_code == 422


def test_accepts_readable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="bookmark",
            title="A view",
        )
        s.commit()
        config = _report_config(item.id)
        validate_report_payload(s, config, user=user)  # no raise


# --- Garde de capacité export sur POST/PUT /configs (revue finale SP-17b, I3) ---
# Sur une instance sans capacité export (défaut), un ReportSchedule pouvait
# être créé mais son rendu restait "pending" à jamais : rien ne dépile la file
# `export`, et export_repo.reclaim_stuck_jobs ne récupère que les "running".
# Jumeau de _require_etl_enabled_for_pipeline (kind="pipeline"/CORE_ETL_ENABLED).


def _client_and_tenant(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    db_url = f"sqlite+pysqlite:///{tmp_path / 'report_export_gate.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        bookmark = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="bookmark",
            title="A view",
        )
        app_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="app",
            title="Dashboard",
        )
        from app.configs import repository as configs_repo

        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "kind": "bookmark",
                    "bookmark": {
                        "appId": app_item.id,
                        "pageId": "page-1",
                        "timeRange": None,
                        "extent": None,
                        "crossFilter": {},
                    },
                }
            ),
            item_id=bookmark.id,
            tenant_id=tenant.id,
        )
        s.commit()
        bookmark_id = bookmark.id
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, bookmark_id


def _report_body(bookmark_item_id: str) -> dict:
    return {
        "title": "Weekly report",
        "config": {
            "kind": "report",
            "report": {
                "bookmarkItemId": bookmark_item_id,
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        },
    }


def test_create_report_is_rejected_when_export_capability_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    client, bookmark_id = _client_and_tenant(monkeypatch, tmp_path)

    resp = client.post("/configs", json=_report_body(bookmark_id))

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Export capability disabled on this instance"


def test_create_report_is_accepted_when_export_capability_is_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    client, bookmark_id = _client_and_tenant(monkeypatch, tmp_path)

    resp = client.post("/configs", json=_report_body(bookmark_id))

    assert resp.status_code == 201


def test_update_report_is_rejected_when_export_capability_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    client, bookmark_id = _client_and_tenant(monkeypatch, tmp_path)
    created = client.post("/configs", json=_report_body(bookmark_id))
    assert created.status_code == 201
    config_id = created.json()["id"]

    monkeypatch.setenv("CORE_EXPORT_ENABLED", "false")
    resp = client.put(f"/configs/{config_id}", json=_report_body(bookmark_id)["config"])

    assert resp.status_code == 403
    assert resp.json()["detail"] == "Export capability disabled on this instance"

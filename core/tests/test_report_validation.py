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
    return BuilderConfig.model_validate({
        "kind": "report",
        "report": {
            "bookmarkItemId": bookmark_item_id,
            "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    })


def test_ignores_non_report_kind():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        config = BuilderConfig.model_validate({
            "kind": "map",
            "map": {
                "basemap": {"style": "mapbox://styles/mapbox/streets-v12"},
                "view": {"center": [0, 0], "zoom": 1},
            }
        })
        validate_report_payload(s, config, user=user)  # no raise


def test_rejects_unreadable_bookmark():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Not a bookmark",
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
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="bookmark", title="A view",
        )
        s.commit()
        config = _report_config(item.id)
        validate_report_payload(s, config, user=user)  # no raise

# SPDX-License-Identifier: Apache-2.0
"""Même raisonnement que test_tileset3d_config_validation.py (I1, revue
finale de branche tileset3d hosting) : kind="terrain3d" n'a aucune voie de
création/mise à jour légitime par les routes /configs publiques."""

import pytest
from fastapi import HTTPException

from app.configs.schemas import BuilderConfig
from app.configs.terrain3d_validation import validate_terrain3d_payload
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _terrain3d_config(source_key: str = "other-tenant/abc/dem-cog.tif") -> BuilderConfig:
    return BuilderConfig.model_validate(
        {
            "kind": "terrain3d",
            "terrain3d": {"sourceKey": source_key, "originalFilename": "dem.tif"},
        }
    )


def _session_and_user():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    s = Session()
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
    s.commit()
    return s, user


def test_ignores_non_terrain3d_kind():
    s, user = _session_and_user()
    with s:
        config = BuilderConfig.model_validate(
            {
                "kind": "map",
                "map": {
                    "basemap": {"style": "mapbox://styles/mapbox/streets-v12"},
                    "view": {"center": [0, 0], "zoom": 1},
                },
            }
        )
        validate_terrain3d_payload(s, config, user=user)  # no raise


def test_rejects_any_terrain3d_payload():
    s, user = _session_and_user()
    with s:
        with pytest.raises(HTTPException) as exc:
            validate_terrain3d_payload(s, _terrain3d_config(), user=user)
        assert exc.value.status_code == 422


def _client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    db_url = f"sqlite+pysqlite:///{tmp_path / 'terrain3d_config_validation.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client


def _body() -> dict:
    return {"title": "DEM volé", "config": _terrain3d_config().model_dump(mode="json")}


def test_post_configs_with_kind_terrain3d_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    resp = client.post("/configs", json=_body())

    assert resp.status_code == 422
    assert resp.json()["detail"] == "terrain3d configs can only be created by the conversion task"

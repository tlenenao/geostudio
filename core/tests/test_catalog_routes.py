# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        setup_session.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    test_client = TestClient(app)
    yield test_client
    engine.dispose()


def test_metadata_catalog_lists_all_three_families(client):
    res = client.get("/v1/metadata-catalog")
    assert res.status_code == 200
    body = res.json()
    license_ids = {e["id"] for e in body["licenses"]}
    assert license_ids == {
        "etalab-2.0",
        "cc0-1.0",
        "cc-by-4.0",
        "cc-by-sa-4.0",
        "odbl-1.0",
        "proprietary",
        "other",
    }
    assert {e["id"] for e in body["frequencies"]} == {
        "continuous",
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "annual",
        "irregular",
    }
    assert {e["id"] for e in body["languages"]} == {"fr", "en", "de", "es", "it"}


def test_metadata_catalog_license_carries_dcat_and_spdx_ids(client):
    res = client.get("/v1/metadata-catalog")
    etalab = next(e for e in res.json()["licenses"] if e["id"] == "etalab-2.0")
    assert etalab["dcatUri"] == "https://spdx.org/licenses/etalab-2.0.html"
    assert etalab["spdxId"] == "etalab-2.0"


def test_metadata_catalog_requires_authentication():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    test_client = TestClient(app)
    res = test_client.get("/v1/metadata-catalog")
    assert res.status_code == 401
    engine.dispose()

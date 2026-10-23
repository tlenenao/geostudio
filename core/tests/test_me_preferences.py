# SPDX-License-Identifier: Apache-2.0
"""AUD-115 : préférences de langue/fuseau, claim JIT, erreurs 7807 localisées."""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
            locale="fr-FR",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    def current(session=Depends(db.get_session, scope="function")):
        return session.scalar(select(User))

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = current
    yield TestClient(app), Session
    engine.dispose()


def test_jit_claim_seeds_locale(env):
    client, _ = env
    assert client.get("/v1/me/preferences").json() == {"locale": "fr", "timezone": None}


def test_put_preferences_persists_and_validates(env):
    client, Session = env
    ok = client.put("/v1/me/preferences", json={"locale": "en", "timezone": "Europe/Paris"})
    assert ok.status_code == 200, ok.text
    assert client.get("/v1/me/preferences").json() == {"locale": "en", "timezone": "Europe/Paris"}
    with Session() as s:
        assert s.scalar(select(User)).timezone == "Europe/Paris"
    assert client.put("/v1/me/preferences", json={"timezone": "Mars/Base"}).status_code == 422
    assert client.put("/v1/me/preferences", json={"locale": "de"}).status_code == 422


def test_error_is_localized_only_on_request_and_carries_code(env):
    client, _ = env
    plain = client.get("/v1/does-not-exist-route").json()
    assert plain["title"] == "Not Found" and plain["code"] == "not_found"
    fr = client.get("/v1/does-not-exist-route", headers={"Accept-Language": "fr-FR,fr;q=0.9"})
    body = fr.json()
    assert body["title"] == "Introuvable" and body["detail"] == "Introuvable"
    assert body["code"] == "not_found"

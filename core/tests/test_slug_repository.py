# SPDX-License-Identifier: Apache-2.0
"""Résolution de slug côté repository (`create_item`, `slug_exists`,
`ensure_unique_slug`) — logique pure de sélection SQL, testée sur SQLite
(cf. task-2-report.md §Déviation pour la justification : ces 5 tests
n'exercent jamais l'index unique partiel Postgres, seulement le chemin
Python de résolution)."""

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as repo
from app.items.slug import InvalidSlugError, SlugCollisionError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-1",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    return tenant, user


def test_create_site_genere_slug_depuis_titre(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="site",
        title="Mon Portail",
    )
    assert item.slug == "mon-portail"


def test_create_site_collision_implicite_suffixe(session, tenant_and_user):
    tenant, user = tenant_and_user
    a = repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="site",
        title="Portail",
    )
    b = repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="site",
        title="Portail",
    )
    assert a.slug == "portail"
    assert b.slug == "portail-2"


def test_create_site_slug_fourni_collision_leve(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="site",
        title="X",
        slug="pris",
    )
    with pytest.raises(SlugCollisionError):
        repo.create_item(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="site",
            title="Y",
            slug="pris",
        )


def test_create_site_slug_fourni_invalide_leve(session, tenant_and_user):
    tenant, user = tenant_and_user
    with pytest.raises(InvalidSlugError):
        repo.create_item(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="site",
            title="Y",
            slug="Pas Valide",
        )


def test_create_non_site_slug_reste_null(session, tenant_and_user):
    tenant, user = tenant_and_user
    item = repo.create_item(
        session,
        tenant_id=tenant.id,
        owner_id=user.id,
        resource_type="app",
        title="Appli",
    )
    assert item.slug is None

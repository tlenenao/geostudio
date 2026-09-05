# SPDX-License-Identifier: Apache-2.0
"""Garde-fou permanent (GAP-64.2, SP-49) : le nombre de requêtes SQL de
`GET /harvest/layers`/`GET /harvest/feature-layers` ne doit pas croître avec
le nombre de couches — même patron que tests/test_items_no_nplus1.py.

Sans ce test, une implémentation qui appelle `items_repo.get_access_facts`
puis `can()` ligne par ligne passe tous les tests fonctionnels de
test_harvest_layers_endpoint.py/test_harvest_feature_layers_endpoint.py — et
ajoute jusqu'à deux requêtes par ligne à chaque affichage.

Le viewer n'est ni propriétaire ni bénéficiaire d'un item public/publié
(cf. `ItemShare` viewer via un groupe) : c'est la condition qui force `can()`
à consulter `roles_for_items` (le court-circuit owner/public/published
n'ajoute déjà aucune requête, donc ne prouverait rien ici)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _build(n_layers: int, *, feature: bool = False):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-owner",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        viewer = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-viewer",
            username="viewer",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=viewer.id, tenant_id=tenant.id))
        source = harvest_repo.create_source(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            type="wms",
            url="https://ows.example.com/wms",
            mode="reference",
            enabled=True,
            interval_minutes=None,
        )
        for i in range(n_layers):
            item = items_repo.create_item(
                s,
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_type="external",
                title=f"Layer {i}",
            )
            s.add(ItemShare(item_id=item.id, group_id="gv", tenant_id=tenant.id, role="viewer"))
            if feature:
                harvest_repo.create_record(
                    s,
                    tenant_id=tenant.id,
                    source_id=source.id,
                    external_id=f"f{i}",
                    item_id=item.id,
                    collection_id=None,
                    content_hash=None,
                    external_url=f"https://ows.example.com/wfs?layer={i}",
                    layer_kind="feature",
                )
            else:
                harvest_repo.create_record(
                    s,
                    tenant_id=tenant.id,
                    source_id=source.id,
                    external_id=f"r{i}",
                    item_id=item.id,
                    collection_id=None,
                    content_hash=None,
                    tiles_url=f"https://ows.example.com/wms?layer={i}",
                    layer_kind="raster",
                )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: viewer
    return engine, TestClient(app)


def _count_queries(engine, fn):
    seen = 0

    def bump(conn, cursor, statement, params, context, executemany):
        nonlocal seen
        seen += 1

    event.listen(engine, "before_cursor_execute", bump)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", bump)
    return seen


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_layers_query_count_does_not_grow_with_layer_count(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n)
        try:

            def call(client=client, n=n):
                response = client.get("/harvest/layers")
                assert response.status_code == 200, response.text
                assert len(response.json()["layers"]) == n

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec le nombre de couches : {counts} — "
        "c'est un N+1, probablement get_access_facts+can() appelés ligne par ligne"
    )


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_feature_layers_query_count_does_not_grow_with_layer_count(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n, feature=True)
        try:

            def call(client=client, n=n):
                response = client.get("/harvest/feature-layers")
                assert response.status_code == 200, response.text
                assert len(response.json()["layers"]) == n

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec le nombre de couches : {counts} — "
        "c'est un N+1, probablement get_access_facts+can() appelés ligne par ligne"
    )

# SPDX-License-Identifier: Apache-2.0
"""Garde-fou permanent : le nombre de requêtes SQL d'un `GET /items` ne doit
pas croître avec le nombre d'items de la page.

Sans ce test, une implémentation qui appelle `can()` ligne par ligne passe
tous les tests fonctionnels de `test_items_permissions.py` — et ajoute jusqu'à
deux requêtes par item à chaque affichage du catalogue.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items.models import Item
from app.main import create_app
from app.sharing.models import Group, GroupMember, ItemShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _build(n_items: int):
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
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-reader",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(id="gv", tenant_id=tenant.id, name="V", created_by=owner.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id="gv", user_id=reader.id, tenant_id=tenant.id))
        for i in range(n_items):
            s.add(
                Item(
                    id=f"i-{i}",
                    tenant_id=tenant.id,
                    owner_id=owner.id,
                    resource_type="app",
                    title=f"Item {i}",
                )
            )
        s.flush()
        for i in range(n_items):
            s.add(
                ItemShare(
                    item_id=f"i-{i}",
                    group_id="gv",
                    tenant_id=tenant.id,
                    role="viewer",
                )
            )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: reader
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
def test_query_count_does_not_grow_with_page_size(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n)
        try:

            def call(client=client, n=n):
                response = client.get(f"/v1/items?scope=all&pageSize={n}")
                assert response.status_code == 200, response.text
                assert len(response.json()["items"]) == n

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec la page : {counts} — "
        "c'est un N+1, probablement un can() appelé ligne par ligne"
    )

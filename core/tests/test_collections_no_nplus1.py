# SPDX-License-Identifier: Apache-2.0
"""Garde-fou permanent : le nombre de requêtes SQL d'un `GET /collections` ne
doit pas croître avec le nombre de collections. Pendant de
`test_items_no_nplus1.py` — la même classe de bug existait ici
(`_can_write_collection` appelé ligne par ligne dans `list_collections`),
jamais corrigée depuis SP-29a."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.sharing.models import CollectionShare, Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _build(n_collections: int):
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
        for i in range(n_collections):
            s.add(
                Collection(
                    id=f"c-{i}",
                    tenant_id=tenant.id,
                    owner_id=owner.id,
                    table_name=f"c_{i}",
                    title=f"Collection {i}",
                    pk_column="id",
                )
            )
        s.flush()
        for i in range(n_collections):
            s.add(
                CollectionShare(
                    collection_id=f"c-{i}",
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
    # list_collections (GET /collections) dépend de get_current_user_optional,
    # pas get_current_user (contrairement à list_items) — les deux sont
    # overridés par prudence, mais seul le premier est exercé par ce test.
    app.dependency_overrides[get_current_user] = lambda: reader
    app.dependency_overrides[get_current_user_optional] = lambda: reader
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
def test_query_count_does_not_grow_with_collection_count(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build(n)
        try:

            def call(client=client, n=n):
                response = client.get("/v1/collections")
                assert response.status_code == 200, response.text
                assert len(response.json()["collections"]) == n

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec le nombre de collections : {counts} — "
        "c'est un N+1, probablement _can_write_collection appelé ligne par ligne"
    )

# SPDX-License-Identifier: Apache-2.0
"""REV-279e : le filtre tag du catalogue public passe en SQL (jsonb @>) sur Postgres."""

import pytest
from sqlalchemy import event, text

from app.db import Base, make_session_factory
from app.items.models import Item
from app.items.repository import list_published_items
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    with make_session_factory(pg_engine)() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text("TRUNCATE items, users, tenants CASCADE"))


def test_tag_filter_runs_in_sql_on_postgres(pg_session, pg_engine):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    for item_id, title, keywords in (("i1", "Avec", ["eau", "air"]), ("i2", "Sans", ["air"])):
        pg_session.add(
            Item(
                id=item_id,
                tenant_id=tenant.id,
                owner_id=user.id,
                resource_type="app",
                title=title,
                keywords=keywords,
                is_published=True,
            )
        )
    pg_session.commit()
    statements = []

    def _capture(_conn, _cursor, statement, *_a):
        statements.append(statement)

    event.listen(pg_engine, "before_cursor_execute", _capture)
    try:
        page = list_published_items(pg_session, tenant_id=tenant.id, tag="eau")
    finally:
        event.remove(pg_engine, "before_cursor_execute", _capture)
    assert [i.title for i in page.items] == ["Avec"] and page.total == 1
    assert any("@>" in s for s in statements)

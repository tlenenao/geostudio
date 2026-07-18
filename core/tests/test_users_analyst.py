# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_new_user_defaults_to_not_analyst():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(s, tenant_id=t.id, oidc_sub="x", username="x",
                               email=None, first_name="", last_name="")
        assert u.is_analyst is False

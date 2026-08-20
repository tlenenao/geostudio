# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_analyst


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_new_user_defaults_to_not_analyst():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(
            s, tenant_id=t.id, oidc_sub="x", username="x", email=None, first_name="", last_name=""
        )
        assert u.is_analyst is False


def test_bootstrap_analyst_promotes_and_never_demotes():
    Session = _session()
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(
            s,
            tenant_id=t.id,
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
            bootstrap_analyst=True,
        )
        assert u.is_analyst is True
        # Un appel ultérieur sans bootstrap ne rétrograde pas.
        u2 = get_or_create_user(
            s,
            tenant_id=t.id,
            oidc_sub="x",
            username="x",
            email=None,
            first_name="",
            last_name="",
            bootstrap_analyst=False,
        )
        assert u2.is_analyst is True


def test_set_analyst_toggles():
    Session = _session()
    with Session() as s:
        t = get_or_create_default_tenant(s)
        u = get_or_create_user(
            s, tenant_id=t.id, oidc_sub="y", username="y", email=None, first_name="", last_name=""
        )
        set_analyst(s, tenant_id=t.id, user_id=u.id, is_analyst=True)
        assert u.is_analyst is True
        set_analyst(s, tenant_id=t.id, user_id=u.id, is_analyst=False)
        assert u.is_analyst is False
        assert set_analyst(s, tenant_id=t.id, user_id="nope", is_analyst=True) is None

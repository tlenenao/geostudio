import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import count_admins, get_or_create_user, set_admin


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def _user(session, sub="sub-1", bootstrap_admin=False):
    tenant = get_or_create_default_tenant(session)
    return get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub=sub, username=sub,
        email=None, first_name="", last_name="", bootstrap_admin=bootstrap_admin,
    )


def test_bootstrap_promotes(session):
    user = _user(session, bootstrap_admin=True)
    assert user.is_admin is True


def test_bootstrap_never_demotes(session):
    user = _user(session, bootstrap_admin=True)
    again = _user(session, bootstrap_admin=False)  # sub retiré de l'env ensuite
    assert again.id == user.id and again.is_admin is True


def test_set_admin_and_count(session):
    tenant = get_or_create_default_tenant(session)
    user = _user(session)
    assert count_admins(session, tenant_id=tenant.id) == 0
    updated = set_admin(session, tenant_id=tenant.id, user_id=user.id, is_admin=True)
    assert updated.is_admin is True
    assert count_admins(session, tenant_id=tenant.id) == 1
    assert set_admin(session, tenant_id=tenant.id, user_id="nope", is_admin=True) is None

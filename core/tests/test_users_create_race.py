# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users import repository as repo
from app.users.models import User

KW = dict(username="alice", email=None, first_name="A", last_name="B")


def test_concurrent_first_login_returns_existing_user(monkeypatch):
    """Course TOCTOU : un autre login a committé le même sub entre notre SELECT
    et notre INSERT -> on relit l'existant, sans InvalidRequestError (500 vu en CI)."""
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        tenant = get_or_create_default_tenant(s)
        winner = repo.get_or_create_user(s, tenant_id=tenant.id, oidc_sub="sub-1", **KW)
        calls = {"n": 0}
        real = s.scalar

        def blind_first_lookup(stmt, *a, **k):
            if "FROM users" in str(stmt) and calls["n"] == 0:
                calls["n"] += 1
                return None  # le SELECT initial ne voit pas le gagnant
            return real(stmt, *a, **k)

        monkeypatch.setattr(s, "scalar", blind_first_lookup)
        loser = repo.get_or_create_user(s, tenant_id=tenant.id, oidc_sub="sub-1", **KW)
        assert loser.id == winner.id
        assert len(s.scalars(select(User)).all()) == 1
    engine.dispose()

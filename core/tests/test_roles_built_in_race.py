# SPDX-License-Identifier: Apache-2.0
"""Course TOCTOU de `ensure_built_in_roles` : la requête perdante ne doit pas
échouer (flake CI test_copilot_routes, 2026-10-09 : `InvalidRequestError:
Instance <Role> is not present in this Session`)."""

from app.db import init_db, make_engine, make_session_factory
from app.roles import repository
from app.roles.privileges import BUILT_IN_ROLE_PRIVILEGES
from app.tenants.repository import get_or_create_default_tenant


def test_losing_the_race_returns_the_winners_roles(monkeypatch):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    factory = make_session_factory(engine)

    with factory() as winner:
        tenant_id = get_or_create_default_tenant(winner).id
        repository.ensure_built_in_roles(winner, tenant_id=tenant_id)
        winner.commit()

    real = repository._existing_built_in_roles
    calls = {"n": 0}

    def stale_first_read(session, *, tenant_id):
        calls["n"] += 1
        return {} if calls["n"] == 1 else real(session, tenant_id=tenant_id)

    monkeypatch.setattr(repository, "_existing_built_in_roles", stale_first_read)
    with factory() as loser:
        roles = repository.ensure_built_in_roles(loser, tenant_id=tenant_id)
        loser.commit()
    assert set(roles) == set(BUILT_IN_ROLE_PRIVILEGES)

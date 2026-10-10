# SPDX-License-Identifier: Apache-2.0
"""REV-310 : la garde « un seul run actif par pipeline » est ATOMIQUE — deux
créations simultanées (SELECT puis INSERT sans verrou laisseraient passer les
deux) ne produisent qu'un run. Nécessite Postgres (verrou advisory)."""

import threading

import pytest

from app.db import Base, make_session_factory
from app.items.repository import create_item
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

_N = 6


def test_concurrent_creations_yield_exactly_one_active_run(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="run-conc",
            username="run-conc",
            email=None,
            first_name="",
            last_name="",
        )
        item = create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="pipeline", title="Conc"
        )
        s.commit()
        tenant_id, item_id = tenant.id, item.id

    barrier = threading.Barrier(_N)
    outcomes: list[str] = []

    def worker() -> None:
        with Session() as s:
            barrier.wait()
            try:
                pipelines_repo.create_run_unless_active(
                    s, tenant_id=tenant_id, pipeline_item_id=item_id
                )
                s.commit()
                outcomes.append("created")
            except pipelines_repo.PipelineRunActive:
                s.rollback()
                outcomes.append("refused")

    threads = [threading.Thread(target=worker) for _ in range(_N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["created"] + ["refused"] * (_N - 1)

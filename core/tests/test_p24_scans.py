# SPDX-License-Identifier: Apache-2.0
"""P24 : plans sans SCAN (modèles) et compteur de requêtes (pas de temps mur,
piège n°7)."""

import uuid

import pytest
from sqlalchemy import event, text

from app.configs.models import Config, ConfigRevision
from app.configs.repository import list_configs_by_kind, list_configs_by_kind_and_tenant
from app.db import init_db, make_engine
from app.tenants.models import Tenant


@pytest.fixture()
def engine():
    eng = make_engine("sqlite+pysqlite:///:memory:")
    init_db(eng)
    yield eng
    eng.dispose()


PLANS = {
    "audit_log": "SELECT * FROM audit_log WHERE tenant_id='t' AND created_at >= '2026-01-01'",
    "config_revisions": "SELECT * FROM config_revisions WHERE config_id='c' ORDER BY version DESC",
    "configs": "SELECT * FROM configs WHERE item_id='i'",
    "configs_kind": "SELECT * FROM configs WHERE kind='alert' AND tenant_id='t'",
    "report_runs": "SELECT * FROM report_runs WHERE tenant_id='t' AND report_item_id='r' "
    "ORDER BY created_at DESC LIMIT 1",
}


@pytest.mark.parametrize("name", PLANS)
def test_no_full_scan(engine, name):
    with engine.connect() as c:
        plan = " | ".join(r[-1] for r in c.execute(text("EXPLAIN QUERY PLAN " + PLANS[name])))
    assert "SEARCH" in plan and "SCAN" not in plan, plan


def test_list_configs_by_kind_is_one_query(engine):
    from sqlalchemy.orm import Session

    with Session(engine) as s:
        s.execute(text("PRAGMA foreign_keys=OFF"))  # items non nécessaires à ce test
        s.add(Tenant(id="t", slug="t", name="t"))
        s.flush()
        for n in range(5):
            cid = uuid.uuid4().hex
            s.add(Config(id=cid, tenant_id="t", kind="alert", item_id=f"i{n}", current_version=2))
            s.add(ConfigRevision(tenant_id="t", config_id=cid, version=1, data={"kind": "alert"}))
            s.add(ConfigRevision(tenant_id="t", config_id=cid, version=2, data={"kind": "alert"}))
        s.commit()
        count = 0

        def _inc(*_a, **_k):
            nonlocal count
            count += 1

        event.listen(engine, "before_cursor_execute", _inc)
        list_configs_by_kind(s, "alert")
        list_configs_by_kind_and_tenant(s, kind="alert", tenant_id="t")
        event.remove(engine, "before_cursor_execute", _inc)
    assert count == 2  # 1 par appel, indépendamment du nombre de configs

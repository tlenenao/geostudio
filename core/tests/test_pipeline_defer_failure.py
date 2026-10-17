# SPDX-License-Identifier: Apache-2.0
"""AUD-025 : un `defer()` définitivement échoué ne doit pas laisser un run
`pending` qui bloque tout nouveau run en 409."""

import pytest
from fastapi import HTTPException

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import service
from app.pipelines.models import PipelineRun
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

CONFIG = {
    "version": 1,
    "kind": "pipeline",
    "pipeline": {
        "nodes": [
            {
                "id": "r1",
                "kind": "reader",
                "op": "reader.collection",
                "params": {"collectionId": "x"},
            },
            {
                "id": "w1",
                "kind": "writer",
                "op": "writer.export",
                "params": {"format": "csv", "key": "o.csv"},
            },
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    },
}


def test_failed_defer_marks_run_failed_and_does_not_block_next_run(monkeypatch):
    monkeypatch.setattr("app.jobs.defer.time.sleep", lambda _s: None)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session = make_session_factory(engine)()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="u",
        username="u",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=True,
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="P"
    )
    configs_repo.create_config(
        session, BuilderConfig.model_validate(CONFIG), item_id=item.id, tenant_id=tenant.id
    )
    session.commit()

    def down(run_id, tenant_id):
        raise RuntimeError("down")

    with pytest.raises(HTTPException) as e:
        service.run_pipeline_service(session, user=user, item_id=item.id, defer_task=down)
    assert e.value.status_code == 503
    run = session.query(PipelineRun).one()
    assert run.status == "failed" and "mise en file" in run.error

    # pas de 409 : le run précédent n'est plus actif
    run_id = service.run_pipeline_service(
        session, user=user, item_id=item.id, defer_task=lambda *_: None
    )
    assert session.get(PipelineRun, run_id).status == "queued"

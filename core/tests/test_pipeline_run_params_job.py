# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F3 : le worker applique les paramètres du run (postgis)."""

import pytest
from sqlalchemy import text

from app.configs.schemas import PipelinePayload
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from tests.test_pipeline_jobs import env  # noqa: F401  (fixture partagée)

pytestmark = pytest.mark.postgis


def param_payload():
    return PipelinePayload.model_validate(
        {
            "parameters": [{"name": "min", "type": "integer", "default": 5}],
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.collection",
                    "params": {"collectionId": "villes"},
                },
                {
                    "id": "t1",
                    "kind": "transform",
                    "op": "transform.filter",
                    "params": {"expr": "pop >= {{param.min}}"},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.collection",
                    "params": {"collectionId": "villes_propres", "mode": "replace"},
                },
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "w1"},
            ],
        }
    )


@pytest.mark.parametrize(
    ("params", "expected_rows"),
    [({"min": 11}, 0), ({"min": 10}, 1), (None, 1)],  # None -> défaut 5
)
def test_run_pipeline_task_applies_run_params(env, monkeypatch, params, expected_rows):  # noqa: F811
    app, Session, tenant, user, item_id = env
    monkeypatch.setattr(
        pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: param_payload()
    )
    with Session() as s:
        run = pipelines_repo.create_run(
            s, tenant_id=tenant.id, pipeline_item_id=item_id, params=params
        )
        s.commit()
        run_id = run.id
    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])
    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "succeeded", fetched.error
        assert s.execute(text("SELECT count(*) FROM villes_propres")).scalar() == expected_rows
        assert fetched.params == params

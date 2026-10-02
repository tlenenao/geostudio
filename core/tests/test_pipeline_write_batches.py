# SPDX-License-Identifier: Apache-2.0
"""writer.collection en lots (P18.03/05, t03b-001/009) : requêtes groupées,
progression par lot, annulation, trace audit (c03-003)."""

import math

import pytest
from sqlalchemy import event, select, text

from app.audit.models import AuditLog
from app.collections.ddl import apply_collection_ddl
from app.configs.schemas import PipelinePayload
from app.db import Base, make_session_factory
from app.items import repository as items_repo  # noqa: F401
from app.pipelines import runtime
from app.pipelines.errors import PipelineCancelledError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_pipeline_runtime import (
    _no_masking_by_default,  # noqa: F401
    _row,
    _table_info_for,
    _write_partition,
)

N = 5000  # 3 lots de 2000

_PAYLOAD = {
    "nodes": [
        {
            "id": "r1",
            "kind": "reader",
            "op": "reader.collection",
            "params": {"collectionId": "villes"},
        },
        {
            "id": "w1",
            "kind": "writer",
            "op": "writer.collection",
            "params": {"collectionId": "villes_batch"},
        },
    ],
    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
}


@pytest.fixture()
def setup(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )  # fmt: skip
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, geometry_column, is_public, editable, "
                "created_at, updated_at) VALUES ('villes_batch', :t, :o, 'villes_batch', "
                "'V', '', 'id', 'geometry', false, true, now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE villes_batch (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
            )
        )
        apply_collection_ddl(s, "villes_batch")
        s.commit()
        _write_partition(
            tmp_path,
            tenant_id=tenant.id,
            rows=[_row(i, "R", i, x=1.0, y=45.0) for i in range(N)],
        )
        monkeypatch.setattr(
            runtime, "_table_info_for_collection", lambda session, cid: _table_info_for(cid)
        )
        monkeypatch.setattr(
            runtime,
            "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )
        yield s, tenant, user, tmp_path
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "DROP TABLE villes_batch; TRUNCATE items, configs, config_revisions, "
                "collections, audit_log, users, tenants CASCADE"
            )
        )


def _run(s, tenant, user, tmp_path, **kw):
    return runtime.run_pipeline(
        s,
        payload=PipelinePayload.model_validate(_PAYLOAD),
        tenant_id=tenant.id,
        user=user,
        endpoint_url="http://localhost:9000",
        access_key="x",
        secret_key="y",
        base_uri=str(tmp_path),
        **kw,
    )


@pytest.mark.postgis
def test_write_is_batched_with_progress_and_audit(setup):
    s, tenant, user, tmp_path = setup
    inserts: list[str] = []

    @event.listens_for(s.get_bind(), "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith('INSERT INTO PUBLIC."VILLES_BATCH"') or (
            "villes_batch" in statement and statement.lstrip().upper().startswith("INSERT")
        ):
            inserts.append(statement)

    progress: list[int] = []
    _run(s, tenant, user, tmp_path, on_progress=lambda st: progress.append(st.rowCount))
    s.commit()

    assert s.execute(text("SELECT count(*) FROM villes_batch")).scalar() == N
    # Piège n°7 : on compte des requêtes, pas des secondes — 1 INSERT par lot, pas par ligne.
    assert len(inserts) == math.ceil(N / runtime._WRITE_BATCH_SIZE)
    assert progress == [2000, 4000, 5000]
    audit = s.execute(
        select(AuditLog).where(AuditLog.action == "collection.pipeline_write")
    ).scalar_one()
    assert audit.payload["rows"] == N and audit.payload["mode"] == "append"


@pytest.mark.postgis
def test_cancel_between_batches_rolls_back_the_write(setup):
    s, tenant, user, tmp_path = setup
    with pytest.raises(PipelineCancelledError):
        _run(s, tenant, user, tmp_path, should_cancel=lambda: True)
    s.rollback()
    assert s.execute(text("SELECT count(*) FROM villes_batch")).scalar() == 0

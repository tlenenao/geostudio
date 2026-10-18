# SPDX-License-Identifier: Apache-2.0
"""collect_client_ops (L8 T1) : réservation unique par (tenant, collection, acteur, kind, op),
rejeu = résultat d'origine, rétention."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.collect import repository as ops
from app.collect.models import CollectClientOp
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="a",
            email=None,
            first_name="",
            last_name="",
        )
        for cid in ("c1", "c2"):
            s.add(
                Collection(
                    id=cid,
                    tenant_id=tenant.id,
                    owner_id=user.id,
                    table_name=cid,
                    title=cid,
                    pk_column="id",
                )
            )
        s.commit()
        yield s, tenant.id, user.id


def _claim(s, tenant, actor, **kw):
    args = dict(
        tenant_id=tenant, collection_id="c1", actor_id=actor, kind="feature", client_op_id="op-1"
    )
    args.update(kw)
    return ops.claim(s, **args)


def test_first_claim_then_replay_returns_recorded_result(env):
    s, tenant, actor = env
    row, replay = _claim(s, tenant, actor)
    assert replay is False
    ops.record_result(s, row, {"fid": 7})
    again, replay = _claim(s, tenant, actor)
    assert replay is True
    assert again.result == {"fid": 7}


def test_other_actor_collection_or_kind_is_a_distinct_operation(env):
    s, tenant, actor = env
    _claim(s, tenant, actor)
    for kw in ({"actor_id": "someone-else"}, {"collection_id": "c2"}, {"kind": "attachment"}):
        _, replay = _claim(s, tenant, actor, **kw)
        assert replay is False


def test_purge_expired_keeps_recent_rows(env):
    s, tenant, actor = env
    old, _ = _claim(s, tenant, actor, client_op_id="old")
    _claim(s, tenant, actor, client_op_id="new")
    old.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31)
    s.flush()
    assert ops.purge_expired(s) == 1
    assert s.scalar(select(func.count()).select_from(CollectClientOp)) == 1

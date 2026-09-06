# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from app.audit.writer import write_audit
from app.db import init_db, make_engine, make_session_factory
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.usage.service import JOB_AUDIT_ACTIONS, list_tasks, summarize
from app.users.repository import get_or_create_user


def _seed(s, *, tenant_id, actor_id, action, object_type="pipeline", object_id="p1"):
    write_audit(
        s,
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_kind="user",
        action=action,
        object_type=object_type,
        object_id=object_id,
    )


def test_list_tasks_filters_to_job_actions_and_tenant():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        # FK réelle (audit_log.tenant_id -> tenants.id, PRAGMA foreign_keys=ON
        # sur ce moteur sqlite) : un id de tenant bidon ferait échouer le
        # commit, il faut un second tenant réel pour le bruit cross-tenant.
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_tenant_id = other_tenant.id
        # bruit : action non-job du même tenant, et action job d'un AUTRE tenant
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="config.update")
        _seed(s, tenant_id=other_tenant_id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u2", action="export.run")
        s.commit()

        rows, total = list_tasks(s, tenant_id=tenant.id, page=1, page_size=50)
        assert total == 2
        assert {r.action for r in rows} == {"pipeline.run", "export.run"}
        assert all(r.tenant_id == tenant.id for r in rows)


def test_list_tasks_scopes_to_one_actor_when_requested():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run")
        _seed(s, tenant_id=tenant.id, actor_id="u2", action="pipeline.run")
        s.commit()

        rows, total = list_tasks(s, tenant_id=tenant.id, actor_id="u1", page=1, page_size=50)
        assert total == 1
        assert rows[0].actor_id == "u1"


def test_list_tasks_paginates_and_orders_newest_first():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        for i in range(3):
            _seed(s, tenant_id=tenant.id, actor_id="u1", action="pipeline.run", object_id=f"p{i}")
        s.commit()

        page1, total = list_tasks(s, tenant_id=tenant.id, page=1, page_size=2)
        assert total == 3
        assert len(page1) == 2
        page2, _ = list_tasks(s, tenant_id=tenant.id, page=2, page_size=2)
        assert len(page2) == 1
        # tri décroissant sur created_at : id auto-incrément croissant sert de
        # témoin d'ordre d'insertion sur sqlite (même seconde possible)
        assert page1[0].id > page1[1].id


def test_summarize_aggregates_by_actor_and_resource_across_all_actions():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="s1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        _seed(
            s,
            tenant_id=tenant.id,
            actor_id="u-inconnu",
            action="config.update",
            object_type="collection",
            object_id="c1",
        )
        _seed(
            s,
            tenant_id=tenant.id,
            actor_id="u-inconnu",
            action="config.update",
            object_type="collection",
            object_id="c1",
        )
        _seed(
            s,
            tenant_id=tenant.id,
            actor_id="u-inconnu",
            action="feature.create",
            object_type="collection",
            object_id="c2",
        )
        s.commit()

        now = datetime.now(UTC)
        summary = summarize(
            s,
            tenant_id=tenant.id,
            since=now - timedelta(days=1),
            until=now + timedelta(days=1),
            limit=10,
        )
        assert summary.total_actions == 3
        by_actor = {a.actor_id: a.count for a in summary.by_actor}
        assert by_actor["u-inconnu"] == 3
        by_resource = {(r.object_type, r.object_id): r.count for r in summary.by_resource}
        assert by_resource[("collection", "c1")] == 2
        assert by_resource[("collection", "c2")] == 1


def test_job_audit_actions_excludes_lifecycle_and_crud_actions():
    # garde-fou : ces actions ne doivent JAMAIS entrer dans la vue "tâches"
    for excluded in ("tileset3d.purge", "analytics.sql", "config.update", "role.create"):
        assert excluded not in JOB_AUDIT_ACTIONS
    for included in ("pipeline.run", "export.run", "ingestion.job_create"):
        assert included in JOB_AUDIT_ACTIONS

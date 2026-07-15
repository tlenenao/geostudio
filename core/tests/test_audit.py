# SPDX-License-Identifier: Apache-2.0
from sqlalchemy import select

from app.audit.models import AuditLog
from app.audit.writer import write_audit
from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant


def test_write_audit_persists_a_row():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            write_audit(
                session,
                tenant_id=tenant.id,
                actor_id="user-1",
                actor_kind="user",
                action="config.create",
                object_type="config",
                object_id="config-1",
                payload={"title": "My App"},
            )
            # Writer only flushes; commit to persist across the session
            # boundary this test deliberately crosses.
            session.commit()

        with Session() as session:
            rows = session.scalars(select(AuditLog)).all()
            assert len(rows) == 1
            assert rows[0].action == "config.create"
            assert rows[0].payload == {"title": "My App"}
    finally:
        engine.dispose()

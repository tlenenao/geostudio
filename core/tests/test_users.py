from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_get_or_create_user_creates_then_refreshes():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            created = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice", email="alice@example.com",
                first_name="Alice", last_name="Doe",
            )
            assert created.username == "alice"
            # Repository only flushes; commit to persist across the session
            # boundary this test deliberately crosses.
            session.commit()

        with Session() as session:
            tenant = get_or_create_default_tenant(session)
            refreshed = get_or_create_user(
                session, tenant_id=tenant.id, oidc_sub="sub-1",
                username="alice2", email="alice@example.com",
                first_name="Alice", last_name="Doe",
            )
            assert refreshed.id == created.id
            assert refreshed.username == "alice2"
    finally:
        engine.dispose()

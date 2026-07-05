from app.db import make_engine, make_session_factory, init_db
from app.tenants.repository import get_or_create_default_tenant


def test_get_or_create_default_tenant_is_idempotent():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    try:
        with Session() as session:
            first = get_or_create_default_tenant(session)
            assert first.slug == "default"

        with Session() as session:
            second = get_or_create_default_tenant(session)
            assert second.id == first.id
    finally:
        engine.dispose()

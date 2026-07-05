from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if "memory" in url and url.startswith("sqlite"):
        # StaticPool ensures all threads share the single in-memory connection,
        # which is required when TestClient runs the ASGI handler in a worker thread.
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        engine = create_engine(url, connect_args=connect_args)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    # Import models so they register on Base.metadata before create_all.
    from app.audit import models as audit_models  # noqa: F401
    from app.configs import models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.tenants import models as tenants_models  # noqa: F401
    from app.users import models as users_models  # noqa: F401

    # Alembic migrations (core/alembic/versions/) are the sole source of truth
    # for schema on real databases (Postgres). create_all() is only safe/used
    # for the fast-test and local-dev SQLite path, where there is no migration
    # history to conflict with. Running it against Postgres too would race
    # with `alembic upgrade head`: whichever runs second fails with
    # "relation already exists".
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)


def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")

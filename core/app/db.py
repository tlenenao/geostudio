# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from contextlib import contextmanager

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


def core_table_names() -> frozenset[str]:
    """Noms des tables du cœur, calculés APRÈS import de tous les modules
    models. Les imports paresseux sont indispensables : un appelant peut être
    importé avant app.items/app.configs (ordre alphabétique dans main.py), et
    ``Base.metadata`` ne connaît que les modèles déjà importés. Source de
    vérité de la denylist du registre de collections."""
    from app.alerts import models as alerts_models  # noqa: F401
    from app.appexport import models as appexport_models  # noqa: F401
    from app.audit import models as audit_models  # noqa: F401
    from app.collections import models as collections_models  # noqa: F401
    from app.configs import models  # noqa: F401
    from app.export import models as export_models  # noqa: F401
    from app.extensions import models as extensions_models  # noqa: F401
    from app.harvest import models as harvest_models  # noqa: F401
    from app.ingestion import models as ingestion_models  # noqa: F401
    from app.items import models as items_models  # noqa: F401
    from app.pipelines import models as pipelines_models  # noqa: F401
    from app.reports import models as reports_models  # noqa: F401
    from app.secrets import models as secrets_models  # noqa: F401
    from app.sharing import models as sharing_models  # noqa: F401
    from app.tenants import models as tenants_models  # noqa: F401
    from app.terrain3d import models as terrain3d_models  # noqa: F401
    from app.tileset3d import models as tileset3d_models  # noqa: F401
    from app.users import models as users_models  # noqa: F401

    return frozenset(Base.metadata.tables)


def init_db(engine: Engine) -> None:
    # Import models (via core_table_names) so they register on Base.metadata
    # before create_all.
    core_table_names()

    # Alembic migrations (core/alembic/versions/) are the sole source of truth
    # for schema on real databases (Postgres). create_all() is only safe/used
    # for the fast-test and local-dev SQLite path, where there is no migration
    # history to conflict with. Running it against Postgres too would race
    # with `alembic upgrade head`: whichever runs second fails with
    # "relation already exists".
    if engine.dialect.name == "sqlite":
        Base.metadata.create_all(engine)


@contextmanager
def request_scoped_session(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Own the transaction boundary for one request/test.

    Repository/writer functions never commit themselves — they only
    ``flush()`` within the open transaction. This wrapper commits once when
    the block completes successfully, or rolls back everything on any
    exception, so a mid-request failure can never leave a partial write
    (e.g. an orphaned Item with no linked Config).
    """
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")

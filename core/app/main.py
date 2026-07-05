import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import db
from app.auth import routes as auth_routes
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import routes as items_routes


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    def get_session() -> Iterator[Session]:
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session

    app.include_router(configs_routes.router)
    app.include_router(items_routes.router)
    app.include_router(auth_routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

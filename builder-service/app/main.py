import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import routes
from app.db import init_db, make_engine, make_session_factory


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[routes.get_session] = get_session
    app.include_router(routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

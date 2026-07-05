import logging
import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import db
from app.auth import routes as auth_routes
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory
from app.items import routes as items_routes


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session

    geonode_url = os.environ.get("GEONODE_BASE_URL")
    geonode_token = os.environ.get("GEONODE_TOKEN")
    if geonode_url and geonode_token:
        from app.geonode import GeoNodeItemClient

        geonode_client = GeoNodeItemClient(geonode_url, geonode_token)
        app.dependency_overrides[configs_routes.get_item_client] = lambda: geonode_client
    else:
        logging.getLogger("uvicorn.error").warning(
            "GEONODE_BASE_URL/GEONODE_TOKEN not set; item creation uses the in-memory stub."
        )

    app.include_router(auth_routes.router)
    app.include_router(configs_routes.router)
    app.include_router(items_routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

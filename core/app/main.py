import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import db
from app.auth import routes as auth_routes
from app.configs import routes as configs_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import routes as items_routes
from app.public import routes as public_routes
from app.sharing import routes as sharing_routes


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
    app.include_router(sharing_routes.router)
    app.include_router(public_routes.router)

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL")
    s3_access_key = os.environ.get("S3_ACCESS_KEY")
    s3_secret_key = os.environ.get("S3_SECRET_KEY")
    s3_bucket = os.environ.get("S3_THUMBNAILS_BUCKET", "geostudio-thumbnails")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.items.storage import S3ThumbnailStore

        app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: S3ThumbnailStore(
            endpoint_url=s3_endpoint, access_key=s3_access_key,
            secret_key=s3_secret_key, bucket=s3_bucket,
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

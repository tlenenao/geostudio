# SPDX-License-Identifier: Apache-2.0
import contextlib
import os
import re
from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import db, observability
from app.auth import routes as auth_routes
from app.auth.dependency import is_read_only_mode
from app.collections import routes as collections_routes
from app.configs import routes as configs_routes
from app.dcat import routes as dcat_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.extensions import routes as extensions_routes
from app.features import routes as features_routes
from app.ingestion import routes as ingestion_routes
from app.instance import routes as instance_routes
from app.items import routes as items_routes
from app.mcp.server import create_mcp_server
from app.public import routes as public_routes
from app.schemas_routes import router as schemas_router
from app.sharing import routes as sharing_routes
from app.stac import routes as stac_routes

_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")


def create_app() -> FastAPI:
    observability.setup()
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    observability.instrument_engine(engine)
    observability.register_jobs_backlog_gauge(engine)
    init_db(engine)
    session_factory = make_session_factory(engine)

    base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    # Deliberately not memoized process-wide: create_app() is called exactly
    # once in production (module import below), but the test suite calls it
    # repeatedly with different CORE_AUTH_MODE/CORE_OIDC_ISSUER per test —
    # a cached singleton would freeze the FIRST call's TokenVerifier/issuer
    # for the rest of the process and silently ignore later env changes.
    mcp_server = create_mcp_server(base_url, session_factory)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        async with mcp_server.session_manager.run():
            yield

    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0", lifespan=lifespan)
    observability.instrument_app(app)

    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and request.url.path != "/analytics/sql"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Mode démo : lecture seule, écritures désactivées."},
            )
        return await call_next(request)

    def get_session() -> Iterator[Session]:
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session

    app.include_router(configs_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(instance_routes.router)
    app.include_router(items_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(sharing_routes.router)
    app.include_router(public_routes.router)
    app.include_router(schemas_router)
    app.include_router(collections_routes.router)
    app.include_router(features_routes.router)
    app.include_router(ingestion_routes.router)
    app.include_router(stac_routes.router)
    app.include_router(dcat_routes.router)

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

    s3_uploads_bucket = os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.ingestion.storage import make_s3_client

        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint, access_key=s3_access_key, secret_key=s3_secret_key,
        )
        app.dependency_overrides[ingestion_routes.get_uploads_bucket] = lambda: s3_uploads_bucket

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Mounted last: streamable_http_app() already bakes in its own full
    # paths ("/mcp", "/.well-known/oauth-protected-resource/mcp") rather
    # than paths relative to a mount prefix, so it must be mounted at "/"
    # (not "/mcp", which would double the segment to "/mcp/mcp"). Starlette
    # matches routes in registration order and a root Mount matches any
    # path as a prefix, so it must come after every app-specific route
    # above or it would shadow them (e.g. swallow "/health").
    app.mount("/", mcp_server.streamable_http_app())

    return app


app = create_app()

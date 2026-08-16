# SPDX-License-Identifier: Apache-2.0
import contextlib
import os
import re
from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app import db, observability
from app.alerts import routes as alerts_routes
from app.appexport import routes as appexport_routes
from app.auth import routes as auth_routes
from app.auth.dependency import (
    is_appexport_enabled, is_copilot_enabled, is_etl_enabled, is_export_enabled,
    is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)
from app.collections import dataset_validation as collections_dataset_validation  # noqa: F401
from app.harvest import dataset_validation as harvest_dataset_validation  # noqa: F401
from app.pipelines import config_validation as pipelines_config_validation  # noqa: F401
from app.collections import routes as collections_routes
from app.configs import routes as configs_routes
from app.copilot import routes as copilot_routes
from app.dcat import routes as dcat_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.export import routes as export_routes
from app.extensions import routes as extensions_routes
from app.features import routes as features_routes
from app.harvest import routes as harvest_routes
from app.ingestion import routes as ingestion_routes
from app.instance import routes as instance_routes
from app.items import routes as items_routes
from app.mcp.server import create_mcp_server
from app.pipelines import routes as pipelines_routes
from app.public import routes as public_routes
from app.reports import routes as reports_routes
from app.secrets import crypto as secrets_crypto
from app.secrets import routes as secrets_routes
from app.schemas_routes import router as schemas_router
from app.sharing import routes as sharing_routes
from app.stac import routes as stac_routes
from app.terrain3d import routes as terrain3d_routes
from app.tileset3d import routes as tileset3d_routes

_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")
_EXPORT_PATH_RE = re.compile(
    r"^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$|^/export$|^/app-exports$"
)
# CORS narrow allowlist (SP-18b) : uniquement les endpoints déjà
# anonymes-capables (get_current_user_optional) qu'un bundle d'export
# Connecté appelle en direct depuis un domaine tiers arbitraire — jamais
# toute l'API. Wildcard origin sûr ici précisément parce qu'aucune
# credential/cookie ne traverse cette frontière (Bearer-ou-rien).
#
# Path-only : sert uniquement à décider si une requête OPTIONS de preflight
# doit recevoir un 204 CORS. Un navigateur envoie toujours OPTIONS pour
# précéder une requête réelle qu'il ne connaît pas encore (méthode incluse) :
# le preflight ne doit donc être gated que par chemin, jamais par méthode —
# c'est la requête réelle qui, elle, est gated par méthode+chemin ci-dessous
# (_APPEXPORT_CORS_RULES) pour ne jamais exposer les endpoints d'écriture ou
# admin-only qui partagent le même préfixe de chemin (ex. POST /collections,
# GET /collections/candidates, PATCH/DELETE /collections/{id}).
_APPEXPORT_CORS_PATH_RE = re.compile(
    r"^/collections(/[^/]+)?$"
    r"|^/collections/[^/]+/schema$"
    r"|^/collections/[^/]+/items(/[^/]+)?$"
    r"|^/collections/[^/]+/aggregate$"
    r"|^/extensions$"
    r"|^/public/items$"
)

# Méthode+chemin exacts pour les requêtes réelles (non-preflight) : c'est ce
# qui empêche effectivement POST /collections, GET /collections/candidates,
# PATCH/DELETE /collections/{id} et les écritures sous .../items de recevoir
# Access-Control-Allow-Origin, même si leur chemin matche le regex path-only
# ci-dessus. "candidates" est explicitement exclu de la branche {id} : c'est
# un chemin statique admin-only (GET /collections/candidates,
# app/collections/routes.py) qui partage la même forme /collections/<segment>
# qu'un id de collection réel.
_APPEXPORT_CORS_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^/collections$"), "GET"),
    (re.compile(r"^/collections/(?!candidates$)[^/]+$"), "GET"),
    (re.compile(r"^/collections/[^/]+/schema$"), "GET"),
    (re.compile(r"^/collections/[^/]+/items$"), "GET"),
    (re.compile(r"^/collections/[^/]+/items/[^/]+$"), "GET"),
    (re.compile(r"^/collections/[^/]+/aggregate$"), "POST"),
    (re.compile(r"^/extensions$"), "GET"),
    (re.compile(r"^/public/items$"), "GET"),
)


def create_app() -> FastAPI:
    observability.setup()
    secrets_crypto.load_master_key()  # échec rapide si absente/mal formée (design SP-15e §4/§8)
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
            and request.url.path != "/copilot/turn"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
            and not _EXPORT_PATH_RE.match(request.url.path)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Mode démo : lecture seule, écritures désactivées."},
            )
        return await call_next(request)

    if is_appexport_enabled():
        @app.middleware("http")
        async def appexport_cors(request: Request, call_next):
            path = request.url.path
            if request.method == "OPTIONS":
                if not _APPEXPORT_CORS_PATH_RE.match(path):
                    return await call_next(request)
                return Response(
                    status_code=204,
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                        "Access-Control-Allow-Headers": "Content-Type",
                    },
                )
            if not any(
                method == request.method and regex.match(path)
                for regex, method in _APPEXPORT_CORS_RULES
            ):
                return await call_next(request)
            response = await call_next(request)
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response

    def get_session() -> Iterator[Session]:
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = get_session

    app.include_router(configs_routes.router)
    app.include_router(extensions_routes.router)
    app.include_router(secrets_routes.router)
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
    app.include_router(harvest_routes.router)
    app.include_router(alerts_routes.router)
    app.include_router(reports_routes.router)
    if is_etl_enabled():
        app.include_router(pipelines_routes.router)
    if is_export_enabled():
        app.include_router(export_routes.router)
    if is_appexport_enabled():
        app.include_router(appexport_routes.router)
    if is_tileset3d_enabled():
        app.include_router(tileset3d_routes.router)
    if is_terrain3d_enabled():
        app.include_router(terrain3d_routes.router)
    if is_copilot_enabled():
        app.include_router(copilot_routes.router)

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
    s3_exports_bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.ingestion.storage import make_s3_client

        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint, access_key=s3_access_key, secret_key=s3_secret_key,
        )
        app.dependency_overrides[ingestion_routes.get_uploads_bucket] = lambda: s3_uploads_bucket
        # app.export.routes réutilise ingestion_routes.get_s3_client verbatim
        # (même clé d'override, cf. app/export/routes.py) — seul le bucket
        # diffère, donc seul get_exports_bucket a besoin de son propre
        # override ici (revue SP-17a, finding Important task 7, fix round 1).
        app.dependency_overrides[export_routes.get_exports_bucket] = lambda: s3_exports_bucket
        s3_appexports_bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        app.dependency_overrides[appexport_routes.get_appexports_bucket] = lambda: s3_appexports_bucket
        s3_tileset3d_bucket = os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")
        app.dependency_overrides[tileset3d_routes.get_tileset3d_bucket] = lambda: s3_tileset3d_bucket
        s3_terrain3d_bucket = os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
        app.dependency_overrides[terrain3d_routes.get_terrain3d_bucket] = lambda: s3_terrain3d_bucket

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

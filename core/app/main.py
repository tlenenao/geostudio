# SPDX-License-Identifier: Apache-2.0
import contextlib
import os
import re
import time
import tomllib
from collections.abc import Iterator
from http import HTTPStatus
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Receive, Scope, Send
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app import db, observability
from app.admin_tools import routes as admin_tools_routes
from app.alerts import routes as alerts_routes
from app.apikeys import routes as apikeys_routes
from app.appexport import routes as appexport_routes
from app.attachments import routes as attachments_routes
from app.auth import routes as auth_routes
from app.auth.dependency import (
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_raster_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
    reject_admin_tools_without_secret,
    reject_mock_outside_development,
)
from app.catalog import routes as catalog_routes
from app.collections import dataset_validation as collections_dataset_validation  # noqa: F401
from app.collections import geo_limits_routes as collections_geo_limits_routes
from app.collections import routes as collections_routes
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.compliance import routes as compliance_routes
from app.configs import routes as configs_routes
from app.copilot import routes as copilot_routes
from app.dataexport import routes as dataexport_routes
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.dcat import routes as dcat_routes
from app.errors import ValidationHTTPException
from app.export import routes as export_routes
from app.extensions import routes as extensions_routes
from app.features import routes as features_routes
from app.features import tiles as tiles_routes
from app.geocoding import routes as geocoding_routes
from app.harvest import dataset_validation as harvest_dataset_validation  # noqa: F401
from app.harvest import routes as harvest_routes
from app.history import routes as history_routes
from app.ingestion import routes as ingestion_routes
from app.ingestion.storage import require_public_s3_endpoint
from app.instance import routes as instance_routes
from app.items import routes as items_routes
from app.jobs import open_sync_defer
from app.jobs.engine import database_reachable, jobs_backlog
from app.lineage import routes as lineage_routes
from app.mapicons import routes as mapicons_routes
from app.mcp.server import create_mcp_server
from app.notifications import routes as notifications_routes
from app.ows import routes as ows_routes
from app.ows import wms_routes
from app.pipelines import analysis_routes as analysis_routes
from app.pipelines import config_validation as pipelines_config_validation  # noqa: F401
from app.pipelines import routes as pipelines_routes
from app.public import routes as public_routes
from app.public_submit import routes as public_submit_routes
from app.quality import routes as quality_routes
from app.quotas import routes as quotas_routes
from app.quotas.service import QuotaExceededError, validate_quota_settings
from app.raster import routes as raster_routes
from app.ratelimit.limiter import PgRateLimiter, caller_key, make_rate_limiter, route_group
from app.records import routes as records_routes
from app.relations import routes as relations_routes
from app.relations.service import RelationHooks
from app.reports import routes as reports_routes
from app.roles import routes as roles_routes
from app.routing import routes as routing_routes
from app.schemas_routes import router as schemas_router
from app.secrets import crypto as secrets_crypto
from app.secrets import routes as secrets_routes
from app.sharing import routes as sharing_routes
from app.stac import routes as stac_routes
from app.styles import routes as styles_routes
from app.terrain3d import routes as terrain3d_routes
from app.tileset3d import routes as tileset3d_routes
from app.usage import routes as usage_routes
from app.webhooks import routes as webhooks_routes
from app.xlsform import routes as xlsform_routes

MAX_CONFIG_BODY_BYTES = 5 * 1024 * 1024
_CONFIG_WRITE_PATH_RE = re.compile(r"^/v1/configs(/[^/]+){0,2}$")
_PUBLIC_SUBMIT_PATH_RE = re.compile(r"^/v1/public/submit/[^/]+$")
# AUD-153 : pièce jointe (25 Mo) + charge GeoJSON (64 Ko) + enveloppe multipart.
MAX_PUBLIC_SUBMIT_BODY_BYTES = 26 * 1024 * 1024
_BODY_LIMITS: list[tuple[re.Pattern[str], int, str]] = [
    (_CONFIG_WRITE_PATH_RE, MAX_CONFIG_BODY_BYTES, "config"),
    (_PUBLIC_SUBMIT_PATH_RE, MAX_PUBLIC_SUBMIT_BODY_BYTES, "submission"),
]
_AGGREGATE_PATH_RE = re.compile(r"^/v1/collections/[^/]+/aggregate$")
_EXPORT_PATH_RE = re.compile(
    r"^/v1/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$"
    r"|^/v1/export$|^/v1/app-exports$"
)
# Mode démo (REV-358) : seuls les exports d'agrégat synchrones sont des lectures ; `/v1/export`
# et `/v1/app-exports` créent un job (ligne en base) et restent refusés en lecture seule.
_EXPORT_READ_PATH_RE = re.compile(r"^/v1/(collections/[^/]+|datasets/[^/]+/arcgis)/export$")
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
    r"^/v1/collections(/[^/]+)?$"
    r"|^/v1/collections/[^/]+/schema$"
    r"|^/v1/collections/[^/]+/items(/[^/]+)?$"
    r"|^/v1/collections/[^/]+/aggregate$"
    r"|^/v1/extensions$"
    r"|^/v1/public/items$"
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
    (re.compile(r"^/v1/collections$"), "GET"),
    (re.compile(r"^/v1/collections/(?!candidates$)[^/]+$"), "GET"),
    (re.compile(r"^/v1/collections/[^/]+/schema$"), "GET"),
    (re.compile(r"^/v1/collections/[^/]+/items$"), "GET"),
    (re.compile(r"^/v1/collections/[^/]+/items/[^/]+$"), "GET"),
    (re.compile(r"^/v1/collections/[^/]+/aggregate$"), "POST"),
    (re.compile(r"^/v1/extensions$"), "GET"),
    (re.compile(r"^/v1/public/items$"), "GET"),
)


def trusted_proxy_hosts() -> str:
    return os.environ.get(
        "CORE_TRUSTED_PROXIES", "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"
    )


class _ListedOriginsCORS:
    """CORS complet pour les seules origines listées ; toute autre requête
    traverse intacte (CORSMiddleware répondrait 400 au préflight d'une app
    exportée, servi par `appexport_cors` avec `*`)."""

    def __init__(self, app: ASGIApp, origins: list[str]) -> None:
        self.app = app
        self.origins = {o.encode() for o in origins}
        self.cors = CORSMiddleware(
            app,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=[
                "ETag",
                "Retry-After",
                "Content-Disposition",
                "X-Tile-Aggregated",
                "X-Tile-Truncated",
                "X-Request-ID",
            ],
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        origin = (
            dict(scope.get("headers") or []).get(b"origin") if scope["type"] == "http" else None
        )
        target = self.cors if origin in self.origins else self.app
        await target(scope, receive, send)


def _core_version() -> str:
    """Version unique = pyproject.toml (copié en /app dans l'image). importlib.metadata
    ne marche pas : le projet n'est pas installé comme paquet (uv --no-emit-project)."""
    try:
        path = Path(__file__).resolve().parent.parent / "pyproject.toml"
        return tomllib.loads(path.read_text())["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0.0.0"


API_DESCRIPTION = """\
API du cœur GeoStudio (Apache-2.0).

## Authentification
Jeton `Authorization: Bearer <jeton>` : un jeton OIDC émis par Keycloak, ou une clé
d'API de service `gsk_…` (ADR 0016). Les routes de lecture publiques (catalogue public,
OGC API, STAC, DCAT, Records) acceptent aussi un appel anonyme ; elles ne servent alors
que le contenu public.

## Conventions
- Toutes les routes métier sont sous `/v1` ; `/health` et `/mcp` sont hors version.
- Pagination : `limit`/`offset` (ou `page`/`pageSize` sur le catalogue), liens `next`/`prev`.
- Erreurs au format RFC 7807 (`application/problem+json`).
- Concurrence optimiste : `If-Match` sur les écritures de configuration et d'entités.

## Standards ouverts
OGC API Features (Parts 1-4) sous `/v1/collections`, OGC API Records sous `/v1/records`,
STAC sous `/v1/stac`, DCAT-AP sous `/v1/dcat`, WFS/WMS/WMTS et OGC API Tiles sous `/v1/ows`
quand l'instance les active.
"""


def _tag_for(path: str) -> str:
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "v1":
        parts = parts[1:]
    return parts[0] if parts and not parts[0].startswith("{") else "racine"


def create_app() -> FastAPI:
    observability.setup()
    secrets_crypto.load_master_key()  # échec rapide si absente/mal formée (design SP-15e §4/§8)
    reject_mock_outside_development()  # échec rapide si mock hors dev (design SP-26 §3.1)
    require_public_s3_endpoint()  # REV-315 : liens présignés injoignables sinon
    reject_admin_tools_without_secret()  # échec rapide si gate admin sans secret
    validate_quota_settings()  # AUD-132 : « 10GB » = 500 à l'usage sinon
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
        # RC-1 : les `.defer()` synchrones des routes exigent un connecteur ouvert.
        with open_sync_defer():
            async with mcp_server.session_manager.run():
                yield

    # AUD-132 : version réelle (tag déployé) dans /v1/me et le pied de page.
    version = os.environ.get("GEOSTUDIO_VERSION", "").removeprefix("v") or "dev"
    app = FastAPI(
        title="GeoStudio Builder Service",
        version=version,
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url=None,
    )

    def _openapi() -> dict:
        """AUD-046 : contrat versionné (tag déployé, sinon pyproject.toml — jamais « dev »),
        schéma Bearer déclaré, un tag par opération."""
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=version if version != "dev" else _core_version(),
            description=app.description,
            routes=app.routes,
            openapi_version=app.openapi_version,
            tags=app.openapi_tags,
            servers=app.servers,
            webhooks=app.webhooks.routes,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["bearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT OIDC ou clé d'API gsk_",
        }
        schema["security"] = [{"bearerAuth": []}, {}]  # {} = appel anonyme admis (routes publiques)
        for path, ops in schema.get("paths", {}).items():
            for op in ops.values():
                if isinstance(op, dict) and not op.get("tags"):
                    op["tags"] = [_tag_for(path)]
        app.openapi_schema = schema
        return schema

    app.openapi = _openapi  # type: ignore[method-assign]

    # AUD-135 : schéma chargé en relatif — derrière Traefik (`/api` retiré),
    # l'URL absolue `/openapi.json` tombait sur le shell.
    @app.get("/docs", include_in_schema=False)
    def _swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url="openapi.json", title=app.title)

    observability.instrument_app(app)

    @app.exception_handler(ValidationHTTPException)
    async def _validation_exception_handler(request: Request, exc: ValidationHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail,
                "errors": exc.errors,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(request: Request, exc: RequestValidationError):
        # P21.02/05 : 422 en RFC 7807, `errors[] {field, code, message}` comme
        # ValidationHTTPException. Jamais `input`/`ctx` (P16.06 : un secret
        # soumis ne doit pas être renvoyé) : on ne recopie que loc/type/msg.
        errors = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"),
                "code": e.get("type", "invalid"),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()
        ]
        detail = "; ".join(
            f"{e['field']}: {e['message']}" if e["field"] else e["message"] for e in errors
        )
        return JSONResponse(
            status_code=422,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(422).phrase,
                "status": 422,
                "detail": detail or "validation failed",
                "errors": jsonable_encoder(errors),
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "about:blank",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail if isinstance(exc.detail, str) else "request failed",
            },
            # AUD-084 : les en-têtes de l'exception (Retry-After, WWW-Authenticate…) survivent.
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(QuotaExceededError)
    async def _quota_exceeded_handler(request: Request, exc: QuotaExceededError):
        # P26.09 : type dédié que le shell traite (message i18n + lien d'usage).
        return JSONResponse(
            status_code=exc.status_code,
            media_type="application/problem+json",
            content={
                "type": "quota-exceeded",
                "title": HTTPStatus(exc.status_code).phrase,
                "status": exc.status_code,
                "detail": exc.detail,
                "quota": exc.quota,
                "current": exc.current,
                "limit": exc.limit,
            },
        )

    @app.exception_handler(TableNotFound)
    async def _table_not_found_handler(request: Request, exc: TableNotFound):
        # j07-009 : table d'une collection disparue -> 404 stable, jamais 500.
        return await _http_exception_handler(
            request, HTTPException(status_code=404, detail="backing table not found")
        )

    @app.exception_handler(UnsupportedTable)
    async def _unsupported_table_handler(request: Request, exc: UnsupportedTable):
        return await _http_exception_handler(
            request, HTTPException(status_code=409, detail=exc.reason)
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception):
        import logging

        logging.getLogger("app.errors").exception("unhandled exception on %s", request.url.path)
        # Rendu par ServerErrorMiddleware, hors de RequestIdMiddleware : l'en-tête
        # est reposé ici, et l'identifiant donné dans le corps pour le support.
        request_id = observability.current_request_id()
        return JSONResponse(
            status_code=500,
            media_type="application/problem+json",
            headers={"X-Request-ID": request_id} if request_id else None,
            content={
                "type": "about:blank",
                "title": HTTPStatus.INTERNAL_SERVER_ERROR.phrase,
                "status": 500,
                "detail": "internal server error",
                "requestId": request_id,
            },
        )

    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and request.url.path != "/v1/analytics/sql"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
            and not _EXPORT_READ_PATH_RE.match(request.url.path)
        ):
            return JSONResponse(
                status_code=403,
                media_type="application/problem+json",
                content={
                    "type": "about:blank",
                    "title": HTTPStatus(403).phrase,
                    "status": 403,
                    "detail": "Mode démo : lecture seule, écritures désactivées.",
                },
            )
        return await call_next(request)

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        # P09.07 (t02-001) : une config JSON n'a aucune raison de dépasser
        # quelques Mo ; sans plafond, un créateur sature la base (une révision
        # par écriture), la mémoire d'uvicorn et l'historique. AUD-153 : même
        # garde sur la soumission publique anonyme (multipart). Rejet AVANT
        # lecture du corps, sur Content-Length (411 si absent : un corps
        # chunked contournerait le plafond).
        if request.method not in {"POST", "PUT"}:
            return await call_next(request)
        for pattern, max_bytes, label in _BODY_LIMITS:
            if not pattern.match(request.url.path):
                continue
            length = request.headers.get("content-length")
            if length is None or not length.isdigit():
                status, detail = 411, "Content-Length required"
            elif int(length) > max_bytes:
                status, detail = 413, f"{label} too large (max {max_bytes} bytes)"
            else:
                break
            return JSONResponse(
                status_code=status,
                media_type="application/problem+json",
                content={
                    "type": "about:blank",
                    "title": HTTPStatus(status).phrase,
                    "status": status,
                    "detail": detail,
                },
            )
        return await call_next(request)

    # Deliberately created here, not at module level: create_app() is called
    # repeatedly by the test suite (same reasoning as mcp_server above) — a
    # module-level RateLimiter singleton would leak rate-limit state across
    # unrelated tests.
    rate_limiter = make_rate_limiter(database_url)
    shared_limiter = isinstance(rate_limiter, PgRateLimiter)

    @app.middleware("http")
    async def rate_limit_guard(request: Request, call_next):
        group = route_group(
            request.url.path,
            request.method,
            _EXPORT_PATH_RE,
            has_share_token="x-share-link-token" in request.headers,
        )
        if group is not None:
            caller_key_value = caller_key(
                request.headers.get("authorization"),
                request.client.host if request.client else None,
                group,
                request.url.path,
            )
            # Backend Postgres : I/O bloquante -> thread ; backend mémoire : appel direct
            # (non thread-safe, et sans I/O).
            if shared_limiter:
                allowed = await run_in_threadpool(rate_limiter.allow, caller_key_value, group)
            else:
                allowed = rate_limiter.allow(caller_key_value, group)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    media_type="application/problem+json",
                    headers={"Retry-After": "60"},
                    content={
                        "type": "about:blank",
                        "title": "Too Many Requests",
                        "status": 429,
                        "detail": f"rate limit exceeded for {group}",
                    },
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

    # SP-57b : tous les routeurs de l'API du cœur passent sous /v1 — /health
    # (app.get direct, plus bas) et le montage MCP (app.mount("/", ...), plus
    # bas également) restent hors versionnement, contrats externes à
    # protocole fixe (healthcheck Docker, découverte OAuth MCP). Pas de
    # compatibilité ascendante (spec §2.6) : migration directe, aucun double
    # montage /items ET /v1/items.
    v1_router = APIRouter(prefix="/v1")
    v1_router.include_router(configs_routes.router)
    v1_router.include_router(extensions_routes.router)
    v1_router.include_router(secrets_routes.router)
    v1_router.include_router(roles_routes.router)
    v1_router.include_router(mapicons_routes.router)
    v1_router.include_router(instance_routes.router)
    v1_router.include_router(items_routes.router)
    v1_router.include_router(auth_routes.router)
    v1_router.include_router(sharing_routes.router)
    v1_router.include_router(public_routes.router)
    v1_router.include_router(schemas_router)
    v1_router.include_router(collections_routes.router)
    v1_router.include_router(collections_geo_limits_routes.router)
    v1_router.include_router(catalog_routes.router)
    v1_router.include_router(features_routes.router)
    v1_router.include_router(analysis_routes.router)
    v1_router.include_router(quality_routes.router)
    v1_router.include_router(history_routes.router)
    v1_router.include_router(relations_routes.router)  # ARC-21
    v1_router.include_router(dataexport_routes.router)
    v1_router.include_router(tiles_routes.router)
    v1_router.include_router(attachments_routes.router)
    v1_router.include_router(ingestion_routes.router)
    v1_router.include_router(stac_routes.router)
    v1_router.include_router(dcat_routes.router)
    v1_router.include_router(records_routes.router)
    v1_router.include_router(harvest_routes.router)
    v1_router.include_router(alerts_routes.router)
    v1_router.include_router(webhooks_routes.router)  # ARC4-F6
    v1_router.include_router(lineage_routes.router)  # ARC4-F15
    v1_router.include_router(reports_routes.router)
    v1_router.include_router(notifications_routes.router)
    v1_router.include_router(public_submit_routes.router)
    v1_router.include_router(xlsform_routes.router)
    v1_router.include_router(apikeys_routes.router)
    v1_router.include_router(usage_routes.router)
    v1_router.include_router(quotas_routes.router)
    v1_router.include_router(compliance_routes.router)
    v1_router.include_router(geocoding_routes.router)
    v1_router.include_router(routing_routes.router)
    v1_router.include_router(styles_routes.router)
    if is_etl_enabled():
        v1_router.include_router(pipelines_routes.router)
    if is_export_enabled():
        v1_router.include_router(export_routes.router)
    if is_appexport_enabled():
        v1_router.include_router(appexport_routes.router)
    app.state.ogc_tiles_enabled = ows_routes.is_ows_enabled()  # AUD-042 : /conformance
    if ows_routes.is_ows_enabled():  # ARC-11 : WFS + OGC API Tiles (ADR 0018)
        v1_router.include_router(ows_routes.router)
    if wms_routes.is_wms_enabled():  # ARC-20 : WMS 1.3.0 + WMTS 1.0.0 rendus par le cœur (ADR 0020)
        v1_router.include_router(wms_routes.router)
    if is_tileset3d_enabled():
        v1_router.include_router(tileset3d_routes.router)
    if is_terrain3d_enabled():
        v1_router.include_router(terrain3d_routes.router)
    if is_raster_enabled():  # ARC-33 : COG + proxy TiTiler authentifié (ADR 0024)
        v1_router.include_router(raster_routes.router)
    if is_copilot_enabled():
        v1_router.include_router(copilot_routes.router)
    if is_admin_tools_enabled():
        v1_router.include_router(admin_tools_routes.router)
    app.include_router(v1_router)

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL")
    s3_access_key = os.environ.get("S3_ACCESS_KEY")
    s3_secret_key = os.environ.get("S3_SECRET_KEY")
    s3_bucket = os.environ.get("S3_THUMBNAILS_BUCKET", "geostudio-thumbnails")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.items.storage import S3ThumbnailStore

        app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: S3ThumbnailStore(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
            bucket=s3_bucket,
        )

    app.dependency_overrides[features_routes.get_relation_hooks] = lambda: RelationHooks()  # ARC-21
    # L8 (M1) : pièces jointes seulement sur un fid existant, relu par la porte de lecture
    # de features (app.attachments est en dessous dans le contrat : injection).
    app.dependency_overrides[attachments_routes.get_entity_checker] = (
        features_routes.get_feature_exists
    )
    app.dependency_overrides[features_routes.get_export_job_starter] = lambda: (
        dataexport_routes.default_starter
    )

    s3_uploads_bucket = os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")
    s3_exports_bucket = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    if s3_endpoint and s3_access_key and s3_secret_key:
        from app.ingestion.storage import make_s3_client

        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
        app.dependency_overrides[ingestion_routes.get_uploads_bucket] = lambda: s3_uploads_bucket
        # app.export.routes réutilise ingestion_routes.get_s3_client verbatim
        # (même clé d'override, cf. app/export/routes.py) — seul le bucket
        # diffère, donc seul get_exports_bucket a besoin de son propre
        # override ici (revue SP-17a, finding Important task 7, fix round 1).
        app.dependency_overrides[export_routes.get_exports_bucket] = lambda: s3_exports_bucket
        s3_appexports_bucket = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
        app.dependency_overrides[appexport_routes.get_appexports_bucket] = lambda: (
            s3_appexports_bucket
        )
        s3_tileset3d_bucket = os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")
        app.dependency_overrides[tileset3d_routes.get_tileset3d_bucket] = lambda: (
            s3_tileset3d_bucket
        )
        s3_raster_bucket = os.environ.get("S3_RASTER_BUCKET", "geostudio-raster")
        app.dependency_overrides[raster_routes.get_raster_bucket] = lambda: s3_raster_bucket
        s3_terrain3d_bucket = os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
        app.dependency_overrides[terrain3d_routes.get_terrain3d_bucket] = lambda: (
            s3_terrain3d_bucket
        )
        # Clé d'override DISTINCTE de ingestion_routes.get_s3_client : ce
        # stub est défini localement dans app.attachments.routes (pas
        # réutilisé depuis app.ingestion) — cf. spec SP-40 §3.1. Partagée
        # entre les propres routes d'app.attachments (déjà incluses ci-dessus)
        # ET app.features.routes::remove_feature (cascade de suppression),
        # même mécanisme que les cinq modules ci-dessus avec la clé
        # ingestion_routes.get_s3_client.
        app.dependency_overrides[attachments_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
        # Clé d'override DISTINCTE, de nouveau : collections_routes.get_s3_client
        # est lui aussi un stub redéfini localement (SP-42/
        # F-securite-tenant-rls-03, même raison que ci-dessus) — consommé par
        # unregister_collection (purge des pièces jointes avant suppression
        # d'une collection).
        app.dependency_overrides[collections_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
        # Clé d'override DISTINCTE, encore : app.quotas.routes.get_s3_client
        # est lui aussi un stub local (SP-58 Tâche 3, même rationale que les
        # deux ci-dessus) — usage_for_tenant() lit les 4 buckets
        # tenant-préfixés directement depuis les variables d'environnement
        # (pas de dépendance par bucket), un seul client générique suffit.
        app.dependency_overrides[instance_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )
        app.dependency_overrides[quotas_routes.get_s3_client] = lambda: make_s3_client(
            endpoint_url=s3_endpoint,
            access_key=s3_access_key,
            secret_key=s3_secret_key,
        )

    health_cache: dict = {"at": float("-inf"), "value": None}

    @app.get("/health")
    def health() -> dict:
        # `status` reste la liveness (healthcheck compose) ; `jobsBacklog` rend
        # un worker arrêté visible (t02-013/j09-014) sans jamais faire échouer la sonde.
        # Route non authentifiée : le COUNT SQL est mis en cache 5 s (par app) pour
        # qu'un appelant anonyme ne puisse pas le déclencher à chaque requête.
        now = time.monotonic()
        if now - health_cache["at"] > 5.0:
            health_cache["value"] = jobs_backlog()
            health_cache["database"] = "ok" if database_reachable() else "unreachable"
            health_cache["at"] = now
        # `status` reste « ok » (liveness : un redémarrage ne réparerait pas la base) ;
        # `database` rend une base injoignable lisible (REV-364 g).
        return {
            "status": "ok",
            "database": health_cache["database"],
            "jobsBacklog": health_cache["value"],
        }

    # Mounted last: streamable_http_app() already bakes in its own full
    # paths ("/mcp", "/.well-known/oauth-protected-resource/mcp") rather
    # than paths relative to a mount prefix, so it must be mounted at "/"
    # (not "/mcp", which would double the segment to "/mcp/mcp"). Starlette
    # matches routes in registration order and a root Mount matches any
    # path as a prefix, so it must come after every app-specific route
    # above or it would shadow them (e.g. swallow "/health").
    mcp_app = mcp_server.streamable_http_app()
    # Le montage racine attrape aussi toute route inconnue : sans handler propre,
    # son 404 sort en text/plain hors RFC 7807 (P21.02).
    mcp_app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.mount("/", mcp_app)

    # GAP-61.a : sans cette couche, request.client reflète l'IP du conteneur
    # Traefik, identique pour tous les visiteurs, ce qui viderait caller_key()
    # de son utilité pour les appelants anonymes. REV-299a : X-Forwarded-For
    # n'est honoré QUE depuis les proxys de confiance (CORE_TRUSTED_PROXIES,
    # défaut : loopback + RFC 1918, soit le sous-réseau Docker de Traefik) —
    # « * » le laissait forger par tout pair atteignant core:8200, donc
    # contourner les budgets par IP (/share-links, /embed, anonymes).
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=trusted_proxy_hosts())
    # Ajouté en dernier = le plus externe : les 403/411/413/429 des middlewares
    # ci-dessus portent aussi X-Request-ID (AUD-040).
    app.add_middleware(observability.RequestIdMiddleware)
    # AUD-132 : démarrage rapide (shell :8300 → cœur :8200 cross-origin).
    # Le plus externe : les erreurs portent aussi les en-têtes CORS.
    dev_origins = [
        o.strip() for o in os.environ.get("CORE_CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]
    if dev_origins:
        app.add_middleware(_ListedOriginsCORS, origins=dev_origins)

    return app


app = create_app()

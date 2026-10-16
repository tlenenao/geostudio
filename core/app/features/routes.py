# SPDX-License-Identifier: Apache-2.0
"""Routes OGC API Features (Part 1 lecture, Part 4 écriture).
Le repository et le scope RLS sont injectables : les tests SQLite substituent
un fake et un scope nul ; le vrai chemin est PostGIS-only."""

import functools
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from opentelemetry import metrics
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.analytics.aggregate import (
    AggregateRequestBody,
    AggregateResponse,
    UnknownAggregateField,
    aggregate_columns,
    lake_as_of,
    run_collection_aggregate,
)
from app.analytics.duckdb_conn import open_spatial_connection
from app.analytics.export import (
    EXPORT_MEDIA_TYPES,
    export_filename,
    export_job_max,
    export_sync_max,
    features_to_format,
    rows_to_format,
)
from app.analytics.lake_lag import lake_lag_bytes
from app.analytics.profile import CollectionProfileResponse, run_collection_profile
from app.analytics.sql_sandbox import SqlSandboxError, run_analyst_sql
from app.attachments import repository as attachments_repo
from app.attachments.routes import get_attachments_bucket, get_s3_client
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.bbox import parse_bbox_floats
from app.collections.domains import with_attribute_rules
from app.collections.introspection import TableNotFound, hide_sensitive_columns
from app.collections.repository import get_access_facts, list_visible_collections
from app.collections.routes import (
    get_collection_for_read,
    get_introspector,
    get_readable_collection,
)
from app.collections.sensitive import (
    has_sensitive_privilege,
    masked_fields_for,
    unmask_for_owner,
)
from app.configs.geo_limits_dep import get_request_geo_limits
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.errors import ValidationHTTPException
from app.features.etag import feature_etag, if_match_satisfied
from app.features.repository import SUPPORTED_EPSG, CursorError, FilterError
from app.features.validation import validate_for_write
from app.filter_values import fold_query_filters
from app.history import service as history
from app.roles.guards import has_privilege, require_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import can
from app.sharing.geo_limits import refuse_if_geo_limited

router = APIRouter()

_meter = metrics.get_meter(__name__)
_sql_queries_counter = _meter.create_counter(
    "geostudio.analytics.sql_queries",
    unit="1",
    description="Analyst read-only SQL queries executed via POST /analytics/sql",
)


class SqlQueryBody(BaseModel):
    sql: str


RESERVED_QUERY_PARAMS = {
    "limit",
    "offset",
    "cursor",
    "bbox",
    "geom_intersects",
    "f",
    "format",
    "sortby",
    "datetime",
    "datetime_field",
    "crs",
    "bbox-crs",
    "filter",
    "filter-lang",
    "filter-crs",
}
MAX_LIMIT = 1000

CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    # Pas de `conf/oas30` (REV-364 b) : le document de définition est servi en
    # OpenAPI 3.1.0, et Features Part 1 ne définit pas de classe oas31.
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-2/1.0/conf/crs",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
    # ARC-12 : CQL2-text en sous-ensemble (cf. app/features/cql2.py)
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/filter",
    "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/features-filter",
    "http://www.opengis.net/spec/cql2/1.0/conf/cql2-text",
    "http://www.opengis.net/spec/cql2/1.0/conf/basic-cql2",
    "http://www.opengis.net/spec/cql2/1.0/conf/advanced-comparison-operators",
    "http://www.opengis.net/spec/cql2/1.0/conf/basic-spatial-functions",
    "http://www.opengis.net/spec/cql2/1.0/conf/temporal-functions",
]


@router.get("/")
def landing_page(request: Request):
    # request.base_url ne porte jamais le préfixe du routeur (juste
    # scheme://host/) — ce routeur est nesté sous /v1 (SP-57b) donc les
    # liens vers ses propres routes (self/conformance/data) doivent l'ajouter
    # explicitement ; /openapi.json reste hors /v1 (endpoint FastAPI natif,
    # posé directement sur `app`, jamais sous un routeur inclus).
    base = str(request.base_url).rstrip("/")
    v1 = f"{base}/v1"
    return {
        "title": "GeoStudio OGC API Features",
        "description": "Collections éditables du cœur GeoStudio",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{v1}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{v1}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{v1}/collections"},
            {
                "rel": "service-desc",
                "type": "application/vnd.oai.openapi+json;version=3.0",
                "href": f"{base}/openapi.json",
            },
        ],
    }


@router.get("/conformance")
def conformance():
    return {"conformsTo": CONFORMANCE_CLASSES}


def get_features_repo():  # overridé en test SQLite
    from app.features import repository

    return repository


@contextmanager
def null_rls_scope(
    session, tenant_id, *, masked: bool = False, geo_limits=None
):  # pour SQLite (pas de rôles/GUC)
    yield


class _NoRelationHooks:
    """ARC-21 : points d'extension des relations entre collections (clé étrangère
    logique à l'écriture, politique de suppression). Câblés dans main.py par
    app.relations (couche au-dessus de features : injection, pas d'import)."""

    def check_write(self, session, user, col, properties, fid, rls) -> None:
        return None

    def before_delete(self, session, user, col, fid, rls, s3) -> None:
        return None


def get_relation_hooks():  # overridé dans main.py
    return _NoRelationHooks()


def get_rls_scope(geo_limits=Depends(get_request_geo_limits)):  # overridé en test SQLite
    """Scope RLS lié aux limites géographiques de la requête (GAP-27) : chaque
    `rls(session, tenant, ...)` des routes (features, tuiles, STAC, DCAT) est
    donc limité sans que le site d'appel ait à y penser (fail-closed)."""
    from app.features.rls import rls_scope

    return functools.partial(rls_scope, geo_limits=geo_limits)


def get_masked_for_user(
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
) -> bool:
    """Verdict de masquage colonne (GAP-22) pour la requête courante — jamais
    faire confiance à un lecteur anonyme pour du sensible."""
    if user is None:
        return True
    # Volet privilège seul ; l'exception propriétaire se règle par collection
    # (`unmask_for_owner`, appelée là où `col` est résolue).
    return not has_sensitive_privilege(session, user)


def _validation_error(errors: list[dict], status: int = 400):
    return ValidationHTTPException(errors=errors, status_code=status)


def parse_bbox(raw: str | None, *, check_bounds: bool = True):
    """`minx,miny,maxx,maxy` ; fini ; bornes EPSG:4326 sauf `check_bounds=False`
    (bbox-crs projeté). REV-353 : sinon l'erreur SQL de ST_MakeEnvelope = 500."""
    try:
        return parse_bbox_floats(raw, check_bounds=check_bounds)
    except ValueError:
        raise _validation_error(
            [
                {
                    "field": "bbox",
                    "code": "invalid_bbox",
                    "message": "bbox must be minx,miny,maxx,maxy",
                }
            ]
        ) from None


def parse_crs(raw: str | None, field: str) -> int | None:
    """`EPSG:2154`, `epsg:2154` ou URI `.../def/crs/EPSG/0/2154` (+ CRS84 = 4326) -> code
    EPSG parmi SUPPORTED_EPSG, sinon 400 `invalid_crs`."""
    if raw is None:
        return None
    tail = raw.strip().rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    code = 4326 if tail.upper() == "CRS84" else int(tail) if tail.isdigit() else None
    if code not in SUPPORTED_EPSG:
        raise _validation_error(
            [
                {
                    "field": field,
                    "code": "invalid_crs",
                    "message": f"unsupported crs, expected one of EPSG {list(SUPPORTED_EPSG)}",
                }
            ]
        )
    return code


def parse_sortby(raw: str | None) -> list[tuple[str, bool]] | None:
    """`sortby=-nom,+id` -> [("nom", True), ("id", False)] ; `+` (espace après décodage) ok."""
    if raw is None:
        return None
    out = []
    for part in raw.split(","):
        name = part.strip().removeprefix("+")
        desc = name.startswith("-")
        name = name.removeprefix("-").strip()
        if not name:
            raise _validation_error(
                [{"field": "sortby", "code": "invalid_sortby", "message": "empty sortby term"}]
            )
        out.append((name, desc))
    return out


def _parse_geom_intersects(raw: str | None):
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise _validation_error(
            [
                {
                    "field": "geom_intersects",
                    "code": "invalid_geom_intersects",
                    "message": "geom_intersects must be a GeoJSON geometry encoded as JSON",
                }
            ]
        ) from None
    if not isinstance(parsed, dict) or "type" not in parsed or "coordinates" not in parsed:
        raise _validation_error(
            [
                {
                    "field": "geom_intersects",
                    "code": "invalid_geom_intersects",
                    "message": "geom_intersects must be a GeoJSON geometry encoded as JSON",
                }
            ]
        )
    return parsed


def _collect_filters(request: Request) -> dict[str, str]:
    return fold_query_filters(request.query_params.multi_items(), RESERVED_QUERY_PARAMS)


def _page_links(request: Request, *, limit: int, offset: int, page, cursor=None) -> list[dict]:
    links = [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}]
    if page.next_cursor:
        # REV-279a : next par curseur keyset, jamais par offset.
        url = request.url.remove_query_params("offset").include_query_params(
            limit=limit, cursor=page.next_cursor
        )
        links.append({"rel": "next", "type": "application/geo+json", "href": str(url)})
    if page.next_offset is not None:  # tri personnalisé : pas de curseur keyset
        url = request.url.include_query_params(limit=limit, offset=page.next_offset)
        links.append({"rel": "next", "type": "application/geo+json", "href": str(url)})
    if offset > 0 and cursor is None:
        href = str(request.url.include_query_params(limit=limit, offset=max(0, offset - limit)))
        links.append({"rel": "prev", "type": "application/geo+json", "href": href})
    return links


@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    cursor: str | None = None,
    bbox: str | None = None,
    geom_intersects: str | None = None,
    sortby: str | None = None,
    datetime_q: str | None = Query(None, alias="datetime"),
    datetime_field: str | None = None,
    crs: str | None = None,
    bbox_crs: str | None = Query(None, alias="bbox-crs"),
    filter_q: str | None = Query(None, alias="filter"),
    filter_lang: str | None = Query(None, alias="filter-lang"),
    filter_crs: str | None = Query(None, alias="filter-crs"),
    response: Response = None,  # type: ignore[assignment]
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
):
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    limit = min(limit, MAX_LIMIT)
    out_srid = parse_crs(crs, "crs")
    bbox_srid = parse_crs(bbox_crs, "bbox-crs") or 4326
    parsed_bbox = parse_bbox(bbox, check_bounds=bbox_srid == 4326)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)
    if filter_lang is not None and filter_lang != "cql2-text":
        raise _validation_error(
            [
                {
                    "field": "filter-lang",
                    "code": "invalid_filter_lang",
                    "message": "only cql2-text is supported",
                }
            ]
        )
    if cursor is not None and offset > 0:
        raise _validation_error(
            [{"field": "cursor", "code": "invalid_cursor", "message": "cursor excludes offset"}]
        )
    # ARC-02 : paramètres transmis seulement s'ils sont posés (contrat inchangé sinon)
    extra: dict = {
        k: v
        for k, v in {
            "sortby": parse_sortby(sortby),
            "datetime_": datetime_q,
            "datetime_field": datetime_field,
            "out_srid": out_srid,
            "bbox_srid": bbox_srid if bbox_srid != 4326 else None,
            "cql2": filter_q,
            "cql2_srid": parse_crs(filter_crs, "filter-crs"),
        }.items()
        if v is not None
    }
    try:
        with rls(session, col.tenant_id, masked=masked):
            page = repo.select_features(
                session,
                info,
                limit=limit,
                offset=offset,
                bbox=parsed_bbox,
                geom_intersects=parsed_geom_intersects,
                filters=filters or None,
                after=cursor,
                count_mode="capped",
                **extra,
            )
    except CursorError as exc:
        raise _validation_error(
            [{"field": "cursor", "code": "invalid_cursor", "message": "invalid cursor"}]
        ) from exc
    except FilterError as exc:
        raise _validation_error(
            [{"field": exc.field, "code": exc.code, "message": exc.message}]
        ) from exc
    if out_srid is not None:
        response.headers["Content-Crs"] = f"<http://www.opengis.net/def/crs/EPSG/0/{out_srid}>"
    body: dict = {"type": "FeatureCollection", "features": page.features}
    if page.number_matched is not None:
        body["numberMatched"] = page.number_matched
    if page.number_matched_lower_bound:
        body["numberMatchedLowerBound"] = True
    body["numberReturned"] = page.number_returned
    body["timeStamp"] = datetime.now(UTC).isoformat()
    body["links"] = _page_links(request, limit=limit, offset=offset, page=page, cursor=cursor)
    return body


def get_duckdb_connection_factory():  # overridé en test
    from app.analytics.duckdb_conn import open_connection

    def factory():
        return open_connection(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ["S3_SECRET_KEY"],
        )

    return factory


def get_analytics_base_uri():  # overridé en test (pointe un répertoire tmp_path local)
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    return f"s3://{bucket}/cdc"


@router.post("/collections/{collection_id}/aggregate", response_model=AggregateResponse)
def aggregate_features(
    collection_id: str,
    body: AggregateRequestBody,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
    geo_limits=Depends(get_request_geo_limits),
):
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    # GAP-27 : le lac DuckDB n'est pas soumis à la RLS — refus fail-closed.
    refuse_if_geo_limited(geo_limits, col.table_name, path="aggregates")
    info = introspect(session, col.table_name)
    masked_fields = masked_fields_for(session, user, col)
    conn = conn_factory()
    try:
        try:
            category_key, rows = run_collection_aggregate(
                conn,
                base_uri=base_uri,
                tenant_id=col.tenant_id,
                collection_id=col.id,
                table_info=info,
                request=body,
                masked_fields=masked_fields,
            )
        except UnknownAggregateField as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_field", "message": exc.message}]
            ) from exc
        # P25.10/11 : le lac peut retarder sur la base (flush CDC ~30 s) —
        # la réponse dit jusqu'où il est à jour ; pending = pas encore répliqué.
        as_of = lake_as_of(conn, base_uri, col.tenant_id, col.id)
    finally:
        conn.close()
    # Retard slot-global de l'instance : reserve aux exploitants authentifies.
    lag_bytes = (
        lake_lag_bytes(session)
        if user is not None
        and has_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
        else None
    )
    return AggregateResponse(
        categoryKey=category_key,
        rows=rows,
        asOf=as_of,
        pending=as_of is None,
        lagBytes=lag_bytes,
    )


@router.get("/collections/{collection_id}/profile", response_model=CollectionProfileResponse)
def profile_collection(
    collection_id: str,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
    geo_limits=Depends(get_request_geo_limits),
):
    """Résumé exploratoire (REV-117) : mêmes droits, même masquage de colonnes
    sensibles et mêmes bornes DuckDB que POST /aggregate."""
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    # REV-334 : le lac n'est pas soumis à la RLS — refus fail-closed (comme /aggregate).
    refuse_if_geo_limited(geo_limits, col.table_name, path="profile")
    info = introspect(session, col.table_name)
    masked_fields = masked_fields_for(session, user, col)
    conn = conn_factory()
    try:
        try:
            result = run_collection_profile(
                conn,
                base_uri=base_uri,
                tenant_id=col.tenant_id,
                collection_id=col.id,
                table_info=info,
                masked_fields=masked_fields,
            )
        except UnknownAggregateField as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_field", "message": exc.message}]
            ) from exc
        as_of = lake_as_of(conn, base_uri, col.tenant_id, col.id)
    finally:
        conn.close()
    return CollectionProfileResponse(**result, asOf=as_of, pending=as_of is None)


EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}


@router.post("/collections/{collection_id}/export")
def export_collection_aggregate(
    collection_id: str,
    body: AggregateRequestBody,
    format: str = Query(...),
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
    geo_limits=Depends(get_request_geo_limits),
):
    if format not in EXPORT_FORMATS_AGGREGATE:
        raise _validation_error(
            [
                {
                    "field": "format",
                    "code": "unsupported_format",
                    "message": f"unsupported format '{format}'",
                }
            ]
        )
    col = get_collection_for_read(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="aggregate export")
    info = introspect(session, col.table_name)
    masked_fields = masked_fields_for(session, user, col)
    conn = conn_factory()
    try:
        try:
            category_key, rows = run_collection_aggregate(
                conn,
                base_uri=base_uri,
                tenant_id=col.tenant_id,
                collection_id=col.id,
                table_info=info,
                request=body,
                masked_fields=masked_fields,
            )
        except UnknownAggregateField as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_field", "message": exc.message}]
            ) from exc
    finally:
        conn.close()
    content = rows_to_format(rows, format=format, columns=aggregate_columns(body, category_key))
    filename = export_filename(col.title, format=format)
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="export.run",
        object_type="collection",
        object_id=col.id,
        payload={"format": format, "mode": "aggregate"},
    )
    return Response(
        content=content,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}
# P29.04 : plafond mémoire de l'export synchrone, réglable (CORE_EXPORT_ITEMS_MAX).
# Export de collection : synchrone jusqu'à CORE_EXPORT_SYNC_MAX, puis job (écriture en
# flux, analytics/export.py). Ce plafond-ci borne l'export en mémoire du moissonnage
# (harvest/routes.py l'importe : un seul réglage, REV-283c).
EXPORT_ITEMS_CAP = int(os.environ.get("CORE_EXPORT_ITEMS_MAX", "100000"))


def get_export_job_starter():  # câblé dans main.py (app.dataexport) : pas d'arête vers le haut
    raise RuntimeError("collection export job starter not configured")


@router.get(
    "/collections/{collection_id}/export/items",
    responses={202: {"description": "Export asynchrone : {jobId}, suivre via export/jobs/{jobId}"}},
)
def export_collection_items(
    collection_id: str,
    request: Request,
    format: str = Query(...),
    bbox: str | None = None,
    geom_intersects: str | None = None,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
    start_job=Depends(get_export_job_starter),
):
    if format not in EXPORT_FORMATS_ITEMS:
        raise _validation_error(
            [
                {
                    "field": "format",
                    "code": "unsupported_format",
                    "message": f"unsupported format '{format}'",
                }
            ]
        )
    col = get_collection_for_read(session, user, collection_id)
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    parsed_bbox = parse_bbox(bbox)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)
    sync_max = export_sync_max()
    job_max = export_job_max(format)

    features: list[dict] = []
    cursor = None
    while True:
        try:
            with rls(session, col.tenant_id, masked=masked):
                page = repo.select_features(
                    session,
                    info,
                    limit=MAX_LIMIT,
                    offset=0,
                    bbox=parsed_bbox,
                    geom_intersects=parsed_geom_intersects,
                    filters=filters or None,
                    after=cursor,
                    # Total sur la 1re page : il tranche sync / asynchrone / 413. Borné à
                    # job_max (REV-323 B : count(*) exact non borné sur une grosse table).
                    count_mode="capped" if cursor is None else "none",
                    count_cap=job_max,
                )
        except FilterError as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_filter", "message": exc.message}]
            ) from exc
        if cursor is None and page.number_matched is not None:
            if page.number_matched_lower_bound or page.number_matched > job_max:
                raise HTTPException(
                    status_code=413, detail="too many entities matched, refine your filters"
                )
            if page.number_matched > sync_max:
                job_id = start_job(
                    session,
                    tenant_id=col.tenant_id,
                    collection_id=col.id,
                    user_id=user.id,
                    fmt=format,
                    masked=bool(masked),
                    query={
                        "bbox": list(parsed_bbox) if parsed_bbox else None,
                        "geomIntersects": parsed_geom_intersects,
                        "filters": filters,
                    },
                )
                return JSONResponse(
                    status_code=202,
                    content={"jobId": job_id},
                    headers={"Location": f"/v1/collections/{col.id}/export/jobs/{job_id}"},
                )
        features.extend(page.features)
        if len(features) > sync_max:
            raise HTTPException(
                status_code=413, detail="too many entities matched, refine your filters"
            )
        cursor = page.next_cursor
        if cursor is None:
            break

    if format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=format)
    filename = export_filename(col.title, format=format)
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="export.run",
        object_type="collection",
        object_id=col.id,
        payload={"format": format, "mode": "items"},
    )
    return Response(
        content=content,
        media_type=EXPORT_MEDIA_TYPES[format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/analytics/sql")
def analytics_sql(
    body: SqlQueryBody,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
    geo_limits=Depends(get_request_geo_limits),
):
    require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)
    sensitive_ok = has_sensitive_privilege(session, user)
    cols = list_visible_collections(
        session,
        tenant_id=user.tenant_id,
        user_id=user.id,
        can_see_all=has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value),
    )
    allowed: dict = {}
    masked_fields_by_collection: dict[str, frozenset[str]] = {}
    for col in cols:
        # GAP-27 : le lac DuckDB n'applique pas les limites géographiques — une
        # collection limitée pour l'appelant n'est simplement pas interrogeable.
        if col.table_name in geo_limits:
            continue
        try:
            allowed[col.id] = introspect(session, col.table_name)
        except TableNotFound:
            continue
        masked_fields_by_collection[col.id] = (
            frozenset()
            if sensitive_ok or col.owner_id == user.id
            else frozenset(col.sensitive_fields)
        )
    conn = conn_factory()
    try:
        columns, rows, truncated = run_analyst_sql(
            conn,
            sql=body.sql,
            allowed=allowed,
            base_uri=base_uri,
            tenant_id=user.tenant_id,
            masked_fields_by_collection=masked_fields_by_collection,
        )
    except SqlSandboxError as exc:
        _sql_queries_counter.add(1, {"outcome": "error"})
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="analytics.sql",
            object_type="analytics",
            object_id="sql",
            payload={"sql": body.sql[:500], "outcome": "error"},
        )
        # Commit the abuse/failure trail on the request session itself: the outer
        # request_scoped_session rolls back on the raised 400, so we must persist
        # the audit row here (this route is otherwise read-only, so the audit is
        # the only pending write). The later rollback is then a harmless no-op.
        session.commit()
        raise _validation_error(
            [{"field": "sql", "code": "sql_error", "message": str(exc)}]
        ) from exc
    finally:
        conn.close()
    _sql_queries_counter.add(1, {"outcome": "success"})
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="analytics.sql",
        object_type="analytics",
        object_id="sql",
        payload={"sql": body.sql[:500], "outcome": "success"},
    )
    return {"columns": columns, "rows": rows, "truncated": truncated}


@router.get("/collections/{collection_id}/items/{fid}")
def get_single_feature(
    collection_id: str,
    fid: str,
    response: Response,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
):
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    with rls(session, col.tenant_id, masked=masked):
        feature = repo.get_feature(session, info, fid=fid)
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    response.headers["ETag"] = feature_etag(feature)
    return feature


def _enforce_if_match(session, repo, view_info, fid, if_match):
    """ARC-04 : `If-Match` optionnel. Verrouille la ligne puis compare l'ETag recalculé
    (même vue que GET) : 404 si absente, 412 si périmé. À appeler dans le scope RLS, avant
    l'écriture ; sans en-tête : aucun effet (rétro-compatible)."""
    if if_match is None:
        return
    repo.lock_feature(session, view_info, fid=fid)
    current = repo.get_feature(session, view_info, fid=fid)
    if current is None:
        raise HTTPException(status_code=404, detail="feature not found")
    if not if_match_satisfied(if_match, feature_etag(current)):
        raise HTTPException(
            status_code=412, detail="precondition failed: the feature changed since it was read"
        )


def _set_etag(response, session, repo, view_info, fid):
    feature = repo.get_feature(session, view_info, fid=str(fid))
    if feature is not None:
        response.headers["ETag"] = feature_etag(feature)


def _raise_if_outside_geo_limit(exc: DBAPIError) -> None:
    """WITH CHECK de la policy `geo_limit` (GAP-27) : SQLSTATE 42501 sur une
    écriture dont la géométrie sort de la limite de l'appelant → 403 explicite."""
    if getattr(exc.orig, "sqlstate", None) == "42501":
        raise HTTPException(
            status_code=403, detail="outside_geo_limit: geometry is outside your geographic limit"
        ) from exc


def _get_writable(session, user, collection_id):
    col = get_readable_collection(session, user, collection_id)
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=get_access_facts(col),
        kind="collection",
        actor_is_admin=user.is_admin,
    ):
        raise HTTPException(status_code=403, detail="write access required")
    if not col.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    return col


def _snapshot(session, repo, info, fid):
    """Instantané du journal ARC-15. À appeler HORS `rls(...)` : rôle propriétaire, donc
    géométrie complète (jamais découpée par `geo_source` sous une limite géographique) ;
    l'appelant n'y lit que la ligne qu'il vient d'écrire (ou va écrire) sous RLS."""
    return history.snapshot(repo.get_feature(session, info, fid=str(fid)))


def _validated(introspect, session, col, payload):
    info = with_attribute_rules(introspect(session, col.table_name), col)
    errors = validate_for_write(info, payload)
    if errors:
        raise _validation_error(errors)
    return info


@router.post("/collections/{collection_id}/items", status_code=201)
def create_feature(
    collection_id: str,
    payload: dict,
    request: Request,
    response: Response,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    relations=Depends(get_relation_hooks),
):
    col = _get_writable(session, user, collection_id)
    info = _validated(introspect, session, col, payload)
    relations.check_write(session, user, col, payload.get("properties") or {}, None, rls)
    try:
        with rls(session, col.tenant_id):
            fid = repo.insert_feature(
                session,
                info,
                properties=payload.get("properties") or {},
                geometry=payload.get("geometry"),
            )
            _set_etag(response, session, repo, info, fid)
        after = _snapshot(session, repo, info, fid)
    except IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="feature conflicts with an existing row"
        ) from exc
    except DBAPIError as exc:
        _raise_if_outside_geo_limit(exc)
        raise
    history.record_change(  # ARC-15 : même transaction que l'écriture
        session,
        tenant_id=col.tenant_id,
        collection_id=col.id,
        fid=str(fid),
        op="create",
        before=None,
        after=after,
        actor_id=user.id,
    )
    session.execute(
        text("UPDATE collections SET feature_count = feature_count + 1 WHERE id = :id"),
        {"id": col.id},
    )
    # REV-016 : aligné sur col.tenant_id — même patron que les write_audit
    # voisins de ce fichier (export.run, analytics.sql exceptés, ceux-là
    # n'ont pas de collection résolue en amont).
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="feature.create",
        object_type="feature",
        object_id=str(fid),
        payload={"collection": col.id, "fid": str(fid)},
    )
    response.headers["Location"] = str(
        request.url_for("get_single_feature", collection_id=col.id, fid=str(fid))
    )
    return {"id": fid}


@router.put("/collections/{collection_id}/items/{fid}", status_code=204)
def put_feature(
    collection_id: str,
    fid: str,
    payload: dict,
    response: Response,
    if_match: str | None = Header(default=None),
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked: bool = Depends(get_masked_for_user),
    relations=Depends(get_relation_hooks),
):
    col = _get_writable(session, user, collection_id)
    _replace(
        col,
        fid,
        payload,
        response,
        if_match,
        user,
        session,
        introspect,
        repo,
        rls,
        masked,
        "update",
        relations,
    )


def _replace(
    col,
    fid,
    payload,
    response,
    if_match,
    user,
    session,
    introspect,
    repo,
    rls,
    masked,
    op,
    relations,
):
    masked = unmask_for_owner(masked, user, col)
    # GAP-22 : le PUT remplace tout — sans ça, un utilisateur masqué mettrait à
    # NULL les colonnes sensibles qu'il n'a jamais vues. Retirées de `info`,
    # elles ne sont ni validées ni écrites (donc conservées en base).
    info = with_attribute_rules(introspect(session, col.table_name), col)
    full_info = info  # journal ARC-15 : instantanés complets (masqués à la lecture)
    # Vue de l'ETag = celle de GET /items/{fid} (masquage inclus).
    view_info = hide_sensitive_columns(info, col.sensitive_fields) if masked else info
    # Même chose pour un lecteur autorisé (propriétaire, REV-276) : une colonne
    # sensible absente du corps est conservée, pas remise à NULL.
    sent = payload.get("properties") or {}
    info = hide_sensitive_columns(
        info, [f for f in col.sensitive_fields if masked or f not in sent]
    )
    if errors := validate_for_write(info, payload):
        raise _validation_error(errors)
    relations.check_write(session, user, col, sent, fid, rls)
    try:
        with rls(session, col.tenant_id):
            _enforce_if_match(session, repo, view_info, fid, if_match)
        before = _snapshot(session, repo, full_info, fid)
        with rls(session, col.tenant_id):
            ok = repo.replace_feature(
                session,
                info,
                fid=fid,
                properties=payload.get("properties") or {},
                geometry=payload.get("geometry"),
            )
            if ok:
                _set_etag(response, session, repo, view_info, fid)
        if ok:
            after = _snapshot(session, repo, full_info, fid)
    except IntegrityError as exc:
        # Même réponse qu'à la création : une collision avec une ligne cachée par une
        # limite géographique est indiscernable d'une collision avec une ligne visible.
        raise HTTPException(
            status_code=409, detail="feature conflicts with an existing row"
        ) from exc
    except DBAPIError as exc:
        _raise_if_outside_geo_limit(exc)
        raise
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    history.record_change(
        session,
        tenant_id=col.tenant_id,
        collection_id=col.id,
        fid=fid,
        op=op,
        before=before,
        after=after,
        actor_id=user.id,
    )
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="feature.update" if op == "update" else "feature.restore",
        object_type="feature",
        object_id=fid,
        payload={"collection": col.id, "fid": fid},
    )


@router.post(
    "/collections/{collection_id}/items/{fid}/history/{version_id}/restore", status_code=204
)
def restore_feature_version(
    collection_id: str,
    fid: str,
    version_id: int,
    response: Response,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked: bool = Depends(get_masked_for_user),
    geo_limits=Depends(get_request_geo_limits),
    relations=Depends(get_relation_hooks),
):
    """ARC-15 : ré-applique l'état APRÈS d'une version (écriture normale : droit
    d'écriture, validation, RLS ; journalisée `restore`). Une suppression n'est pas
    restaurable (409) : la PK ne peut pas être ré-imposée."""
    col = _get_writable(session, user, collection_id)
    # Fail-closed, comme la lecture du journal : une version n'est pas découpée.
    refuse_if_geo_limited(geo_limits, col.table_name, path="entity restore")
    version = history.get_version(
        session, tenant_id=col.tenant_id, collection_id=col.id, fid=fid, version_id=version_id
    )
    if version is None:
        raise HTTPException(status_code=404, detail="version not found")
    if version.after is None:
        raise HTTPException(status_code=409, detail="a deletion cannot be restored")
    hidden = (
        frozenset() if not unmask_for_owner(masked, user, col) else frozenset(col.sensitive_fields)
    )
    target = history.mask_snapshot(version.after, hidden) or {}
    # Seules les colonnes écrivables aujourd'hui : ni `unsupported` (lecture seule), ni
    # réservées, ni supprimées depuis la version.
    info = introspect(session, col.table_name)
    reserved = {info.pk_column, "tenant_id", info.geometry_column}
    writable = {c.name for c in info.columns if c.type != "unsupported" and c.name not in reserved}
    payload = {
        "type": "Feature",
        "properties": {k: v for k, v in (target.get("properties") or {}).items() if k in writable},
        "geometry": target.get("geometry"),
    }
    _replace(
        col,
        fid,
        payload,
        response,
        None,
        user,
        session,
        introspect,
        repo,
        rls,
        masked,
        "restore",
        relations,
    )


@router.delete("/collections/{collection_id}/items/{fid}", status_code=204)
def remove_feature(
    collection_id: str,
    fid: str,
    if_match: str | None = Header(default=None),
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    s3=Depends(get_s3_client),
    masked: bool = Depends(get_masked_for_user),
    relations=Depends(get_relation_hooks),
):
    col = _get_writable(session, user, collection_id)
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    view_info = hide_sensitive_columns(info, col.sensitive_fields) if masked else info
    relations.before_delete(session, user, col, fid, rls, s3)  # ARC-21 : restrict / cascade
    with rls(session, col.tenant_id):
        _enforce_if_match(session, repo, view_info, fid, if_match)
    before = _snapshot(session, repo, info, fid)
    with rls(session, col.tenant_id):
        ok = repo.delete_feature(session, info, fid=fid)
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    history.record_change(
        session,
        tenant_id=col.tenant_id,
        collection_id=col.id,
        fid=fid,
        op="delete",
        before=before,
        after=None,
        actor_id=user.id,
    )
    session.execute(
        text("UPDATE collections SET feature_count = feature_count - 1 WHERE id = :id"),
        {"id": col.id},
    )
    attachments_repo.delete_all_for_feature(
        session,
        s3,
        get_attachments_bucket(),
        tenant_id=col.tenant_id,
        collection_id=col.id,
        fid=fid,
    )
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="feature.delete",
        object_type="feature",
        object_id=fid,
        payload={"collection": col.id, "fid": fid},
    )

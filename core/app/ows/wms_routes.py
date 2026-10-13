# SPDX-License-Identifier: Apache-2.0
"""WMS 1.3.0 + WMTS 1.0.0 rendus par le cœur (ARC-20, ADR 0020).

Même porte de lecture que WFS/Features, sans SQL propre : `get_collection_for_read`
(404 avant 403), `rls_scope` (tenant + limites géographiques), masquage GAP-22 et
`select_features`. Plafonds : entités par couche/requête, taille d'image, nombre de
couches, `statement_timeout`. Montées seulement si CORE_OWS_WMS_ENABLED ; exposition
par collection via `Collection.ows_enabled` (comme WFS)."""

import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import hide_sensitive_columns
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector
from app.collections.sensitive import unmask_for_owner
from app.configs import repository as configs_repo
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.features.repository import CursorError, FilterError
from app.features.routes import get_features_repo, get_masked_for_user, get_rls_scope
from app.features.tiles import apply_tile_statement_timeout
from app.items import repository as items_repo
from app.ows import render, wms
from app.ows.routes import _OwsError, _readable
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.sharing.authorization import can
from app.styles.model import Style, default_style, kind_of_geometry_type, style_from_symbology

router = APIRouter()

MAX_LAYERS = 8
MAX_FEATURES_PER_LAYER = 2000
MAX_FEATURES_PER_REQUEST = 6000
STATEMENT_TIMEOUT_MS = 5000
FEATURE_INFO_MAX = 50
FEATURE_INFO_PIXELS = 5  # tolérance de sélection autour du pixel interrogé
EDGE_BUFFER_PX = 24  # lit un peu au-delà de l'image pour ne pas couper les symboles de bord
XML = "text/xml; charset=utf-8"
_COLOR = re.compile(r"^0[xX]([0-9a-fA-F]{6})$")
_STYLE_REF = re.compile(r"^map:([A-Za-z0-9_-]{1,64}):([A-Za-z0-9_-]{1,64})$")


def is_wms_enabled() -> bool:
    """CORE_OWS_WMS_ENABLED — capacité instance-wide (faux : aucune route montée)."""
    return os.environ.get("CORE_OWS_WMS_ENABLED", "false").lower() == "true"


def _err(code: str, message: str, status: int = 400) -> _OwsError:
    return _OwsError(status, code, None, message)


def _csv(raw: str | None) -> list[str]:
    return [s.strip() for s in raw.split(",")] if raw else []


def _int(q: dict, key: str, lo: int, hi: int) -> int:
    raw = q.get(key)
    if raw is None:
        raise _err("MissingParameterValue", f"{key.upper()} is required")
    try:
        v = int(raw)
    except ValueError:
        raise _err("InvalidParameterValue", f"{key.upper()} must be an integer") from None
    if not lo <= v <= hi:
        raise _err("InvalidParameterValue", f"{key.upper()} must be between {lo} and {hi}")
    return v


def _crs(raw: str | None) -> tuple[int, bool]:
    if not raw:
        raise _err("MissingParameterValue", "CRS is required")
    try:
        return wms.CRS_TABLE[raw.strip().upper()]
    except KeyError:
        raise _err("InvalidCRS", f"unsupported CRS '{raw[:40]}'") from None


def _bbox(raw: str | None, latlon: bool) -> tuple[float, float, float, float]:
    if not raw:
        raise _err("MissingParameterValue", "BBOX is required")
    try:
        v = [float(p) for p in raw.split(",")]
    except ValueError:
        raise _err("InvalidParameterValue", "BBOX must be numeric") from None
    if len(v) != 4 or not wms.finite(*v):
        raise _err("InvalidParameterValue", "BBOX must be minx,miny,maxx,maxy")
    if latlon:  # WMS 1.3.0 : EPSG:4326 = lat,lon
        v = [v[1], v[0], v[3], v[2]]
    if v[0] >= v[2] or v[1] >= v[3]:
        raise _err("InvalidParameterValue", "BBOX must have min < max")
    return v[0], v[1], v[2], v[3]


def _query_bbox(bbox, srid: int, w: int, h: int, buffer_px: int):
    """Emprise de LECTURE : image élargie de `buffer_px`, bornée au domaine du CRS
    (ST_MakeEnvelope/ST_Transform lèveraient sinon une erreur SQL = 500)."""
    bx = (bbox[2] - bbox[0]) / w * buffer_px
    by = (bbox[3] - bbox[1]) / h * buffer_px
    lim = {4326: (180.0, 90.0), 3857: (20037508.34, 20037508.34), 2154: (1e7, 1e7)}[srid]
    return (
        max(bbox[0] - bx, -lim[0]),
        max(bbox[1] - by, -lim[1]),
        min(bbox[2] + bx, lim[0]),
        min(bbox[3] + by, lim[1]),
    )


def _resolve_style(session, user, col, name: str) -> Style:
    """`default` (ou vide) : style par défaut selon la géométrie ; `map:<itemId>:<layerId>` :
    symbologie déclarative d'une couche d'une carte que l'appelant PEUT LIRE (`can()`),
    liée à cette collection. Tout échec = StyleNotDefined (ne révèle rien de la carte)."""
    kind = kind_of_geometry_type(col.geometry_type)
    if name in ("", "default"):
        return default_style(kind)
    m = _STYLE_REF.match(name)
    bad = _err("StyleNotDefined", f"style '{name[:80]}' is not defined for layer '{col.id}'")
    if not m or user is None:
        raise bad
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=m.group(1))
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise bad
    cfg = configs_repo.get_config_by_item(session, m.group(1))
    if cfg is None or cfg.kind != "map" or cfg.config.map is None:
        raise bad
    for layer in cfg.config.map.layers:
        if layer.id == m.group(2) and layer.collectionId == col.id:
            return style_from_symbology(layer.symbology, layer.geometryKind or kind)
    raise bad


def _read(session, rls, repo, col, info, masked, *, bbox, srid, out_srid, limit):
    """(features, tronqué ?) — l'unique chemin de lecture : select_features sous `rls_scope`."""
    kwargs: dict = {"bbox": bbox}
    if srid != 4326:
        kwargs["bbox_srid"] = srid
    if out_srid is not None and out_srid != 4326:
        kwargs["out_srid"] = out_srid
    with rls(session, col.tenant_id, masked=masked):
        apply_tile_statement_timeout(session, STATEMENT_TIMEOUT_MS)
        try:
            page = repo.select_features(
                session, info, limit=limit, offset=0, count_mode="none", **kwargs
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":  # query_canceled
                raise _err("NoApplicableCode", "rendering timed out", 503) from exc
            raise _err("InvalidParameterValue", "request area cannot be read") from exc
    more = page.next_cursor is not None or page.next_offset is not None
    return page.features, more


def _layer_ctx(session, user, guest, introspect, masked_dep, name: str, locator: str):
    col = _readable(session, user, guest, name, locator)
    masked = unmask_for_owner(masked_dep, user, col)
    info = introspect(session, col.table_name)
    if info.geometry_column is None:
        raise _err("LayerNotDefined", f"layer '{col.id}' has no geometry")
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    return col, info, masked


def _exposed(session, user) -> list:
    from app.tenants.repository import get_or_create_default_tenant

    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    can_all = bool(user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value))
    cols = list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None, can_see_all=can_all
    )
    return [c for c in cols if c.ows_enabled and c.geometry_column and wms.NCNAME.match(c.id)]


def _png(body: bytes, truncated: bool) -> Response:
    headers = {"Cache-Control": "private, no-cache"}
    if truncated:
        headers["X-GeoStudio-Truncated"] = "true"
    return Response(content=body, media_type="image/png", headers=headers)


def _render(
    session, rls, repo, introspect, masked_dep, user, guest, *, layers, styles, bbox, srid, size, bg
):
    """Rend `layers` (déjà validés en nombre) dans une image `size` couvrant `bbox`."""
    w, h = size
    canvas = render.new_canvas(bbox, w, h)
    qbox = _query_bbox(bbox, srid, w, h, EDGE_BUFFER_PX)
    budget, truncated = MAX_FEATURES_PER_REQUEST, False
    # Résolution des styles et des droits AVANT d'entrer dans la portée RLS (une erreur de
    # couche/style ne doit pas coûter une requête de lecture).
    ctxs = []
    for i, name in enumerate(layers):
        col, info, masked = _layer_ctx(session, user, guest, introspect, masked_dep, name, "LAYERS")
        ctxs.append((col, info, masked, _resolve_style(session, user, col, styles[i])))
    for col, info, masked, style in ctxs:
        if budget <= 0:
            truncated = True
            break
        feats, more = _read(
            session,
            rls,
            repo,
            col,
            info,
            masked,
            bbox=qbox,
            srid=srid,
            out_srid=srid,
            limit=min(MAX_FEATURES_PER_LAYER, budget),
        )
        budget -= len(feats)
        truncated = truncated or more
        render.draw_features(canvas, feats, style)
    return render.to_png(canvas, bg), truncated


# --- WMS ---------------------------------------------------------------------


@router.get("/ows/wms")
def wms_endpoint(
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    q = {k.lower(): v for k, v in request.query_params.items()}
    try:
        if q.get("service", "WMS").upper() != "WMS":
            raise _err("InvalidParameterValue", "only service=WMS is served here")
        op = (q.get("request") or "").lower()
        if op == "getcapabilities":
            base = f"{str(request.base_url).rstrip('/')}/v1/ows/wms"
            return Response(
                wms.wms_capabilities(base, "GeoStudio WMS", _exposed(session, user)),
                media_type="text/xml",
            )
        if q.get("version", "1.3.0") != "1.3.0":
            raise _err("InvalidParameterValue", "only WMS 1.3.0 is supported")
        if op == "getmap":
            return _get_map(q, session, user, guest, introspect, repo, rls, masked)
        if op == "getfeatureinfo":
            return _get_feature_info(q, session, user, guest, introspect, repo, rls, masked)
        raise _err(
            "OperationNotSupported" if op else "MissingParameterValue",
            "supported operations: GetCapabilities, GetMap, GetFeatureInfo",
        )
    except _OwsError as e:
        return Response(wms.service_exception(e.code, e.message), e.status, media_type=XML)
    except HTTPException as e:
        return Response(
            wms.service_exception("InvalidParameterValue", str(e.detail)),
            e.status_code,
            media_type=XML,
        )
    except (FilterError, CursorError) as e:
        return Response(wms.service_exception("InvalidParameterValue", str(e)), 400, media_type=XML)


def _common(q: dict):
    names = _csv(q.get("layers"))
    if not names or not all(names):
        raise _err("MissingParameterValue", "LAYERS is required")
    if len(names) > MAX_LAYERS:
        raise _err("InvalidParameterValue", f"at most {MAX_LAYERS} layers per request")
    styles = _csv(q.get("styles"))
    if len(styles) not in (0, len(names)):
        raise _err("StyleNotDefined", "STYLES must be empty or match LAYERS one to one")
    styles = styles or [""] * len(names)
    srid, latlon = _crs(q.get("crs"))
    bbox = _bbox(q.get("bbox"), latlon)
    w, h = _int(q, "width", 1, render.MAX_DIM), _int(q, "height", 1, render.MAX_DIM)
    if w * h > render.MAX_PIXELS:
        raise _err("InvalidParameterValue", "image too large")
    return names, styles, srid, bbox, (w, h)


def _get_map(q, session, user, guest, introspect, repo, rls, masked) -> Response:
    names, styles, srid, bbox, size = _common(q)
    if q.get("format", "").lower() not in wms.GETMAP_FORMATS:
        raise _err("InvalidFormat", "FORMAT must be image/png")
    bg = None
    if q.get("transparent", "FALSE").upper() != "TRUE":
        m = _COLOR.match(q.get("bgcolor", "0xFFFFFF"))
        if not m:
            raise _err("InvalidParameterValue", "BGCOLOR must be 0xRRGGBB")
        n = int(m.group(1), 16)
        bg = ((n >> 16) & 255, (n >> 8) & 255, n & 255)
    body, truncated = _render(
        session, rls, repo, introspect, masked, user, guest,
        layers=names, styles=styles, bbox=bbox, srid=srid, size=size, bg=bg,
    )  # fmt: skip
    return _png(body, truncated)


def _get_feature_info(q, session, user, guest, introspect, repo, rls, masked_dep) -> Response:
    names, _styles, srid, bbox, (w, h) = _common(q)
    query_layers = _csv(q.get("query_layers"))
    if not query_layers or not all(query_layers):
        raise _err("MissingParameterValue", "QUERY_LAYERS is required")
    if not set(query_layers) <= set(names):
        raise _err("LayerNotDefined", "QUERY_LAYERS must be a subset of LAYERS")
    fmt = q.get("info_format", "text/plain").lower()
    if fmt not in wms.INFO_FORMATS:
        raise _err("InvalidFormat", f"INFO_FORMAT must be one of {', '.join(wms.INFO_FORMATS)}")
    try:
        i = _int(q if "i" in q else {"i": q.get("x")}, "i", 0, w - 1)
        j = _int(q if "j" in q else {"j": q.get("y")}, "j", 0, h - 1)
    except _OwsError as e:
        raise _err("InvalidPoint", e.message) from None
    count = _int({"c": q.get("feature_count", "1")}, "c", 1, FEATURE_INFO_MAX)
    cx = bbox[0] + (i + 0.5) / w * (bbox[2] - bbox[0])
    cy = bbox[3] - (j + 0.5) / h * (bbox[3] - bbox[1])
    tx, ty = (
        FEATURE_INFO_PIXELS * (bbox[2] - bbox[0]) / w,
        FEATURE_INFO_PIXELS * (bbox[3] - bbox[1]) / h,
    )
    pick = _query_bbox((cx - tx, cy - ty, cx + tx, cy + ty), srid, 1, 1, 0)
    ctxs = [
        _layer_ctx(session, user, guest, introspect, masked_dep, n, "QUERY_LAYERS")
        for n in query_layers
    ]
    out: list[tuple[str, dict]] = []
    for col, info, masked in ctxs:
        feats, _more = _read(
            session, rls, repo, col, info, masked,
            bbox=pick, srid=srid, out_srid=4326, limit=count,
        )  # fmt: skip
        out += [(col.id, f) for f in feats[: count - len(out)]]
        if len(out) >= count:
            break
    if fmt == "application/json":
        body = {
            "type": "FeatureCollection",
            "features": [
                {**f, "id": f"{cid}.{f.get('id')}", "properties": f.get("properties") or {}}
                for cid, f in out
            ],
        }
        return Response(json.dumps(body, default=str), media_type="application/json")
    lines = []
    for cid, f in out:
        lines.append(f"{cid}.{f.get('id')}")
        lines += [f"  {k} = {v}" for k, v in (f.get("properties") or {}).items() if v is not None]
    return Response("\n".join(lines) + "\n", media_type="text/plain; charset=utf-8")


# --- WMTS --------------------------------------------------------------------


def _wmts_error(e: _OwsError) -> Response:
    loc = f" locator={wms._a(e.locator)}" if e.locator else ""
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<ows:ExceptionReport xmlns:ows="{wms.NS_OWS}" version="1.1.0">'
        f"<ows:Exception exceptionCode={wms._a(e.code)}{loc}>"
        f"<ows:ExceptionText>{wms._t(e.message)}</ows:ExceptionText></ows:Exception>"
        "</ows:ExceptionReport>"
    )
    return Response(body, e.status, media_type=XML)


def _tile(session, user, guest, introspect, repo, rls, masked, *, layer, style, tms, z, row, col):
    if tms != wms.TMS:
        raise _OwsError(400, "InvalidParameterValue", "TileMatrixSet", "unknown TileMatrixSet")
    if not 0 <= z <= wms.MAX_ZOOM:
        raise _OwsError(400, "TileOutOfRange", "TileMatrix", "TileMatrix out of range")
    n = 2**z
    if not 0 <= row < n:
        raise _OwsError(400, "TileOutOfRange", "TileRow", "TileRow out of range")
    if not 0 <= col < n:
        raise _OwsError(400, "TileOutOfRange", "TileCol", "TileCol out of range")
    try:
        body, truncated = _render(
            session, rls, repo, introspect, masked, user, guest,
            layers=[layer], styles=[style], bbox=wms.tile_bbox(z, col, row),
            srid=3857, size=(256, 256), bg=None,
        )  # fmt: skip
    except _OwsError as e:
        if e.code in ("LayerNotDefined", "StyleNotDefined"):
            raise _OwsError(e.status, "InvalidParameterValue", "Layer", e.message) from None
        raise
    return _png(body, truncated)


def _tile_int(raw: str | None, name: str) -> int:
    try:
        return int(str(raw))
    except ValueError:
        raise _OwsError(400, "InvalidParameterValue", name, f"{name} must be an integer") from None


@router.get("/ows/wmts")
def wmts_endpoint(
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    q = {k.lower(): v for k, v in request.query_params.items()}
    try:
        if q.get("service", "WMTS").upper() != "WMTS":
            raise _OwsError(400, "InvalidParameterValue", "service", "only service=WMTS here")
        op = (q.get("request") or "").lower()
        if op == "getcapabilities":
            return _wmts_capabilities(request, session, user)
        if op == "gettile":
            if q.get("format", "image/png").lower() != "image/png":
                raise _OwsError(400, "InvalidParameterValue", "format", "FORMAT must be image/png")
            for k in ("layer", "tilematrixset", "tilematrix", "tilerow", "tilecol"):
                if not q.get(k):
                    raise _OwsError(400, "MissingParameterValue", k, f"{k} is required")
            return _tile(
                session, user, guest, introspect, repo, rls, masked,
                layer=q["layer"], style=q.get("style", "default"), tms=q["tilematrixset"],
                z=_tile_int(q["tilematrix"], "TileMatrix"),
                row=_tile_int(q["tilerow"], "TileRow"),
                col=_tile_int(q["tilecol"], "TileCol"),
            )  # fmt: skip
        raise _OwsError(
            400,
            "OperationNotSupported" if op else "MissingParameterValue",
            "request",
            "supported operations: GetCapabilities, GetTile",
        )
    except _OwsError as e:
        return _wmts_error(e)
    except HTTPException as e:
        return _wmts_error(_OwsError(e.status_code, "InvalidParameterValue", None, str(e.detail)))


def _wmts_capabilities(request: Request, session, user) -> Response:
    base = f"{str(request.base_url).rstrip('/')}/v1/ows/wmts"
    return Response(
        wms.wmts_capabilities(base, "GeoStudio WMTS", _exposed(session, user)),
        media_type="text/xml",
    )


@router.get("/ows/wmts/1.0.0/WMTSCapabilities.xml")
def wmts_capabilities_rest(
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
) -> Response:
    return _wmts_capabilities(request, session, user)


@router.get("/ows/wmts/1.0.0/{layer}/{style}/{tms}/{z}/{row}/{col}.png")
def wmts_tile_rest(
    layer: str,
    style: str,
    tms: str,
    z: int,
    row: int,
    col: int,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    try:
        return _tile(
            session, user, guest, introspect, repo, rls, masked,
            layer=layer, style=style, tms=tms, z=z, row=row, col=col,
        )  # fmt: skip
    except _OwsError as e:
        return _wmts_error(e)
    except HTTPException as e:
        return _wmts_error(_OwsError(e.status_code, "InvalidParameterValue", None, str(e.detail)))

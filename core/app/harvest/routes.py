# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

import httpx

from app.analytics.aggregate import AggregateMeasure, AggregateRequestBody
from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format, rows_to_format
from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.harvest import live_query, repository as repo
from app.harvest.connectors import get_connector
from app.harvest.egress import EgressBlockedError, build_guarded_client
from app.harvest.jobs import run_harvest_task
from app.harvest.schemas import HarvestSourceCreate, HarvestSourcePatch
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_MAX_LIMIT = 1000


def get_arcgis_http_client():  # overridé en test
    return build_guarded_client()


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")


def _resolve_arcgis_dataset(session: Session, *, item_id: str, user: User) -> str:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="dataset not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if (
        config is None or config.kind != "dataset" or config.config.dataset is None
        or config.config.dataset.source != "arcgis"
    ):
        raise HTTPException(status_code=404, detail="dataset not found")
    arcgis_item_id = config.config.dataset.arcgisItemId
    assert arcgis_item_id is not None
    record = repo.get_feature_layer_record(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if record is None or record.external_url is None:
        raise HTTPException(status_code=404, detail="arcgis layer not found")
    layer_facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if layer_facts is None or not can(session, user_id=user.id, action="read", item=layer_facts):
        raise HTTPException(status_code=404, detail="arcgis layer not found")
    return record.external_url


def _groupby_fields(raw: str | list[str] | None) -> list[str]:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _measure_label(m: AggregateMeasure) -> str:
    return m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)


def _source_json(source) -> dict:
    return {
        "id": source.id, "type": source.type, "url": source.url, "mode": source.mode,
        "enabled": source.enabled, "intervalMinutes": source.interval_minutes,
        "lastRunAt": source.last_run_at.isoformat() if source.last_run_at else None,
        "lastStatus": source.last_status, "lastError": source.last_error,
    }


def _check_copy_support(type_: str, mode: str) -> None:
    if mode != "copy":
        return
    connector = get_connector(type_)
    if not connector.supports_copy:
        raise HTTPException(status_code=400, detail=f"connector {type_!r} does not support copy mode")


def get_task_deferrer():  # overridé en test
    def deferrer(source_id: str, tenant_id: str) -> None:
        run_harvest_task.defer(source_id=source_id, tenant_id=tenant_id)
    return deferrer


@router.post("/harvest/sources", status_code=201)
def create_source(
    body: HarvestSourceCreate,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    _check_copy_support(body.type, body.mode)
    source = repo.create_source(
        session, tenant_id=user.tenant_id, owner_id=user.id, type=body.type,
        url=body.url, mode=body.mode, enabled=body.enabled, interval_minutes=body.intervalMinutes,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.create", object_type="harvest_source", object_id=source.id,
        payload={"type": source.type, "url": source.url},
    )
    return _source_json(source)


@router.get("/harvest/sources")
def list_sources(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_admin(user)
    sources = repo.list_sources(session, tenant_id=user.tenant_id)
    return {"sources": [_source_json(s) for s in sources]}


@router.get("/harvest/layers")
def list_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, tiles_url, _layer_kind in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title, "kind": "raster", "tilesUrl": tiles_url})
    return {"layers": layers}


@router.get("/harvest/feature-layers")
def list_feature_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_feature_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, _external_url in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title})
    return {"layers": layers}


@router.get("/harvest/sources/{source_id}")
def get_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    return _source_json(source)


@router.patch("/harvest/sources/{source_id}")
def patch_source(
    source_id: str, body: HarvestSourcePatch,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    fields = body.model_dump(exclude_unset=True)
    if "intervalMinutes" in fields:
        fields["interval_minutes"] = fields.pop("intervalMinutes")
    if fields.get("mode") == "copy":
        _check_copy_support(source.type, "copy")
    repo.update_source(session, source, **fields)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.update", object_type="harvest_source", object_id=source.id,
        payload={"fields": list(fields)},
    )
    return _source_json(source)


@router.delete("/harvest/sources/{source_id}", status_code=204)
def delete_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.delete", object_type="harvest_source", object_id=source.id, payload={},
    )
    repo.delete_source(session, source)


@router.post("/harvest/sources/{source_id}/run", status_code=202)
def run_source(
    source_id: str,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    defer_task=Depends(get_task_deferrer),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.run", object_type="harvest_source", object_id=source.id, payload={},
    )
    session.commit()
    defer_task(source.id, user.tenant_id)
    return {"status": "queued"}


@router.get("/datasets/{item_id}/arcgis/items")
def get_dataset_arcgis_items(
    item_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0), bbox: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    limit = min(limit, _MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    reserved = {"limit", "offset", "bbox"}
    filters = {k: v for k, v in request.query_params.items() if k not in reserved}
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    try:
        params = live_query.translate_features_query(
            filters=filters, bbox=parsed_bbox, limit=limit, offset=offset,
        )
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_filter", "message": exc.message}]},
        )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    features = raw.get("features", []) if isinstance(raw, dict) else []
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberMatched": offset + len(features),
        "numberReturned": len(features),
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": [],
    }


@router.post("/datasets/{item_id}/arcgis/aggregate")
def get_dataset_arcgis_aggregate(
    item_id: str, body: AggregateRequestBody,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if body.bucket is not None or body.split is not None or body.bins is not None:
        raise HTTPException(
            status_code=400,
            detail="bucket/split/bins are not supported for arcgis-sourced datasets",
        )
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    group_by = _groupby_fields(body.groupBy)
    measures_in = body.measures or [AggregateMeasure(field=body.field, agg=body.agg, label="value")]
    measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
    try:
        params = live_query.translate_aggregate_query(
            group_by=group_by, measures=measures, filters=body.filters, bbox=body.bbox,
        )
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_aggregate", "message": exc.message}]},
        )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
    return {"categoryKey": category_key, "rows": rows}


_EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}


@router.post("/datasets/{item_id}/arcgis/export")
def export_dataset_arcgis_aggregate(
    item_id: str, body: AggregateRequestBody, format: str = Query(...),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if format not in _EXPORT_FORMATS_AGGREGATE:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}]},
        )
    if body.bucket is not None or body.split is not None or body.bins is not None:
        raise HTTPException(
            status_code=400,
            detail="bucket/split/bins are not supported for arcgis-sourced datasets",
        )
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    group_by = _groupby_fields(body.groupBy)
    measures_in = body.measures or [AggregateMeasure(field=body.field, agg=body.agg, label="value")]
    measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
    try:
        params = live_query.translate_aggregate_query(
            group_by=group_by, measures=measures, filters=body.filters, bbox=body.bbox,
        )
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_aggregate", "message": exc.message}]},
        )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    _category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
    content = rows_to_format(rows, format=format)
    item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    filename = export_filename(item.title if item else item_id, format=format)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="item", object_id=item_id,
                payload={"format": format, "mode": "aggregate"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})

# SPDX-License-Identifier: Apache-2.0
"""Tools MCP du domaine analytics : run_analytics_query, explain_dataset
(SP-43 Étape 8 — extrait de app/mcp/tools.py). app.analytics.aggregate est
explicitement hors périmètre de ce découpage (spec SP-43 §7) : seulement
appelé ici, jamais modifié."""

import httpx
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.analytics.aggregate import (
    AggregateMeasure,
    AggregateRequestBody,
    UnknownAggregateField,
    _measure_label,
    run_collection_aggregate,
)
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs import repository as configs_repo
from app.configs.schemas import DatasetPayload
from app.db import request_scoped_session
from app.features import routes as features_routes
from app.harvest import live_query
from app.harvest import repository as harvest_repo
from app.harvest import routes as harvest_routes
from app.harvest.egress import EgressBlockedError
from app.items import repository as items_repo
from app.mcp.tools.identity import require_access, require_collection_read, resolve_actor
from app.sharing.authorization import can
from app.users.models import User


def _resolve_dataset_payload(session, *, user: User, dataset_item_id: str) -> DatasetPayload:
    """Read-access check on the dataset item itself, plus its kind/payload —
    shared first step for run_analytics_query and explain_dataset (Task 3)."""
    require_access(session, user=user, item_id=dataset_item_id, action="read")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if config is None or config.kind != "dataset" or config.config.dataset is None:
        raise ValueError("dataset not found")
    return config.config.dataset


def _resolve_arcgis_external_url(session, *, user: User, dataset_item_id: str) -> str:
    """Mirrors app/harvest/routes.py's _resolve_arcgis_dataset — same
    dataset-read-then-arcgis-layer-read double check as
    /datasets/{id}/arcgis/aggregate — but raises ValueError instead of
    HTTPException, same rationale as require_access above. Re-checks
    dataset-item read access independently of _resolve_dataset_payload's
    own check (harmless, cheap, and keeps this a faithful, self-contained
    mirror of the REST route's helper rather than a partial reimplementation)."""
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=dataset_item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise ValueError("dataset not found")
    config = configs_repo.get_config_by_item(session, dataset_item_id)
    if (
        config is None
        or config.kind != "dataset"
        or config.config.dataset is None
        or config.config.dataset.source != "arcgis"
    ):
        raise ValueError("dataset not found")
    arcgis_item_id = config.config.dataset.arcgisItemId
    assert arcgis_item_id is not None
    record = harvest_repo.get_feature_layer_record(
        session, tenant_id=user.tenant_id, item_id=arcgis_item_id
    )
    if record is None or record.external_url is None:
        raise ValueError("arcgis layer not found")
    layer_facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=arcgis_item_id
    )
    if layer_facts is None or not can(session, user_id=user.id, action="read", item=layer_facts):
        raise ValueError("arcgis layer not found")
    return record.external_url


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def run_analytics_query(
        ctx: Context, datasetId: str, query: AggregateRequestBody
    ) -> dict:
        """Run a structured aggregate query against a dataset (source
        collection or arcgis) — mirrors POST /collections/{id}/aggregate and
        POST /datasets/{id}/arcgis/aggregate, same query contract
        (groupBy/split/measures/filters/bbox/bucket/bins), same permissions.
        Never fabricates SQL (A19). SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = require_collection_read(
                    session, user=user, collection_id=payload.collectionId
                )
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound as exc:
                    raise ValueError("collection backing table not found") from exc
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason) from exc
                conn = features_routes.get_duckdb_connection_factory()()
                try:
                    try:
                        category_key, rows = run_collection_aggregate(
                            conn,
                            base_uri=features_routes.get_analytics_base_uri(),
                            tenant_id=col.tenant_id,
                            collection_id=col.id,
                            table_info=info,
                            request=query,
                        )
                    except UnknownAggregateField as exc:
                        raise ValueError(f"{exc.field}: {exc.message}") from exc
                finally:
                    conn.close()
                return {"categoryKey": category_key, "rows": rows}

            assert payload.arcgisItemId is not None
            if query.bucket is not None or query.split is not None or query.bins is not None:
                raise ValueError("bucket/split/bins are not supported for arcgis-sourced datasets")
            external_url = _resolve_arcgis_external_url(
                session, user=user, dataset_item_id=datasetId
            )
            group_by = (
                query.groupBy
                if isinstance(query.groupBy, list)
                else ([query.groupBy] if query.groupBy else [])
            )
            measures_in = query.measures or [
                AggregateMeasure(field=query.field, agg=query.agg, label="value")
            ]
            measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
            try:
                params = live_query.translate_aggregate_query(
                    group_by=group_by,
                    measures=measures,
                    filters=query.filters,
                    bbox=query.bbox,
                )
            except live_query.ArcgisQueryError as exc:
                raise ValueError(f"{exc.field}: {exc.message}") from exc
            client = harvest_routes.get_arcgis_http_client()
            try:
                raw = live_query.fetch_query(client, external_url, params)
            except EgressBlockedError as exc:
                raise ValueError("arcgis service unavailable") from exc
            except httpx.HTTPError as exc:
                raise ValueError("arcgis service unavailable") from exc
            finally:
                client.close()
            category_key, rows = live_query.aggregate_response(
                raw, group_by=group_by, measures=measures
            )
            return {"categoryKey": category_key, "rows": rows}

    @server.tool()
    async def explain_dataset(ctx: Context, datasetId: str) -> dict:
        """Describe a dataset's queryable fields before calling
        run_analytics_query — author metadata (columns/timeField/
        reactsToExtent) plus introspected field name+type, so an agent
        doesn't have to guess a groupBy/measure field name. No stats, no
        sampling. SP-14l."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = _resolve_dataset_payload(session, user=user, dataset_item_id=datasetId)
            item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=datasetId)
            assert item is not None
            base = {
                "title": item.title,
                "source": payload.source,
                "timeField": payload.timeField,
                "reactsToExtent": payload.reactsToExtent,
                "columns": {k: v.model_dump() for k, v in payload.columns.items()},
            }

            if payload.source == "collection":
                assert payload.collectionId is not None
                col = require_collection_read(
                    session, user=user, collection_id=payload.collectionId
                )
                try:
                    info = introspect_table(session, col.table_name)
                except TableNotFound as exc:
                    raise ValueError("collection backing table not found") from exc
                except UnsupportedTable as exc:
                    raise ValueError(exc.reason) from exc
                schema = table_info_to_schema(info)
                fields = [{"name": f["name"], "type": f["type"]} for f in schema["fields"]]
                return {**base, "fields": fields}

            external_url = _resolve_arcgis_external_url(
                session, user=user, dataset_item_id=datasetId
            )
            client = harvest_routes.get_arcgis_http_client()
            try:
                response = client.get(f"{external_url}?f=json")
                response.raise_for_status()
            except EgressBlockedError as exc:
                raise ValueError("arcgis service unavailable") from exc
            except httpx.HTTPError as exc:
                raise ValueError("arcgis service unavailable") from exc
            finally:
                client.close()
            data = response.json()
            raw_fields = data.get("fields") if isinstance(data, dict) else None
            fields = [
                {"name": f.get("name"), "type": f.get("type")}
                for f in (raw_fields or [])
                if isinstance(f, dict)
            ]
            return {**base, "fields": fields}

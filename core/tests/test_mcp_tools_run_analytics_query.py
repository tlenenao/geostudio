# SPDX-License-Identifier: Apache-2.0
"""run_analytics_query, source "collection" (SP-14l) — mirrors POST
/collections/{id}/aggregate: same DuckDB/GeoParquet CDC read path
(app.analytics.aggregate.run_collection_aggregate). get_duckdb_connection_
factory/get_analytics_base_uri are called as plain functions inside the MCP
tool body (no FastAPI Depends there), so tests monkeypatch the
app.features.routes module attributes directly instead of using
app.dependency_overrides — same substitution app.dependency_overrides does
for the REST route's own test (test_features_aggregate_routes.py), just at
the Python-attribute level instead of the ASGI-DI level."""

import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.features import routes as features_routes
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)

pytestmark = pytest.mark.postgis


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-04"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geom", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _fake_duckdb_factory():
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


@pytest.fixture(autouse=True)
def _local_duckdb(monkeypatch, tmp_path):
    monkeypatch.setattr(
        features_routes, "get_duckdb_connection_factory", lambda: _fake_duckdb_factory
    )
    monkeypatch.setattr(features_routes, "get_analytics_base_uri", lambda: str(tmp_path))
    return tmp_path


def _create_collection_dataset(app_client, collection_id):  # noqa: F811
    result = call_tool(
        app_client,
        "create_dataset",
        {
            "title": "Incidents (dataset)",
            "source": "collection",
            "collectionId": collection_id,
        },
    )
    return result["pk"]


def test_run_analytics_query_collection_source_returns_grouped_counts(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        _write_partition(
            _local_duckdb,
            tenant_id=app_client.tenant.id,
            collection_id=collection_id,
            rows=[
                {
                    "id": 1,
                    "tenant_id": app_client.tenant.id,
                    "titre": "Nid de poule",
                    "_op": "insert",
                    "_lsn": 1,
                    "_ts": 1.0,
                    "geom": Point(2.3, 48.8),
                },
                {
                    "id": 2,
                    "tenant_id": app_client.tenant.id,
                    "titre": "Nid de poule",
                    "_op": "insert",
                    "_lsn": 1,
                    "_ts": 1.0,
                    "geom": Point(2.3, 48.8),
                },
                {
                    "id": 3,
                    "tenant_id": app_client.tenant.id,
                    "titre": "Lampadaire cassé",
                    "_op": "insert",
                    "_lsn": 1,
                    "_ts": 1.0,
                    "geom": Point(2.3, 48.8),
                },
            ],
        )
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        result = call_tool(
            app_client,
            "run_analytics_query",
            {
                "datasetId": dataset_item_id,
                "query": {"groupBy": "titre"},
            },
        )

    assert result["categoryKey"] == "titre"
    assert sorted(result["rows"], key=lambda r: r["titre"]) == [
        {"titre": "Lampadaire cassé", "value": 1},
        {"titre": "Nid de poule", "value": 2},
    ]


def test_run_analytics_query_unknown_group_by_field_errors(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        _write_partition(
            _local_duckdb,
            tenant_id=app_client.tenant.id,
            collection_id=collection_id,
            rows=[
                {
                    "id": 1,
                    "tenant_id": app_client.tenant.id,
                    "titre": "Nid de poule",
                    "_op": "insert",
                    "_lsn": 1,
                    "_ts": 1.0,
                    "geom": Point(2.3, 48.8),
                },
            ],
        )
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        error_text = call_tool_expecting_error(
            app_client,
            "run_analytics_query",
            {
                "datasetId": dataset_item_id,
                "query": {"groupBy": "inconnu"},
            },
        )
    assert "inconnu" in error_text


def test_run_analytics_query_dataset_not_found_errors(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        error_text = call_tool_expecting_error(
            app_client,
            "run_analytics_query",
            {
                "datasetId": "does-not-exist",
                "query": {"groupBy": "titre"},
            },
        )
    assert "not found" in error_text


def _register_incidents_collection_owned_by_other(app_client):  # noqa: F811
    """Same schema/data as _register_incidents_collection, but owned by a
    different user (still public at creation, so create_dataset succeeds).
    Deviation from the plan brief's literal test (which reused
    _register_incidents_collection, owned by mock_user): app.sharing.
    authorization.can() short-circuits `item.owner_id == user_id` before
    even looking at is_public, so flipping is_public on a collection the
    caller owns can never revoke their read access — the brief's version of
    this test could never actually exercise the "collection turned
    unreadable" path it's named for."""
    with app_client.session_factory() as session:
        from sqlalchemy import text

        from app.collections import repository as collections_repo
        from app.collections.ddl import apply_collection_ddl

        other_owner = get_or_create_user(
            session,
            tenant_id=app_client.tenant.id,
            oidc_sub="other-owner-raq-collection-sub",
            username="otherowner-raq-collection",
            email=None,
            first_name="Other",
            last_name="Owner",
        )
        session.execute(
            text(
                "CREATE TABLE incidents (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "titre text, geom geometry(Point, 4326))"
            )
        )
        session.commit()
        apply_collection_ddl(session, "incidents")
        col = collections_repo.create_collection(
            session,
            tenant_id=app_client.tenant.id,
            owner_id=other_owner.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        session.execute(
            text(
                "INSERT INTO incidents (tenant_id, titre, geom) VALUES "
                "(:tid, 'Nid de poule', ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
            ),
            {"tid": app_client.tenant.id},
        )
        session.commit()
        return col.id


def test_run_analytics_query_collection_unreadable_by_caller_errors(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection_owned_by_other(app_client)
        dataset_item_id = _create_collection_dataset(app_client, collection_id)
        # Simulate the share being revoked after the dataset was created: flip
        # the collection private with no share, independent of the dataset item
        # (which stays readable — it's owned by mock_user, the caller).
        with app_client.session_factory() as session:
            from app.collections.models import Collection

            session.query(Collection).filter(Collection.id == collection_id).update(
                {"is_public": False}
            )
            session.commit()
        error_text = call_tool_expecting_error(
            app_client,
            "run_analytics_query",
            {
                "datasetId": dataset_item_id,
                "query": {"groupBy": "titre"},
            },
        )
    assert "not found" in error_text

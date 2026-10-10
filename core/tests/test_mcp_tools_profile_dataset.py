# SPDX-License-Identifier: Apache-2.0
"""profile_dataset (REV-117) — jumeau MCP de GET /collections/{id}/profile ;
mêmes fixtures que run_analytics_query (lac local, postgis réel)."""

from shapely.geometry import Point

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)
from tests.test_mcp_tools_run_analytics_query import (  # noqa: F401
    _create_collection_dataset,
    _local_duckdb,
    _write_partition,
    pytestmark,
)


def _row(tenant_id, i, titre):
    return {
        "id": i,
        "tenant_id": tenant_id,
        "titre": titre,
        "_op": "insert",
        "_lsn": 1,
        "_ts": 1.0,
        "geom": Point(2.3, 48.8),
    }


def test_profile_dataset_returns_column_profile(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        tid = app_client.tenant.id
        _write_partition(
            _local_duckdb,
            tenant_id=tid,
            collection_id=collection_id,
            rows=[_row(tid, 1, "Nid"), _row(tid, 2, "Nid"), _row(tid, 3, "Lampadaire")],
        )
        dataset_id = _create_collection_dataset(app_client, collection_id)
        result = call_tool(app_client, "profile_dataset", {"datasetId": dataset_id})

    assert result["rowCount"] == 3 and result["pending"] is False
    titre = next(c for c in result["columns"] if c["name"] == "titre")
    assert titre["topValues"][0] == {"value": "Nid", "count": 2}
    assert result["geometry"]["types"] == [{"type": "POINT", "count": 3}]


def test_profile_dataset_unknown_dataset_errors(app_client, _local_duckdb):  # noqa: F811
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "profile_dataset", {"datasetId": "does-not-exist"}
        )
    assert error_text

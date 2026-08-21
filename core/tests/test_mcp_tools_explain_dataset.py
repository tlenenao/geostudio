# SPDX-License-Identifier: Apache-2.0
"""explain_dataset, source "collection" (SP-14l) — introspected field
name+type (via app.collections.schema_json.table_info_to_schema, the same
helper create_form_app already uses) plus author metadata as stored on the
DatasetPayload. No stats, no sampling (design §1 non-buts)."""

import pytest

from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error  # noqa: F401
from tests.test_mcp_tools_query_features import (  # noqa: F401
    _register_incidents_collection,
    app_client,
)

pytestmark = pytest.mark.postgis


def test_explain_dataset_collection_source_returns_fields_and_metadata(app_client):  # noqa: F811
    with app_client:
        collection_id = _register_incidents_collection(app_client)
        create_result = call_tool(
            app_client,
            "create_dataset",
            {
                "title": "Incidents (dataset)",
                "source": "collection",
                "collectionId": collection_id,
                "columns": {
                    "titre": {"label": "Titre de l'incident", "description": None, "format": None}
                },
                "timeField": None,
                "reactsToExtent": True,
            },
        )
        result = call_tool(app_client, "explain_dataset", {"datasetId": create_result["pk"]})

    assert result["title"] == "Incidents (dataset)"
    assert result["source"] == "collection"
    assert result["reactsToExtent"] is True
    assert result["columns"]["titre"]["label"] == "Titre de l'incident"
    field_names = {f["name"] for f in result["fields"]}
    assert "titre" in field_names


def test_explain_dataset_dataset_not_found_errors(app_client):  # noqa: F811
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "explain_dataset", {"datasetId": "does-not-exist"}
        )
    assert "not found" in error_text

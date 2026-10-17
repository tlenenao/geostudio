# SPDX-License-Identifier: Apache-2.0
"""AUD-022 : un gabarit instancié pointe sur les collections choisies, pas sur des slugs
fictifs."""

import pytest

from app.collections.models import Collection
from app.configs import repository as configs_repo
from app.configs.builder_templates import (
    build_config_from_template,
    template_data_sources,
    template_ids,
)
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)

TEMPLATE = "application-de-saisie"


def test_template_data_sources_lists_the_fictitious_slugs():
    assert template_data_sources(TEMPLATE) == ["incidents"]
    assert template_data_sources("two-column") == []


def test_every_template_data_source_is_bindable():
    for template_id in template_ids():
        slugs = template_data_sources(template_id)
        cfg = build_config_from_template(template_id, bindings={s: "col-123" for s in slugs})
        layers = [ds.layer for ds in cfg.dataSources if getattr(ds, "layer", None)]
        assert all(layer == "col-123" for layer in layers), template_id


def test_unknown_binding_is_refused():
    with pytest.raises(ValueError, match="inexistant"):
        build_config_from_template(TEMPLATE, bindings={"inexistant": "col-1"})


def _create(collection_id):
    return {
        "kind": "app",
        "title": "Saisie",
        "template": TEMPLATE,
        "bindings": {"incidents": collection_id},
    }


def test_mcp_create_item_binds_template_sources_to_readable_collections(app_client):  # noqa: F811
    with app_client.session_factory() as s:
        s.add(
            Collection(
                id="incidents-reels",
                tenant_id=app_client.tenant.id,
                owner_id=app_client.mock_user.id,
                table_name="incidents_reels",
                title="Incidents",
                pk_column="id",
                is_public=False,
                editable=True,
            )
        )
        s.commit()
    with app_client:
        created = call_tool(app_client, "create_item", _create("incidents-reels"))
        err = call_tool_expecting_error(app_client, "create_item", _create("autre"))
    assert "collection not found" in err
    with app_client.session_factory() as s:
        cfg = configs_repo.get_config_by_item(s, created["pk"])
        assert [ds.layer for ds in cfg.config.dataSources] == ["incidents-reels"]

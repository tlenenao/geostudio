### Task 1: `create_dataset` tool

**Files:**
- Modify: `core/app/mcp/tools.py`
- Modify: `core/tests/test_mcp_read_only_mode.py` (extend the existing generic read-only-mode coverage — this file already asserts `READ_ONLY_TOOLS` equals an exact set of 4 tool names; adding a 5th tool without updating it would break that test)
- Test: `core/tests/test_mcp_tools_dataset_create.py` (new)

**Interfaces:**
- Produces: MCP tool `create_dataset(ctx, title: str, source: Literal["collection","arcgis"], collectionId: str | None = None, arcgisItemId: str | None = None, columns: dict[str, DatasetColumnMeta] | None = None, timeField: str | None = None, reactsToExtent: bool = False) -> ItemRead`.
- Produces: private helper `_validate_dataset(session, config: BuilderConfig, *, user: User) -> None` (raises `ValueError`), reused by no other task.
- `"create_dataset"` added to `READ_ONLY_TOOLS`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_mcp_tools_dataset_create.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""create_dataset (SP-14l) — mirrors POST /configs with kind="dataset":
same DatasetPayload construction, same per-source readability validation
(app.configs.dataset_validation) as the REST route. SQLite is enough here —
neither source variant needs real PostGIS introspection at creation time,
only catalog metadata (Collection row / harvested "external" item row)."""
from sqlalchemy import select

from app.audit.models import AuditLog
from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.users.repository import get_or_create_user

from tests.test_mcp_tools_create import app_client, call_tool, call_tool_expecting_error  # noqa: F401


def _register_collection(app_client, *, public=True, owner=None):
    with app_client.session_factory() as session:
        col = collections_repo.create_collection(
            session, tenant_id=app_client.tenant.id, owner_id=(owner or app_client.mock_user).id,
            table_name="incidents", title="Incidents", description="", is_public=public,
            pk_column="id", geometry_column="geom", geometry_type="Point", srid=4326,
        )
        session.commit()
        return col.id


def _register_arcgis_layer(app_client, *, public=True, owner=None):
    with app_client.session_factory() as session:
        layer_owner = owner or app_client.mock_user
        source = harvest_repo.create_source(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            session, tenant_id=app_client.tenant.id, owner_id=layer_owner.id,
            resource_type="external", title="Bâtiments",
        )
        if public:
            items_repo.set_is_public(
                session, tenant_id=app_client.tenant.id, item_id=layer_item.id, is_public=True,
            )
        harvest_repo.create_record(
            session, tenant_id=app_client.tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0",
            layer_kind="feature",
        )
        session.commit()
        return layer_item.id


def test_create_dataset_collection_source_creates_item_and_config(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.kind == "dataset"
        assert config.config.dataset.source == "collection"
        assert config.config.dataset.collectionId == collection_id


def test_create_dataset_arcgis_source_creates_item_and_config(app_client):
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })

    assert result["resourceType"] == "dataset"
    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.source == "arcgis"
        assert config.config.dataset.arcgisItemId == arcgis_item_id


def test_create_dataset_accepts_columns_time_field_and_reacts_to_extent(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        result = call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
            "columns": {"titre": {"label": "Titre", "description": None, "format": None}},
            "timeField": "created_at", "reactsToExtent": True,
        })

    with app_client.session_factory() as session:
        config = configs_repo.get_config_by_item(session, result["pk"])
        assert config.config.dataset.columns["titre"].label == "Titre"
        assert config.config.dataset.timeField == "created_at"
        assert config.config.dataset.reactsToExtent is True


def test_create_dataset_writes_audit_log_with_agent_actor(app_client):
    with app_client:
        collection_id = _register_collection(app_client)
        call_tool(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })

    with app_client.session_factory() as session:
        rows = list(session.scalars(select(AuditLog)))
        actions = {r.action for r in rows}
        assert "item.create" in actions
        assert "config.create" in actions
        assert all(r.actor_kind == "agent" for r in rows)


def test_create_dataset_unreadable_collection_errors_without_leaking_existence(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd-sub",
            username="otherowner-cd", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        collection_id = _register_collection(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Incidents (dataset)", "source": "collection", "collectionId": collection_id,
        })
    assert "not found" in error_text


def test_create_dataset_unreadable_arcgis_layer_errors(app_client):
    with app_client.session_factory() as session:
        other_owner = get_or_create_user(
            session, tenant_id=app_client.tenant.id, oidc_sub="other-owner-cd2-sub",
            username="otherowner-cd2", email=None, first_name="Other", last_name="Owner",
        )
        session.commit()
    with app_client:
        arcgis_item_id = _register_arcgis_layer(app_client, public=False, owner=other_owner)
        error_text = call_tool_expecting_error(app_client, "create_dataset", {
            "title": "Bâtiments (live)", "source": "arcgis", "arcgisItemId": arcgis_item_id,
        })
    assert "not found" in error_text
```

Extend `core/tests/test_mcp_read_only_mode.py`:

```python
def test_read_only_tools_constant_matches_the_five_write_tools():
    assert READ_ONLY_TOOLS == {
        "save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset",
    }
```

Replace the old `test_read_only_tools_constant_matches_the_four_write_tools` with the function above (same file, same fixtures — just the one function body and its name change), and add this new test right after `test_create_form_app_refuses_in_read_only_mode`:

```python
def test_create_dataset_refuses_in_read_only_mode(app_client, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    with app_client:
        error_text = call_tool_expecting_error(
            app_client, "create_dataset",
            {"title": "X", "source": "collection", "collectionId": "does-not-exist"},
        )
    assert READ_ONLY_MESSAGE in error_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_mcp_tools_dataset_create.py tests/test_mcp_read_only_mode.py -v`
Expected: `test_mcp_tools_dataset_create.py` fails with something like `AssertionError: tool create_dataset errored: ... Unknown tool: create_dataset` (or a `ValueError`/`KeyError` from FastMCP about an unregistered tool name). `test_read_only_tools_constant_matches_the_five_write_tools` fails because `READ_ONLY_TOOLS` still has 4 entries. `test_create_dataset_refuses_in_read_only_mode` fails the same "unknown tool" way.

- [ ] **Step 3: Implement `create_dataset`**

In `core/app/mcp/tools.py`, add to the imports at the top:

```python
from fastapi import HTTPException

from app.configs.dataset_validation import validate_dataset_payload
from app.configs.schemas import DatasetColumnMeta, DatasetPayload
```

(`BuilderConfig`, `Literal`, `items_repo`, `configs_repo`, `write_audit`, `is_read_only_mode` are already imported.)

Change the `READ_ONLY_TOOLS` line to:

```python
READ_ONLY_TOOLS = {"save_app_config", "create_item", "create_form_app", "set_sharing", "create_dataset"}
```

Add this private helper right after `_validate_extension_scope` (same file, module level, before `_parse_bbox_tuple`):

```python
def _validate_dataset(session, config: BuilderConfig, *, user: User) -> None:
    """Mirrors app/configs/routes.py's call to validate_dataset_payload — same
    per-source (collection/arcgis) readability check the REST route runs on
    POST /configs and PUT /configs/{by-item} — but raises ValueError instead
    of HTTPException, same rationale as _require_access above. Without this
    call, create_dataset could create a dataset pointing at a collection or
    arcgis layer invisible to the caller."""
    try:
        validate_dataset_payload(session, config, user=user)
    except HTTPException as exc:
        raise ValueError(exc.detail) from exc
```

Add the tool itself inside `register_tools`, right after `create_form_app` and before `get_sharing`:

```python
    @server.tool()
    async def create_dataset(
        ctx: Context,
        title: str,
        source: Literal["collection", "arcgis"],
        collectionId: str | None = None,
        arcgisItemId: str | None = None,
        columns: dict[str, DatasetColumnMeta] | None = None,
        timeField: str | None = None,
        reactsToExtent: bool = False,
    ) -> ItemRead:
        """Create a shared dataset (source collection or arcgis) — mirrors
        POST /configs with kind="dataset" (the path
        itemClient.ts::createDatasetItem uses). SP-14l."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = _resolve_actor(session, access_token)
            payload = DatasetPayload(
                source=source, collectionId=collectionId, arcgisItemId=arcgisItemId,
                columns=columns or {}, timeField=timeField, reactsToExtent=reactsToExtent,
            )
            config = BuilderConfig(version=1, kind="dataset", dataset=payload)
            _validate_dataset(session, config, user=user)
            item = items_repo.create_item(
                session, tenant_id=user.tenant_id, owner_id=user.id,
                resource_type="dataset", title=title,
            )
            config_result = configs_repo.create_config(
                session, config, item_id=item.id, tenant_id=user.tenant_id
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title},
            )
            write_audit(
                session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                action="config.create", object_type="config", object_id=config_result.id,
                payload={"title": title, "kind": "dataset"},
            )
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item.id)
            assert result is not None
            return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_mcp_tools_dataset_create.py tests/test_mcp_read_only_mode.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add core/app/mcp/tools.py core/tests/test_mcp_tools_dataset_create.py core/tests/test_mcp_read_only_mode.py
git commit -m "feat(core): mcp create_dataset tool (SP-14l)"
```

---


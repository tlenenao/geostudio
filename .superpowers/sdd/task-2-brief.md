### Task 2: Core — `harvest_repo.get_feature_layer_record` + `list_feature_layer_records`

**Files:**
- Modify: `core/app/harvest/repository.py`
- Test: `core/tests/test_harvest_repository.py`

**Interfaces:**
- Consumes: `HarvestRecord` model (existing, `core/app/harvest/models.py`).
- Produces: `get_feature_layer_record(session, *, tenant_id: str, item_id: str) -> HarvestRecord | None` (used by Task 1's validator and Task 5's routes). `list_feature_layer_records(session, *, tenant_id: str, q: str | None = None) -> list[Row]` where each row is `(item_id, title, external_url)` (used by Task 3's route).

- [ ] **Step 1: Write failing tests**

Append to `core/tests/test_harvest_repository.py` (open it first to match its existing fixture style — it already has `session`/`tenant` fixtures for this module; use the same pattern as the surrounding tests for `create_record`/`list_layer_records`):

```python
def test_get_feature_layer_record_returns_feature_kind_only(session, tenant):
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id="u1", type="arcgis",
        url="https://gis.example.com/FeatureServer", mode="reference",
        enabled=True, interval_minutes=None,
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="a",
        item_id="item-feature", collection_id=None, content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="b",
        item_id="item-raster", collection_id=None, content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x", layer_kind="raster",
    )
    found = harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="item-feature")
    assert found is not None
    assert found.external_url == "https://gis.example.com/FeatureServer/0"
    assert harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="item-raster") is None
    assert harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="no-such-item") is None


def test_list_feature_layer_records_excludes_raster_and_filters_by_q(session, tenant):
    from app.items import repository as items_repo

    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id="u1", type="arcgis",
        url="https://gis.example.com/FeatureServer", mode="reference",
        enabled=True, interval_minutes=None,
    )
    feature_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id="u1", resource_type="external", title="Bâtiments",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="a",
        item_id=feature_item.id, collection_id=None, content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
    )
    raster_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id="u1", resource_type="external", title="Ortho",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="b",
        item_id=raster_item.id, collection_id=None, content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x", layer_kind="raster",
    )
    session.commit()

    rows = harvest_repo.list_feature_layer_records(session, tenant_id=tenant.id)
    ids = {r[0] for r in rows}
    assert feature_item.id in ids
    assert raster_item.id not in ids

    filtered = harvest_repo.list_feature_layer_records(session, tenant_id=tenant.id, q="zzz-nomatch")
    assert filtered == []
```

If `core/tests/test_harvest_repository.py` does not already have `session`/`tenant` fixtures with those exact names, adapt the two tests above to whatever fixture names the file already uses for an in-memory SQLite session and a seeded tenant (read the file first — do not guess).

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -v -k "feature_layer"`
Expected: FAIL with `AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'`.

- [ ] **Step 3: Implement both functions**

In `core/app/harvest/repository.py`, add after `list_layer_records`:

```python
def get_feature_layer_record(
    session: Session, *, tenant_id: str, item_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.item_id == item_id,
            HarvestRecord.layer_kind == "feature",
        )
    )


def list_feature_layer_records(session: Session, *, tenant_id: str, q: str | None = None):
    stmt = (
        select(HarvestRecord.item_id, Item.title, HarvestRecord.external_url)
        .join(Item, Item.id == HarvestRecord.item_id)
        .where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.layer_kind == "feature",
        )
    )
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    return list(session.execute(stmt).all())
```

- [ ] **Step 4: Run to verify these tests pass, then re-run Task 1's blocked test**

Run: `cd core && uv run pytest tests/test_harvest_repository.py tests/test_create_dataset_arcgis.py -v`
Expected: all PASS now (Task 1's `test_create_dataset_arcgis.py` was blocked only on `get_feature_layer_record` existing).

- [ ] **Step 5: Run the full core suite to catch regressions**

Run: `cd core && uv run pytest`
Expected: same pass count as before this task, plus the new tests; no `postgis`-marked test count changes (still skipped without Docker).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/repository.py tests/test_harvest_repository.py tests/test_create_dataset_arcgis.py
git commit -m "feat(core): harvest repo gains get/list_feature_layer_record (SP-14k)"
```

---


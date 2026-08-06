## Task 8: End-to-end integration test — full pipeline run through the sidecar

**Files:**
- Test: `core/tests/test_pipeline_runtime.py`

**Interfaces:**
- Consumes: everything from Tasks 1–7. No new production code — this task
  is purely a test that proves the whole chain works together, mirroring
  SP-15c's own Task 8 (`test_use_case_3_incidents_near_schools_by_commune`).

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_runtime.py`:

```python
@pytest.mark.postgis
@pytest.mark.qgis
def test_transform_qgis_end_to_end_dissolve_then_write(pg_engine, monkeypatch, tmp_path, qgis_worker_url):
    """reader.collection (2 adjacent polygons, same region) ->
    transform.qgis(native:dissolve) -> writer.collection: full run_pipeline,
    real Postgres write, real sidecar round-trip. Two squares sharing an
    edge dissolve (grouped by "region", both "a") into one polygon feature —
    proves the qgis dispatch composes with the pre-existing writer.collection
    path unchanged (design §6, 'no fusion to break, node-by-node as before')."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('dissolved_out', :t, :o, 'dissolved_out', 'Dissolved', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            # geometry(MultiPolygon, 4326), PAS geometry(Polygon, 4326) : verified
            # against a real qgis_process run during plan-writing that
            # native:dissolve always outputs MultiPolygon (even for a single
            # dissolved group of 1 feature) — ogrinfo on the real output showed
            # "Geometry: Multi Polygon". Using Polygon here would make
            # validate_feature reject every row ("expected Polygon").
            "CREATE TABLE dissolved_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, geometry geometry(MultiPolygon, 4326))"
        ))
        apply_collection_ddl(s, "dissolved_out")
        s.commit()

        polygons_info = dataclasses.replace(
            TABLE_INFO, table_name="polygons_in", geometry_type="Polygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )
        out_info = dataclasses.replace(
            # geometry_type="MultiPolygon" (not "Polygon") — see the CREATE
            # TABLE comment above: native:dissolve's real output type, verified.
            TABLE_INFO, table_name="dissolved_out", geometry_type="MultiPolygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )

        def _table_info(session, collection_id):
            return out_info if collection_id == "dissolved_out" else polygons_info

        monkeypatch.setattr(runtime, "_table_info_for_collection", _table_info)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="polygons_in", rows=[
            {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(0, 0), (0, 2), (1, 2), (1, 0)])},
            {"id": 2, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(1, 0), (1, 2), (2, 2), (2, 0)])},
        ])

        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons_in"}},
                {"id": "t1", "kind": "transform", "op": "transform.qgis",
                 "params": {"algorithmId": "native:dissolve",
                            "params": {"FIELD": "region", "SEPARATE_DISJOINT": False}}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "dissolved_out"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
        })
        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
        )
        s.commit()

        rows = s.execute(text("SELECT region FROM dissolved_out")).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "a"
        assert any(stat.op == "writer.collection" and stat.rowCount == 1 for stat in stats)

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE dissolved_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

- [ ] **Step 2: Run test to verify it's skipped without infra**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k transform_qgis_end_to_end -v`
Expected (no `CORE_TEST_DATABASE_URL`/`CORE_TEST_QGIS_WORKER_URL` set): 1
skipped.

- [ ] **Step 3: Run test against real infra**

Run:
```bash
export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
cd core && uv run pytest tests/test_pipeline_runtime.py -k transform_qgis_end_to_end -v
```
Expected: 1 passed — the two adjacent squares (sharing the edge `x=1`)
dissolve into a single polygon feature grouped by `region="a"`, written
into the real `dissolved_out` Postgres table via the unchanged
`writer.collection` path.

- [ ] **Step 4: Run the full core test suite**

Run:
```bash
export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gis_test
export CORE_TEST_QGIS_WORKER_URL=http://localhost:8300
export CORE_TEST_QGIS_SCRATCH_DIR=/scratch
cd core && uv run pytest -q
```
Expected: all tests pass (previous count + this plan's new tests), 0
regressions. Then also run `uv run lint-imports` (expect `Contracts: 1
kept, 0 broken` — this plan adds no new cross-module imports that violate
the layered-architecture contract: `runtime.py`/`compiler.py`/
`routes.py`/`jobs.py` already import from `app.pipelines.ops.schemas`,
`qgis_algorithms.py` is a new file in that same already-permitted
package).

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_pipeline_runtime.py
git commit -m "test(core): end-to-end scenario for transform.qgis dissolve -> writer.collection"
```

---

## Final check (after all 8 tasks)

Run the full suite one more time with all env vars set (Task 8 Step 4's
commands), plus:

```bash
cd shell && npx vitest run && npx tsc --noEmit
```

Expected: unchanged shell test count and a clean typecheck — this plan
never touches `shell/`, so this is purely a regression guard, not expected
to surface anything new.

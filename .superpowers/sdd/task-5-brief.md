## Task 5: Wire into the runtime — `_prepare()` dispatch, end-to-end tests

**Files:**
- Modify: `core/app/pipelines/runtime.py`
- Test: `core/tests/test_pipeline_runtime.py`
- Test: `core/tests/test_pipeline_config_validation.py` (one new regression test, no code change to `config_validation.py`)

**Interfaces:**
- Consumes: `app.pipelines.connector_runtime.materialize_rest_connector`,
  `materialize_postgres_connector`, `ConnectorRuntimeError` (Tasks 3/4);
  `ReaderConnectorRestParams`, `ReaderConnectorPostgresParams` (Task 1).
- Produces: no new public interface — `_prepare()`'s reader-materialization
  loop now dispatches on `node.op` instead of assuming `reader.collection`.
  This is the terminal task of the plan.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_runtime.py`:

```python
def test_preview_reader_connector_rest_feeds_downstream_filter(tmp_path, monkeypatch, httpserver):
    from app.pipelines import egress as pipelines_egress
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    httpserver.expect_request("/items").respond_with_json(
        [{"id": 1, "pop": 10}, {"id": 2, "pop": 5}, {"id": 3, "pop": 20}]
    )
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.connector.rest",
         "params": {"baseUrl": httpserver.url_for("/"), "path": "items"}},
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "pop > 8"}},
        {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "out.csv"}},
    ]
    edges = [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": edges})

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {1, 3}  # pop=5 filtered out


def test_preview_reader_connector_missing_secret_raises_pipeline_runtime_error(tmp_path):
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.connector.postgres",
         "params": {"secretName": "does-not-exist", "query": "SELECT 1"}},
    ]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": []})

    from app.db import init_db, make_engine, make_session_factory
    from app.tenants.repository import get_or_create_default_tenant
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        with pytest.raises(runtime.PipelineRuntimeError, match="not found"):
            runtime.preview_pipeline(
                session=session, payload=payload, tenant_id=tenant.id, user=None, up_to="r1",
                endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
                base_uri=str(tmp_path), limit=50,
            )


def test_run_pipeline_reader_connector_rest_never_leaks_secret_value(tmp_path, monkeypatch, httpserver):
    from app.pipelines import egress as pipelines_egress
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)
    from app.db import init_db, make_engine, make_session_factory
    from app.secrets import repository as secrets_repo
    from app.secrets.crypto import encrypt
    from app.tenants.repository import get_or_create_default_tenant

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as session:
        monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
        tenant = get_or_create_default_tenant(session)
        ciphertext, nonce = encrypt({"kind": "bearer_token", "token": "s3cr3t-leak-check"})
        secrets_repo.create_secret(
            session, tenant_id=tenant.id, created_by="u1", name="my-bearer", kind="bearer_token",
            ciphertext=ciphertext, nonce=nonce,
        )
        session.commit()

        httpserver.expect_request(
            "/items", headers={"Authorization": "Bearer s3cr3t-leak-check"},
        ).respond_with_json([{"id": 1, "name": "a"}])
        payload_nodes = [
            {"id": "r1", "kind": "reader", "op": "reader.connector.rest",
             "params": {"baseUrl": httpserver.url_for("/"), "path": "items", "secretName": "my-bearer"}},
        ]
        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": []})

        rows = runtime.preview_pipeline(
            session=session, payload=payload, tenant_id=tenant.id, user=None, up_to="r1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path), limit=50,
        )
        assert "s3cr3t-leak-check" not in str(rows)
```

Append to `core/tests/test_pipeline_config_validation.py`:

```python
def test_reader_connector_node_saves_without_secret_or_query_check(env):
    # Design §6 : seule la FORME des params est vérifiée à la sauvegarde —
    # ni l'existence de "does-not-exist" comme secret, ni la validité SQL de
    # "not even sql" sont vérifiées ici (elles échoueraient proprement à
    # l'EXÉCUTION, cf. test_pipeline_runtime.py). Une sauvegarde réussie ici
    # n'est pas un bug.
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append({
        "id": "r2", "kind": "reader", "op": "reader.connector.postgres",
        "params": {"secretName": "does-not-exist", "query": "not even sql"},
    })
    response = env.post("/configs", json=body)
    assert response.status_code == 201
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -k reader_connector -v`
Expected: FAIL — `pydantic.ValidationError`/`PipelineRuntimeError: unknown reader op 'reader.connector.rest'`
(the `_prepare()` loop still hard-codes `ReaderCollectionParams.model_validate(node.params)` for every reader node).

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -k reader_connector -v`
Expected: this one already passes (config_validation.py needs no change) —
confirms the "no code change needed" claim from Global Constraints instead
of silently assuming it.

- [ ] **Step 3: Wire the dispatch into `_prepare()`**

Modify `core/app/pipelines/runtime.py` — add to the imports, after the
existing `from app.pipelines.ops.schemas import (...)` block:

```python
from app.pipelines import connector_runtime
from app.pipelines.ops.schemas import (
    ReaderCollectionParams, ReaderConnectorPostgresParams, ReaderConnectorRestParams,
    TransformAggregateParams, TransformCountWithinParams, TransformDeriveParams,
    TransformFilterParams, TransformH3AggregateParams, TransformIntersectionParams,
    TransformJoinParams, TransformQgisParams, WriterCollectionParams, WriterDatasetParams,
    WriterExportParams,
)
```

Replace the reader-materialization loop inside `_prepare()` (currently):

```python
    for node in ordered:
        if node.kind != "reader":
            continue
        p = ReaderCollectionParams.model_validate(node.params)
        table_name = _require_readable_collection_id(
            session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
        )
        table_info = _table_info_for_collection(session, table_name)
        view_name = f"node_{node.id}"
        _materialize_reader(
            conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
            collection_id=p.collectionId, table_info=table_info,
        )
        view_by_node[node.id] = view_name
        srid_by_node[node.id] = table_info.srid or 4326
```

with:

```python
    for node in ordered:
        if node.kind != "reader":
            continue
        view_name = f"node_{node.id}"
        if node.op == "reader.collection":
            p = ReaderCollectionParams.model_validate(node.params)
            table_name = _require_readable_collection_id(
                session, tenant_id=tenant_id, user=user, collection_id=p.collectionId,
            )
            table_info = _table_info_for_collection(session, table_name)
            _materialize_reader(
                conn, view_name=view_name, base_uri=base_uri, tenant_id=tenant_id,
                collection_id=p.collectionId, table_info=table_info,
            )
            srid_by_node[node.id] = table_info.srid or 4326
        elif node.op == "reader.connector.rest":
            p = ReaderConnectorRestParams.model_validate(node.params)
            try:
                connector_runtime.materialize_rest_connector(
                    conn, session=session, tenant_id=tenant_id, node_id=node.id,
                    params=p, view_name=view_name,
                )
            except connector_runtime.ConnectorRuntimeError as exc:
                raise PipelineRuntimeError(str(exc)) from exc
            srid_by_node[node.id] = 4326
        elif node.op == "reader.connector.postgres":
            p = ReaderConnectorPostgresParams.model_validate(node.params)
            try:
                connector_runtime.materialize_postgres_connector(
                    conn, session=session, tenant_id=tenant_id, node_id=node.id,
                    params=p, view_name=view_name,
                )
            except connector_runtime.ConnectorRuntimeError as exc:
                raise PipelineRuntimeError(str(exc)) from exc
            srid_by_node[node.id] = 4326
        else:
            raise PipelineRuntimeError(f"unknown reader op '{node.op}'")
        view_by_node[node.id] = view_name
```

(`srid_by_node[node.id] = 4326` for both connector ops is a harmless
default — design §3.2/non-goals: connector output carries no geometry
column in v0, so this value is never actually consulted by a spatial
transform; a pipeline author who chains a spatial op directly after a
connector reader gets a clean DuckDB error about the missing geometry
column, not a wrong-SRID bug.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v`
Expected: all pass, including the 3 new `reader_connector` tests.

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: all pass.

- [ ] **Step 5: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — `runtime.py` now imports
`app.pipelines.connector_runtime` (same layer, always allowed) and
transitively `app.secrets`/`app.analytics` (already-legal directions,
confirmed in Global Constraints); `app.pipelines.egress` still imports
nothing from `app.harvest`.

- [ ] **Step 6: Run the full core test suite to confirm no regression**

Run: `cd core && uv run pytest -v`
Expected: all pre-existing tests still pass — this plan is additive only
(2 new op catalog entries, 1 new guard module, 1 new connector-runtime
module, 1 dispatch branch in an existing loop; no route, MCP tool, or
existing op's behavior changed).

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py \
  core/tests/test_pipeline_config_validation.py
git commit -m "feat(core): pipelines — wire reader.connector.rest/postgres into runtime dispatch"
```

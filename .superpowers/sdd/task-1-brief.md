## Task 1: Op catalog — `ReaderConnectorRestParams` / `ReaderConnectorPostgresParams`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Produces: `app.pipelines.ops.schemas.ReaderConnectorRestParams`,
  `ReaderConnectorPostgresParams` (Pydantic `BaseModel`s), plus two new
  entries each in `OP_KINDS`/`OP_PARAMS` keyed `"reader.connector.rest"` /
  `"reader.connector.postgres"`. Consumed by Task 5 (`runtime.py`'s
  `_prepare()` dispatch) and Task 3/4 (`connector_runtime.py` functions take
  an already-validated instance of these models as their `params` argument).

- [ ] **Step 1: Write the failing tests**

Modify `core/tests/test_pipeline_ops_schemas.py` — change
`test_all_fifteen_ops_are_registered` (this test asserts an **exact** set
equality; adding two ops without updating it would break it) to:

```python
def test_all_seventeen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "writer.dataset",
        "transform.qgis",
        "reader.connector.rest", "reader.connector.postgres",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)
```

Append at the end of the file:

```python
def test_reader_connector_ops_are_kind_reader():
    assert OP_KINDS["reader.connector.rest"] == "reader"
    assert OP_KINDS["reader.connector.postgres"] == "reader"


def test_reader_connector_rest_minimal_params():
    params = parse_op_params("reader.connector.rest", {"baseUrl": "https://api.example.com/"})
    assert params.path == ""
    assert params.method == "GET"
    assert params.query == {}
    assert params.headers == {}
    assert params.recordsPath is None
    assert params.paginator == "none"
    assert params.paginatorConfig == {}
    assert params.secretName is None


def test_reader_connector_rest_rejects_non_http_base_url():
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.rest", {"baseUrl": "ftp://example.com/"})


def test_reader_connector_rest_full_params():
    params = parse_op_params("reader.connector.rest", {
        "baseUrl": "https://api.example.com/",
        "path": "v1/items",
        "method": "POST",
        "query": {"limit": "100"},
        "headers": {"User-Agent": "geostudio"},
        "recordsPath": "data.items",
        "paginator": "page_number",
        "paginatorConfig": {"pageParam": "page"},
        "secretName": "my-api-key",
    })
    assert params.path == "v1/items"
    assert params.method == "POST"
    assert params.recordsPath == "data.items"
    assert params.paginator == "page_number"
    assert params.secretName == "my-api-key"


def test_reader_connector_rest_rejects_unknown_paginator():
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.rest", {
            "baseUrl": "https://api.example.com/", "paginator": "not-a-paginator",
        })


def test_reader_connector_postgres_requires_secret_name_and_query():
    params = parse_op_params(
        "reader.connector.postgres",
        {"secretName": "warehouse-pg", "query": "SELECT * FROM towns"},
    )
    assert params.secretName == "warehouse-pg"
    assert params.query == "SELECT * FROM towns"
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"query": "SELECT 1"})
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"secretName": "x"})


def test_reader_connector_ops_appear_in_catalog():
    catalog = ops_catalog()
    assert catalog["reader.connector.rest"]["kind"] == "reader"
    assert "baseUrl" in catalog["reader.connector.rest"]["paramsSchema"]["properties"]
    assert catalog["reader.connector.postgres"]["kind"] == "reader"
    assert "query" in catalog["reader.connector.postgres"]["paramsSchema"]["properties"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `test_all_seventeen_ops_are_registered` and every new
`reader_connector` test fail (`KeyError`/`ValueError: unknown op`), since
neither model nor catalog entry exists yet.

- [ ] **Step 3: Implement the two param models**

Modify `core/app/pipelines/ops/schemas.py` — add after `TransformQgisParams`
(before `OP_KINDS`):

```python
class ReaderConnectorRestParams(BaseModel):
    """Lecture d'une ressource REST paginée (design SP-15f §2). `secretName`
    référence un secret api_key/bearer_token/basic_auth/
    oauth2_client_credentials (SP-15e) ; None = endpoint public non
    authentifié. `recordsPath` est un chemin pointé vers le tableau
    d'enregistrements dans le corps de réponse (ex. "data.items") ; None =
    le corps de réponse EST le tableau."""
    baseUrl: str = Field(..., pattern=r"^https?://")
    path: str = ""
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    recordsPath: str | None = None
    paginator: Literal["none", "page_number", "cursor", "offset"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)
    secretName: str | None = None


class ReaderConnectorPostgresParams(BaseModel):
    """Lecture d'une requête SQL libre sur un Postgres distant (design
    SP-15f §2). `secretName` référence toujours un secret postgres_dsn
    (SP-15e) — pas de notion de DSN non authentifié, contrairement à REST.
    `query` n'est validée SELECT-only qu'à l'exécution (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (design §6)."""
    secretName: str
    query: str
```

Then extend `OP_KINDS`/`OP_PARAMS`:

```python
OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "transform.buffer": "transform",
    "transform.reproject": "transform",
    "transform.intersection": "transform",
    "transform.countWithin": "transform",
    "transform.h3Aggregate": "transform",
    "transform.qgis": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
    "reader.connector.rest": "reader",
    "reader.connector.postgres": "reader",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "transform.buffer": TransformBufferParams,
    "transform.reproject": TransformReprojectParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.h3Aggregate": TransformH3AggregateParams,
    "transform.qgis": TransformQgisParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
    "reader.connector.rest": ReaderConnectorRestParams,
    "reader.connector.postgres": ReaderConnectorPostgresParams,
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass (17 ops registered, catalog exposes both new ops).

- [ ] **Step 5: Run the full pipelines test suite to confirm no regression**

Run: `cd core && uv run pytest tests/test_pipeline_*.py tests/test_mcp_tools_pipeline.py -v`
Expected: all pass — pure catalog addition, no behavior change to existing ops.

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): pipelines — reader.connector.rest/postgres op catalog entries"
```

---


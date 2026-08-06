## Task 2: Op catalogue — `transform.qgis` param model

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Consumes: `QGIS_ALGORITHMS` (Task 1, `app.pipelines.ops.qgis_algorithms`).
- Produces: `TransformQgisParams` (Pydantic `BaseModel` in
  `app.pipelines.ops.schemas`), registered as `OP_KINDS["transform.qgis"] =
  "transform"` and `OP_PARAMS["transform.qgis"] = TransformQgisParams`.
  Fields: `algorithmId: str`, `params: dict[str, Any]`, `outputSrid: str |
  None`. Consumed by Task 3 (`compiler.py`), Task 5 (`runtime.py`).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_pipeline_ops_schemas.py`:

```python
def test_fifteenth_op_is_registered():
    assert "transform.qgis" in OP_PARAMS
    assert "transform.qgis" in OP_KINDS
    assert OP_KINDS["transform.qgis"] == "transform"


def test_transform_qgis_accepts_allowlisted_id_with_required_params():
    params = parse_op_params(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
    )
    assert params.algorithmId == "native:centroids"
    assert params.params == {"ALL_PARTS": False}
    assert params.outputSrid is None


def test_transform_qgis_rejects_non_allowlisted_id():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:totallymadeup", "params": {}},
        )


def test_transform_qgis_rejects_missing_required_param():
    # native:centroids requires ALL_PARTS beyond INPUT/OUTPUT (design Task 2 —
    # INPUT/OUTPUT are runtime-injected, never authored, cf. spike finding
    # in test_pipeline_qgis_algorithms.py::test_centroids_required_params_...).
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis", {"algorithmId": "native:centroids", "params": {}},
        )


def test_transform_qgis_does_not_require_input_output_in_params():
    # INPUT/OUTPUT are required by native:simplifygeometries' own schema but
    # are filled in by the runtime (scratch file paths), never by the author.
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "native:simplifygeometries",
            "params": {"METHOD": 0, "TOLERANCE": 1.0},
        },
    )
    assert "INPUT" not in params.params
    assert "OUTPUT" not in params.params


def test_transform_qgis_accepts_optional_output_srid():
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {"TARGET_CRS": "EPSG:2154"},
            "outputSrid": "EPSG:2154",
        },
    )
    assert params.outputSrid == "EPSG:2154"


def test_transform_qgis_rejects_malformed_output_srid():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:dissolve",
             "params": {"SEPARATE_DISJOINT": False},
             "outputSrid": "not-a-crs"},
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -k transform_qgis -v`
Expected: FAIL — `KeyError`/`AttributeError`, `transform.qgis` not in
`OP_PARAMS` (doesn't exist yet).

- [ ] **Step 3: Add the `Any` import and `TransformQgisParams`**

Modify `core/app/pipelines/ops/schemas.py` — change the top import:

```python
from typing import Any, Literal
```

Add after `WriterDatasetParams` (before the `OP_KINDS` dict):

```python
class TransformQgisParams(BaseModel):
    """Op générique pour tout algorithme QGIS Processing de l'allowlist
    gelée (app.pipelines.ops.qgis_algorithms.QGIS_ALGORITHMS, design SP-15d
    §5/§10). `params` ne doit JAMAIS contenir INPUT/OUTPUT — le runtime les
    injecte (chemins scratch, design §6). `outputSrid` doit être renseigné
    explicitement quand l'algorithme change le CRS (ex. gdal:warpreproject
    via son propre param TARGET_CRS) ; laissé à None, le SRID de sortie est
    supposé identique à l'entrée — vrai pour la quasi-totalité des 50 op de
    l'allowlist, faux pour un algorithme de reprojection. Aucune conversion
    automatique d'unité : un DISTANCE/TOLERANCE d'un algorithme QGIS est
    dans les unités du CRS natif de la couche d'entrée, jamais auto-converti
    en mètres (vérifié empiriquement en design, §2)."""
    algorithmId: str
    params: dict[str, Any] = Field(default_factory=dict)
    outputSrid: str | None = Field(default=None, pattern=r"^[A-Za-z]+:\d+$")

    @model_validator(mode="after")
    def _check_allowlisted_and_required_params(self) -> "TransformQgisParams":
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

        schema = QGIS_ALGORITHMS.get(self.algorithmId)
        if schema is None:
            raise ValueError(f"algorithme non autorisé : {self.algorithmId}")
        required = {
            name for name, p in schema["parameters"].items() if not p["optional"]
        } - {"INPUT", "OUTPUT"}
        missing = required - self.params.keys()
        if missing:
            raise ValueError(
                f"{self.algorithmId} : paramètres requis manquants {sorted(missing)}"
            )
        return self
```

Add to `OP_KINDS`:

```python
    "transform.qgis": "transform",
```

Add to `OP_PARAMS`:

```python
    "transform.qgis": TransformQgisParams,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass, including the pre-existing 14-op tests (no regression —
`test_all_fourteen_ops_are_registered` from SP-15c will need updating to
15; do that now too):

Modify the existing `test_all_fourteen_ops_are_registered` (or whatever it's
now named) in `core/tests/test_pipeline_ops_schemas.py` to add
`"transform.qgis"` to the expected set and rename to
`test_all_fifteen_ops_are_registered`.

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): transform.qgis op — generic QGIS Processing param model"
```

---


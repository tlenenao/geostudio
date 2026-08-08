### Task 2: `AlertRule` payload schema

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_alert_config_schema.py`

**Interfaces:**
- Consumes: `app.configs.alert_condition.validate_condition_expr` (Task 1), `PipelineRefreshPolicy` (existing, reused verbatim), `AggregateRequestBody` (existing, `app.analytics.aggregate`).
- Produces: `AlertCondition`, `AlertChannelWebhook`, `AlertChannelEmail`, `AlertRulePayload` classes; `BuilderConfig.kind` gains `"alert"`; `BuilderConfig.alert: AlertRulePayload | None` field. Consumed by Task 3 (`alert_validation.py`) and Task 9 (`app.alerts.jobs`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_config_schema.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _base_alert(**overrides):
    body = {
        "kind": "alert",
        "alert": {
            "datasetItemId": "ds-1",
            "query": {"agg": "count"},
            "condition": {"expr": "value > 100"},
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }
    body["alert"].update(overrides)
    return body


def test_alert_config_requires_alert_payload():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"kind": "alert"})


def test_alert_config_accepts_a_valid_payload():
    config = BuilderConfig.model_validate(_base_alert())
    assert config.alert.datasetItemId == "ds-1"
    assert config.alert.condition.expr == "value > 100"


def test_alert_condition_rejects_an_invalid_expression():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_base_alert(condition={"expr": "value >"}))


def test_alert_condition_rejects_a_table_reference():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(
            _base_alert(condition={"expr": "(SELECT count(*) FROM some_table)"})
        )


def test_alert_requires_at_least_one_channel():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_base_alert(channels=[]))


def test_alert_query_rejects_groupby():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_base_alert(query={"groupBy": "region", "agg": "count"}))


def test_alert_query_rejects_more_than_one_measure():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_base_alert(query={
            "measures": [{"field": "a", "agg": "count", "label": "x"}, {"field": "b", "agg": "sum", "label": "y"}],
        }))


def test_alert_refresh_policy_rejects_invalid_cron():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_base_alert(refreshPolicy={"enabled": True, "cron": "not-a-cron"}))


def test_alert_email_channel_requires_smtp_secret_name():
    config = BuilderConfig.model_validate(
        _base_alert(channels=[{"kind": "email", "to": "ops@example.test", "smtpSecretName": "smtp-main"}])
    )
    assert config.alert.channels[0].smtpSecretName == "smtp-main"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_config_schema.py`
Expected: FAIL — `pydantic_core._pydantic_core.ValidationError` on `kind="alert"` not being a recognized literal (or `AttributeError` on `config.alert`), since nothing has been added yet.

- [ ] **Step 3: Write the implementation**

Add to `core/app/configs/schemas.py`, near `PipelineRefreshPolicy`/`PipelinePayload` (the file already imports `AggregateRequestBody`? confirm — it does not yet; add the import alongside the existing ones at the top of the file):

```python
# Add to the top-level import block in core/app/configs/schemas.py:
from app.analytics.aggregate import AggregateRequestBody
from app.configs.alert_condition import validate_condition_expr
```

```python
# Add near PipelinePayload in core/app/configs/schemas.py:
class AlertCondition(BaseModel):
    # Bounded DuckDB scalar SQL expression, binding `value` — see
    # app.configs.alert_condition (design SP-16b §4: no CEL engine exists
    # server-side, only client-side cel-js for visibleWhen/computed
    # columns).
    expr: str

    @model_validator(mode="after")
    def _require_valid_expr(self) -> "AlertCondition":
        import duckdb

        conn = duckdb.connect(":memory:")
        try:
            validate_condition_expr(conn, self.expr)
        except Exception as exc:
            raise ValueError(f"invalid condition expression: {exc}") from exc
        finally:
            conn.close()
        return self


class AlertChannelWebhook(BaseModel):
    kind: Literal["webhook"] = "webhook"
    url: str


class AlertChannelEmail(BaseModel):
    kind: Literal["email"] = "email"
    to: str
    smtpSecretName: str


class AlertRulePayload(BaseModel):
    datasetItemId: str
    query: AggregateRequestBody
    condition: AlertCondition
    refreshPolicy: PipelineRefreshPolicy
    channels: list[AlertChannelWebhook | AlertChannelEmail] = Field(default_factory=list)
    messageTemplate: str = "Alert {ruleName}: value={value} ({state})"

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "AlertRulePayload":
        if not self.channels:
            raise ValueError("alert rule requires at least one channel")
        return self

    @model_validator(mode="after")
    def _require_single_scalar_query(self) -> "AlertRulePayload":
        # v1 scope (design SP-16b §1 non-buts, §2): one scalar per rule, no
        # per-group/multi-series alerting.
        if self.query.groupBy:
            raise ValueError("alert query must not use groupBy (v1 supports a single scalar per rule)")
        if self.query.split is not None:
            raise ValueError("alert query must not use split (v1 supports a single scalar per rule)")
        if self.query.bucket is not None or self.query.bins is not None:
            raise ValueError("alert query must not use bucket/bins (v1 supports a single scalar per rule)")
        if self.query.measures is not None and len(self.query.measures) > 1:
            raise ValueError("alert query must have at most one measure (v1 supports a single scalar per rule)")
        return self
```

Modify the `kind` literal and add the `alert` field + payload requirement on `BuilderConfig`:

```python
# Change in class BuilderConfig:
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert"]
```

```python
# Add alongside `pipeline: PipelinePayload | None = None` in class BuilderConfig:
    alert: AlertRulePayload | None = None
```

```python
# Add inside _require_kind_payload, alongside the "pipeline" check:
        if self.kind == "alert" and self.alert is None:
            raise ValueError("alert config requires an alert payload")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_config_schema.py`
Expected: `9 passed`

Then run the full config-schema suite to check for regressions on the `BuilderConfig.kind` literal change:

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_bookmark_config_schema.py tests/test_dataset_config_schema.py tests/test_pipeline_config_schema.py`
Expected: all passing, unchanged.

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_alert_config_schema.py
git commit -m "feat(core): SP-16b — AlertRule payload schema (BuilderConfig kind=\"alert\")"
```

---


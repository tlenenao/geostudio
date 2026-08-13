## Task 1: `ReportSchedulePayload` schema + `BuilderConfig` kind registration

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_report_config_schema.py`

**Interfaces:**
- Produces: `ReportSchedulePayload(bookmarkItemId: str, refreshPolicy: PipelineRefreshPolicy, channels: list[AlertChannel])`, consumed by every later core task.
- Produces: `BuilderConfig.kind` now accepts `"report"`, and `BuilderConfig.report: ReportSchedulePayload | None`.

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_config_schema.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig, ReportSchedulePayload


def _payload(**overrides) -> dict:
    base = {
        "bookmarkItemId": "bookmark-1",
        "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
        "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
    }
    base.update(overrides)
    return base


def test_report_schedule_payload_round_trips():
    payload = ReportSchedulePayload.model_validate(_payload())
    assert payload.bookmarkItemId == "bookmark-1"
    assert payload.refreshPolicy.cron == "0 8 * * MON"
    assert payload.channels[0].kind == "webhook"


def test_report_schedule_payload_requires_at_least_one_channel():
    with pytest.raises(ValidationError, match="at least one channel"):
        ReportSchedulePayload.model_validate(_payload(channels=[]))


def test_report_schedule_payload_rejects_invalid_cron():
    with pytest.raises(ValidationError):
        ReportSchedulePayload.model_validate(_payload(refreshPolicy={"enabled": True, "cron": "not-a-cron"}))


def test_builder_config_accepts_kind_report():
    config = BuilderConfig.model_validate({"kind": "report", "report": _payload()})
    assert config.kind == "report"
    assert config.report is not None
    assert config.report.bookmarkItemId == "bookmark-1"


def test_builder_config_kind_report_requires_report_payload():
    with pytest.raises(ValidationError, match="report config requires"):
        BuilderConfig.model_validate({"kind": "report"})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_config_schema.py -v`
Expected: FAIL — `ImportError: cannot import name 'ReportSchedulePayload'`.

- [ ] **Step 3: Add `ReportSchedulePayload` and register the `"report"` kind**

In `core/app/configs/schemas.py`, immediately after the existing `AlertRulePayload` class (the one ending with its `_require_single_scalar_query` validator), add:

```python
class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    refreshPolicy: PipelineRefreshPolicy  # reused verbatim, same shape as pipeline/alert scheduling
    channels: list[AlertChannel] = Field(default_factory=list)  # reused verbatim from AlertRule (SP-16b)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self
```

Then in `BuilderConfig`, change:

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert"]
```
to:
```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert", "report"]
```

Add the field, right after `alert: AlertRulePayload | None = None`:
```python
    alert: AlertRulePayload | None = None
    report: ReportSchedulePayload | None = None
```

And in `_require_kind_payload`, right after the `"alert"` branch:
```python
        if self.kind == "alert" and self.alert is None:
            raise ValueError("alert config requires an alert payload")
        if self.kind == "report" and self.report is None:
            raise ValueError("report config requires a report payload")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_config_schema.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/configs/schemas.py core/tests/test_report_config_schema.py
git commit -m "feat(core): ReportSchedulePayload schema, 9th BuilderConfig kind (SP-17b)"
```

---


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
        ReportSchedulePayload.model_validate(
            _payload(refreshPolicy={"enabled": True, "cron": "not-a-cron"})
        )


def test_builder_config_accepts_kind_report():
    config = BuilderConfig.model_validate({"kind": "report", "report": _payload()})
    assert config.kind == "report"
    assert config.report is not None
    assert config.report.bookmarkItemId == "bookmark-1"


def test_builder_config_kind_report_requires_report_payload():
    with pytest.raises(ValidationError, match="report config requires"):
        BuilderConfig.model_validate({"kind": "report"})

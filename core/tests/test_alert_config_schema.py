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

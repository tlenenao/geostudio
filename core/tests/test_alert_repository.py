# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta

from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _alert_body(dataset_item_id: str, *, refresh_policy=None) -> dict:
    body = {
        "kind": "alert",
        "alert": {
            "datasetItemId": dataset_item_id,
            "query": {"agg": "count"},
            "condition": {"expr": "value > 100"},
            "refreshPolicy": refresh_policy or {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }
    return body


def _seed_alert_rule(session, *, tenant_id, owner_id, dataset_item_id="ds-1", refresh_policy=None):
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="alert",
        title="Rule",
    )
    config = BuilderConfig.model_validate(
        _alert_body(dataset_item_id, refresh_policy=refresh_policy)
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_create_and_mark_evaluated_round_trip():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_id
        )
        assert evaluation.state == "pending"
        alerts_repo.mark_evaluated(
            s,
            evaluation_id=evaluation.id,
            value=150.0,
            state="firing",
            transitioned=True,
        )
        s.commit()

        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_id
        )
        assert latest is not None
        assert latest.state == "firing"
        assert latest.value == 150.0


def test_list_due_rules_includes_a_rule_with_no_prior_evaluation():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

        due = alerts_repo.list_due_rules(s)
        assert (rule_id, tenant.id) in due


def test_list_due_rules_excludes_a_disabled_rule():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        _seed_alert_rule(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            refresh_policy={"enabled": False, "cron": "*/5 * * * *"},
        )
        s.commit()

        assert alerts_repo.list_due_rules(s) == []


def test_list_due_rules_excludes_a_rule_evaluated_within_its_cron_interval():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_id
        )
        alerts_repo.mark_evaluated(
            s, evaluation_id=evaluation.id, value=1.0, state="ok", transitioned=False
        )
        s.commit()

        assert alerts_repo.list_due_rules(s) == []


def test_list_due_rules_reclaims_a_stuck_pending_evaluation():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_id
        )
        # Simulate a stuck evaluation: created long ago, never marked.
        evaluation.created_at = datetime.now(UTC) - timedelta(minutes=120)
        s.commit()

        assert (rule_id, tenant.id) in alerts_repo.list_due_rules(s)


def test_list_evaluations_orders_most_recent_first():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        rule_id = _seed_alert_rule(s, tenant_id=tenant.id, owner_id=user.id)
        first = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(
            s, evaluation_id=first.id, value=1.0, state="ok", transitioned=False
        )
        second = alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        alerts_repo.mark_evaluated(
            s, evaluation_id=second.id, value=2.0, state="firing", transitioned=True
        )
        s.commit()

        rows = alerts_repo.list_evaluations(s, tenant_id=tenant.id, alert_rule_item_id=rule_id)
        assert [r.id for r in rows] == [second.id, first.id]

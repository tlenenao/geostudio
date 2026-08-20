# SPDX-License-Identifier: Apache-2.0
from app.alerts.models import AlertEvaluation
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_alert_evaluation_round_trips_through_sqlite():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="High counts",
        )
        s.commit()

        evaluation = AlertEvaluation(
            id="eval-1",
            tenant_id=tenant.id,
            alert_rule_item_id=item.id,
            value=150.0,
            state="firing",
            transitioned=True,
            error=None,
        )
        s.add(evaluation)
        s.commit()

    with Session() as s:
        reloaded = s.get(AlertEvaluation, "eval-1")
        assert reloaded is not None
        assert reloaded.state == "firing"
        assert reloaded.transitioned is True
        assert reloaded.value == 150.0
        assert reloaded.error is None
        assert reloaded.created_at is not None

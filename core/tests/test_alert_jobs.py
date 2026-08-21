# SPDX-License-Identifier: Apache-2.0
"""evaluate_alert_task (SP-16b) against real Postgres+DuckDB — mirrors
test_pipeline_jobs.py's postgis-marked fixture exactly (real collection
table, real CDC GeoParquet partition on local disk via
S3_CDC_BUCKET_BASE_URI)."""

import geopandas as gpd
import pytest
from procrastinate import testing
from shapely.geometry import Point
from sqlalchemy import select, text

from app.alerts import jobs as alert_jobs
from app.alerts import repository as alerts_repo
from app.audit.models import AuditLog
from app.collections.ddl import apply_collection_ddl
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import Base, make_session_factory
from app.items import repository as items_repo  # noqa: F401 -- registers Item on Base.metadata
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-07"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _alert_body(dataset_item_id, *, expr="value > 2", query=None):
    return {
        "kind": "alert",
        "alert": {
            "datasetItemId": dataset_item_id,
            "query": query or {"agg": "count"},
            "condition": {"expr": expr},
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
        },
    }


@pytest.fixture()
def env(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
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
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, description, "
                "pk_column, geometry_column, is_public, editable, created_at, updated_at) "
                "VALUES ('incidents', :t, :o, 'incidents', 'Incidents', '', 'id', "
                "'geometry', false, true, "
                "now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE incidents (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "category VARCHAR, geometry geometry(Point, 4326))"
            )
        )
        apply_collection_ddl(s, "incidents")

        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Incidents dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant.id)

        alert_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="Trop d'incidents",
        )
        alert_config = BuilderConfig.model_validate(_alert_body(dataset_item.id))
        configs_repo.create_config(s, alert_config, item_id=alert_item.id, tenant_id=tenant.id)
        s.commit()
        alert_item_id = alert_item.id

    _write_partition(
        tmp_path,
        tenant_id=tenant.id,
        collection_id="incidents",
        rows=[
            {
                "id": 1,
                "category": "a",
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1.0, 45.0),
            },
            {
                "id": 2,
                "category": "b",
                "_op": "insert",
                "_lsn": 2,
                "_ts": 1.0,
                "geometry": Point(1.1, 45.1),
            },
            {
                "id": 3,
                "category": "c",
                "_op": "insert",
                "_lsn": 3,
                "_ts": 1.0,
                "geometry": Point(1.2, 45.2),
            },
        ],
    )
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    monkeypatch.setenv("S3_CDC_BUCKET_BASE_URI", str(tmp_path))

    in_memory = testing.InMemoryConnector()
    with alert_jobs.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, alert_item_id
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "DROP TABLE incidents; "
                "TRUNCATE alert_evaluations, items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_evaluate_alert_task_transitions_ok_to_firing_and_notifies(env, monkeypatch):
    app, Session, tenant, alert_item_id = env
    sent = []
    monkeypatch.setattr(alert_jobs, "send_webhook", lambda channel, payload: sent.append(payload))

    with Session() as s:
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        s.commit()
        evaluation_id = evaluation.id

    alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert latest.state == "firing"  # count=3 > 2
        assert latest.value == 3.0
        assert latest.transitioned is True
    assert len(sent) == 1
    assert sent[0]["state"] == "firing"


def test_evaluate_alert_task_does_not_renotify_while_state_is_stable(env, monkeypatch):
    _, Session, tenant, alert_item_id = env
    sent = []
    monkeypatch.setattr(alert_jobs, "send_webhook", lambda channel, payload: sent.append(payload))

    for _ in range(2):
        with Session() as s:
            evaluation = alerts_repo.create_evaluation(
                s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
            )
            s.commit()
            evaluation_id = evaluation.id
        # A fresh InMemoryConnector per iteration, not the one shared by the
        # `env` fixture: InMemoryConnector.run_worker() opens a fresh asyncio
        # event loop (asyncio.run) and closes it at the end of that call —
        # the connector's `_loop` reference (used by a later `.defer()`'s
        # notify) then points at a CLOSED loop, so reusing the same
        # connector for a second defer+run_worker cycle raises "RuntimeError:
        # Event loop is closed". No other test in this suite loops
        # defer+run_worker on one connector (confirmed by inspection of
        # test_pipeline_jobs.py/test_harvest_jobs.py/etc — each calls it
        # once per fixture-provided connector); replacing the connector
        # again here for each cycle sidesteps the staleness instead of
        # relying on that never-before-exercised reuse.
        with alert_jobs.app.replace_connector(testing.InMemoryConnector()) as app:
            alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
            app.run_worker(wait=False, queues=["etl"])

    # Two evaluations, both "firing" (count=3 > 2 both times): only the
    # FIRST should have notified — the second is a stable repeat.
    assert len(sent) == 1
    with Session() as s:
        rows = alerts_repo.list_evaluations(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert [r.transitioned for r in rows] == [False, True]  # most-recent first


def test_evaluate_alert_task_marks_error_on_arcgis_sourced_dataset(
    pg_engine, monkeypatch, tmp_path
):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
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
        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Arcgis dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "arcgis", "arcgisItemId": "external-1", "columns": {}},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant.id)
        alert_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="Arcgis alert",
        )
        alert_config = BuilderConfig.model_validate(_alert_body(dataset_item.id))
        configs_repo.create_config(s, alert_config, item_id=alert_item.id, tenant_id=tenant.id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item.id
        )
        s.commit()
        alert_item_id, evaluation_id = alert_item.id, evaluation.id

    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    monkeypatch.setenv("S3_CDC_BUCKET_BASE_URI", str(tmp_path))

    in_memory = testing.InMemoryConnector()
    with alert_jobs.app.replace_connector(in_memory) as app:
        alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
        app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert latest.state == "error"
        assert "collection-sourced" in latest.error

    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE alert_evaluations, items, configs, config_revisions, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_evaluate_alert_task_evaluates_a_measures_declared_rule_without_explicit_label(
    pg_engine, monkeypatch, tmp_path
):
    # Regression (final-review Finding 1): a rule saved with `query:
    # {"measures": [{"agg": "count"}]}` (schema-legal, no explicit label)
    # used to compute label=None in _measure_value while aggregate.py's own
    # row-keying (_measures_for + _measure_label) keys the row "count" —
    # "None not in row" was always true, so this shape could never evaluate.
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
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
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, description, "
                "pk_column, geometry_column, is_public, editable, created_at, updated_at) "
                "VALUES ('incidents', :t, :o, 'incidents', 'Incidents', '', 'id', "
                "'geometry', false, true, "
                "now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE incidents (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "category VARCHAR, geometry geometry(Point, 4326))"
            )
        )
        apply_collection_ddl(s, "incidents")

        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Incidents dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant.id)

        alert_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="Measures alert",
        )
        alert_config = BuilderConfig.model_validate(
            _alert_body(dataset_item.id, query={"measures": [{"agg": "count"}]})
        )
        configs_repo.create_config(s, alert_config, item_id=alert_item.id, tenant_id=tenant.id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item.id
        )
        s.commit()
        alert_item_id, evaluation_id = alert_item.id, evaluation.id

    _write_partition(
        tmp_path,
        tenant_id=tenant.id,
        collection_id="incidents",
        rows=[
            {
                "id": 1,
                "category": "a",
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1.0, 45.0),
            },
            {
                "id": 2,
                "category": "b",
                "_op": "insert",
                "_lsn": 2,
                "_ts": 1.0,
                "geometry": Point(1.1, 45.1),
            },
            {
                "id": 3,
                "category": "c",
                "_op": "insert",
                "_lsn": 3,
                "_ts": 1.0,
                "geometry": Point(1.2, 45.2),
            },
        ],
    )
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    monkeypatch.setenv("S3_CDC_BUCKET_BASE_URI", str(tmp_path))

    in_memory = testing.InMemoryConnector()
    with alert_jobs.app.replace_connector(in_memory) as app:
        alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
        app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert latest.state == "firing"  # count=3 > 2
        assert latest.value == 3.0
        assert latest.error is None

    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "DROP TABLE incidents; "
                "TRUNCATE alert_evaluations, items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_notify_failure_does_not_overwrite_measured_state_or_cause_renotify(env, monkeypatch):
    # Regression (final-review Finding 2): a non-NotifyError exception
    # escaping the notification step (e.g. .format() on a malformed
    # template, or a decryption error) used to propagate to the task's
    # outer generic `except Exception`, which called mark_evaluated(...,
    # state="error") a SECOND time — overwriting the just-recorded real
    # "firing" state. Next tick then saw "error" as the previous state,
    # treated "firing" as a fresh transition, and re-notified every
    # channel indefinitely (including ones that already succeeded).
    app, Session, tenant, alert_item_id = env
    monkeypatch.setattr(
        alert_jobs,
        "send_webhook",
        lambda channel, payload: (_ for _ in ()).throw(ValueError("boom, not a NotifyError")),
    )

    with Session() as s:
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        s.commit()
        evaluation_id = evaluation.id

    alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        # The real measured state must survive the notification failure.
        assert latest.state == "firing"  # count=3 > 2
        assert latest.value == 3.0
        assert latest.transitioned is True

        notify_rows = s.scalars(
            select(AuditLog).where(
                AuditLog.action == "alert.notify", AuditLog.object_id == alert_item_id
            )
        ).all()
        assert len(notify_rows) == 1
        assert notify_rows[0].payload["success"] is False

    # Second tick: state is still "firing" (webhook keeps failing the same
    # way) — this must NOT be treated as a fresh transition, i.e. no second
    # notification attempt, because the previous state was correctly
    # recorded as "firing" and not corrupted to "error".
    with Session() as s:
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        s.commit()
        evaluation_id = evaluation.id

    with alert_jobs.app.replace_connector(testing.InMemoryConnector()) as app2:
        alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
        app2.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert latest.state == "firing"
        assert latest.transitioned is False  # stable repeat, no re-notify attempt

        notify_rows = s.scalars(
            select(AuditLog).where(
                AuditLog.action == "alert.notify", AuditLog.object_id == alert_item_id
            )
        ).all()
        assert len(notify_rows) == 1  # unchanged — no second attempt was made


def test_evaluate_alert_task_writes_audit_log_on_unexpected_error(env, monkeypatch):
    # Regression (final-review Finding 3): the generic `except Exception`
    # branch changed evaluation.state to "error" but never wrote an
    # audit_log entry, unlike its AlertEvaluationError sibling — silently
    # dropping the audit trail for the most likely real production failures
    # (SqlSandboxError timeout, DuckDB IOException, missing S3_* env var...).
    app, Session, tenant, alert_item_id = env
    monkeypatch.setattr(
        alert_jobs,
        "_measure_value",
        lambda session, *, user, payload: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with Session() as s:
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        s.commit()
        evaluation_id = evaluation.id

    alert_jobs.evaluate_alert_task.defer(evaluation_id=evaluation_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        latest = alerts_repo.get_latest_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=alert_item_id
        )
        assert latest.state == "error"
        assert "boom" in latest.error

        rows = s.scalars(
            select(AuditLog).where(
                AuditLog.action == "alert.evaluate", AuditLog.object_id == alert_item_id
            )
        ).all()
        assert len(rows) == 1
        assert "boom" in rows[0].payload["error"]

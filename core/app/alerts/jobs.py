# SPDX-License-Identifier: Apache-2.0
"""Procrastinate tasks for AlertRule (design SP-16b §3) — mirrors
app.pipelines.jobs (SP-15a/h) exactly: a periodic sweep defers a per-rule
evaluation task, "pending" evaluations are created and committed BEFORE
deferring (same reason as run_pipeline_sweep_task: a worker could otherwise
pick up the task before the row is visible). v1 evaluates collection-sourced
datasets only — an arcgis-sourced dataset fails cleanly with an
AlertEvaluationError rather than being silently mis-evaluated (Global
Constraints)."""

import logging
import os

from sqlalchemy import select

from app.alerts import repository as alerts_repo
from app.alerts.notify import NotifyError, send_email, send_webhook
from app.analytics.aggregate import _measure_label, _measures_for, run_collection_aggregate
from app.analytics.duckdb_conn import open_connection
from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.configs import repository as configs_repo
from app.configs.alert_condition import evaluate_condition
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook, AlertRulePayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.items.models import Item
from app.jobs import app
from app.sharing.authorization import can
from app.users.models import User

logger = logging.getLogger(__name__)


class AlertEvaluationError(Exception):
    """Anything that keeps this evaluation from producing a value — always
    caught, always turns into an `error` evaluation row, never a crash."""


_TERMINAL_STATES = {"ok", "firing", "error"}


def _previous_terminal_state(evaluations, *, current_evaluation_id: str) -> str | None:
    """Walk `evaluations` (most-recent-first, per list_evaluations) past the
    current evaluation AND any other leading "pending" rows, returning the
    first terminal-state (ok/firing/error) row's state.

    Two distinct evaluations can legitimately be "pending" at once: the
    current one being processed right now (committed before deferring, see
    sweep_alert_rules_task), and — when a worker crashed or was restarted
    mid-evaluation — an older one that list_due_rules reclaimed after
    _PENDING_RECLAIM_MINUTES and superseded with a fresh row. Both must be
    skipped; only a real terminal state counts as "the previous state",
    otherwise a reclaim spuriously looks like a transition out of "pending"
    even when the rule's actual state never changed.

    Returns None if the rule has no prior terminal evaluation at all (first
    real run) — the caller treats that the same as any other transition.
    """
    for evaluation in evaluations:
        if evaluation.id == current_evaluation_id:
            continue
        if evaluation.state not in _TERMINAL_STATES:
            continue
        return evaluation.state
    return None


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _analytics_base_uri() -> str:
    # Mirrors app.pipelines.jobs._analytics_base_uri exactly (same env var,
    # same fallback) — S3_CDC_BUCKET_BASE_URI is the test seam that points
    # run_collection_aggregate at local-disk GeoParquet fixtures instead of
    # a real S3/MinIO endpoint (see test_alert_jobs.py's `env` fixture).
    override = os.environ.get("S3_CDC_BUCKET_BASE_URI")  # test seam, local-disk fixtures
    if override:
        return override
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    return f"s3://{bucket}/cdc"


def _get_alert_payload(session, *, item_id: str) -> AlertRulePayload:
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "alert":
        raise AlertEvaluationError(f"alert rule '{item_id}' not found")
    payload = config.config.alert
    assert payload is not None
    return payload


def _owner_user(session, *, tenant_id: str, item_id: str) -> User:
    # Same double-verification pattern as app.pipelines.jobs._acting_user:
    # evaluation runs with the RULE OWNER's permissions, re-checked at
    # evaluation time, never an implicit admin bypass.
    owner_id = session.execute(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if owner_id is None:
        raise AlertEvaluationError(f"alert rule '{item_id}' not found")
    user = session.get(User, owner_id)
    assert user is not None
    return user


def _measure_value(session, *, user: User, payload: AlertRulePayload) -> float:
    dataset_config = configs_repo.get_config_by_item(session, payload.datasetItemId)
    if dataset_config is None or dataset_config.config.kind != "dataset":
        raise AlertEvaluationError(f"dataset '{payload.datasetItemId}' not found")
    dataset = dataset_config.config.dataset
    assert dataset is not None

    if dataset.source != "collection":
        raise AlertEvaluationError(
            f"alert evaluation only supports collection-sourced datasets (got '{dataset.source}')"
        )

    facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=payload.datasetItemId
    )
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise AlertEvaluationError(f"dataset '{payload.datasetItemId}' not readable by rule owner")

    collection_id = dataset.collectionId
    assert collection_id is not None
    col = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id
    )
    if col is None:
        raise AlertEvaluationError(f"collection '{collection_id}' not found")
    table_info = introspect_table(session, col.table_name)

    conn = open_connection(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    try:
        category_key, rows = run_collection_aggregate(
            conn,
            base_uri=_analytics_base_uri(),
            tenant_id=col.tenant_id,
            collection_id=col.id,
            table_info=table_info,
            request=payload.query,
        )
    finally:
        conn.close()

    if len(rows) != 1:
        raise AlertEvaluationError(
            f"alert query must reduce to exactly one row (got {len(rows)}) — "
            "this should be impossible given AlertRulePayload's single-scalar validation"
        )
    # Must match aggregate.py's own row-keying exactly (_measures_for +
    # _measure_label): a rule saved with `measures: [{"agg": "sum", "field":
    # "amount"}]` (no explicit label) rows out keyed "sum_amount", not
    # "value" — reusing the real helpers (rather than re-deriving the label
    # here) is what keeps the two in agreement regardless of which
    # schema-legal query shape (top-level agg/field vs. a one-element
    # measures list, labelled or not) was used.
    label = _measure_label(_measures_for(payload.query)[0])
    row = rows[0]
    if label not in row:
        raise AlertEvaluationError(f"expected measure '{label}' not present in aggregate result")
    return float(row[label])


def _render_message(payload: AlertRulePayload, *, rule_name: str, value: float, state: str) -> str:
    # Keyword shape (ruleName/value/state/datasetName) must stay in sync
    # with AlertRulePayload._require_valid_message_template's save-time
    # `.format(...)` probe in app.configs.schemas — that validator can't
    # import this function (app.configs sits below app.alerts in the
    # layers contract), so it re-derives the same call shape by hand.
    return payload.messageTemplate.format(
        ruleName=rule_name, value=value, state=state, datasetName=payload.datasetItemId
    )


def _notify(
    session,
    *,
    tenant_id: str,
    item_id: str,
    payload: AlertRulePayload,
    rule_name: str,
    value: float,
    state: str,
) -> None:
    message = _render_message(payload, rule_name=rule_name, value=value, state=state)
    for channel in payload.channels:
        success = False
        error_detail = None
        try:
            if isinstance(channel, AlertChannelWebhook):
                send_webhook(
                    channel,
                    payload={
                        "ruleName": rule_name,
                        "state": state,
                        "value": value,
                        "message": message,
                    },
                )
            elif isinstance(channel, AlertChannelEmail):
                send_email(
                    session,
                    tenant_id=tenant_id,
                    channel=channel,
                    subject=f"[GeoStudio] {rule_name}: {state}",
                    body=message,
                )
            success = True
        except NotifyError as exc:
            error_detail = str(exc)
            logger.warning("alert notification failed for rule %s: %s", item_id, exc)
        write_audit(
            session,
            tenant_id=tenant_id,
            actor_id=None,
            actor_kind="agent",
            action="alert.notify",
            object_type="item",
            object_id=item_id,
            payload={
                "channel": channel.kind,
                "state": state,
                "success": success,
                "error": error_detail,
            },
        )


@app.task(queue="etl")
def evaluate_alert_task(evaluation_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    with request_scoped_session(session_factory) as session:
        evaluation = alerts_repo.get_evaluation(
            session, tenant_id=tenant_id, evaluation_id=evaluation_id
        )
        if evaluation is None:
            logger.error("alert evaluation %s introuvable (tenant %s)", evaluation_id, tenant_id)
            return
        item_id = evaluation.alert_rule_item_id

    with request_scoped_session(session_factory) as session:
        try:
            payload = _get_alert_payload(session, item_id=item_id)
            user = _owner_user(session, tenant_id=tenant_id, item_id=item_id)
            value = _measure_value(session, user=user, payload=payload)

            conn = open_connection(
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"],
                secret_key=os.environ["S3_SECRET_KEY"],
            )
            try:
                condition_holds = evaluate_condition(conn, payload.condition.expr, value)
            finally:
                conn.close()
            new_state = "firing" if condition_holds else "ok"

            # NOT get_latest_evaluation(...): by construction, THIS evaluation
            # (still "pending" in the DB at this point, see get_evaluation
            # above) is always the most recently created row for this rule —
            # get_latest_evaluation would return it right back, and excluding
            # it by id would just null the result out every single time,
            # never actually reaching the real previous evaluation behind it.
            # list_evaluations (already ordered most-recent-first) lets us
            # walk past self AND any other leading "pending" rows (a worker
            # crash/restart can leave a stuck pending evaluation that
            # list_due_rules later reclaims and supersedes — see
            # _previous_terminal_state) instead of relying on ordering alone.
            history = alerts_repo.list_evaluations(
                session, tenant_id=tenant_id, alert_rule_item_id=item_id
            )
            previous_state = _previous_terminal_state(history, current_evaluation_id=evaluation_id)
            # A rule with no prior real (terminal) evaluation always counts
            # as a transition into its first observed state — same "first
            # run notifies" semantics as any freshly-created alert.
            transitioned = previous_state is None or previous_state != new_state

            alerts_repo.mark_evaluated(
                session,
                evaluation_id=evaluation_id,
                value=value,
                state=new_state,
                transitioned=transitioned,
            )
            write_audit(
                session,
                tenant_id=tenant_id,
                actor_id=None,
                actor_kind="agent",
                action="alert.evaluate",
                object_type="item",
                object_id=item_id,
                payload={"value": value, "state": new_state, "transitioned": transitioned},
            )
        except AlertEvaluationError as exc:
            alerts_repo.mark_evaluated(
                session,
                evaluation_id=evaluation_id,
                value=None,
                state="error",
                transitioned=False,
                error=str(exc),
            )
            write_audit(
                session,
                tenant_id=tenant_id,
                actor_id=None,
                actor_kind="agent",
                action="alert.evaluate",
                object_type="item",
                object_id=item_id,
                payload={"error": str(exc)},
            )
            return
        except Exception as exc:  # toute erreur inattendue finit "error", jamais un run zombie
            logger.exception("alert evaluation %s : erreur inattendue", evaluation_id)
            error_detail = f"erreur interne : {exc}"
            alerts_repo.mark_evaluated(
                session,
                evaluation_id=evaluation_id,
                value=None,
                state="error",
                transitioned=False,
                error=error_detail,
            )
            # Sibling of the AlertEvaluationError branch above: an
            # unexpected error (SqlSandboxError statement timeout, a DuckDB
            # IOException on a collection with no CDC data yet, a KeyError
            # from a missing S3_* env var, ...) is still a real evaluation
            # transition to "error" and must be audited exactly like the
            # "expected" error path is — this was previously missing here.
            write_audit(
                session,
                tenant_id=tenant_id,
                actor_id=None,
                actor_kind="agent",
                action="alert.evaluate",
                object_type="item",
                object_id=item_id,
                payload={"error": error_detail},
            )
            return

        # The measured state (ok/firing/error above) is already durably
        # recorded (mark_evaluated + write_audit, still uncommitted but
        # flushed in this same transaction) BEFORE notification is even
        # attempted. Notification failures below are deliberately confined
        # to their own broad try/except and their own audit entry — they
        # must never reach mark_evaluated again for this evaluation. If they
        # did (as before this fix), an unguarded failure inside _notify or
        # _render_message (a KeyError/IndexError/ValueError from a malformed
        # messageTemplate, or a non-NotifyError exception from secret
        # decryption) would propagate to a generic handler that overwrites
        # the just-recorded real ok/firing state with "error" — making the
        # NEXT tick see "error" as the previous state, re-derive
        # transitioned=True, and re-notify every channel indefinitely,
        # including ones that already succeeded.
        if transitioned:
            item = items_repo.get_item(session, tenant_id=tenant_id, item_id=item_id)
            rule_name = item.title if item else item_id
            try:
                _notify(
                    session,
                    tenant_id=tenant_id,
                    item_id=item_id,
                    payload=payload,
                    rule_name=rule_name,
                    value=value,
                    state=new_state,
                )
            except Exception as exc:
                # _notify itself already catches NotifyError per-channel and
                # audits per-channel; this is the backstop for anything else
                # (e.g. _render_message's `.format()` on a malformed
                # template — save-time validation in
                # AlertRulePayload._require_valid_message_template makes this
                # unreachable for new rules, but pre-existing rules saved
                # before that validator existed are still possible).
                logger.exception(
                    "alert notification pipeline %s : erreur inattendue", evaluation_id
                )
                write_audit(
                    session,
                    tenant_id=tenant_id,
                    actor_id=None,
                    actor_kind="agent",
                    action="alert.notify",
                    object_type="item",
                    object_id=item_id,
                    payload={
                        "channel": None,
                        "state": new_state,
                        "success": False,
                        "error": f"erreur interne : {exc}",
                    },
                )


@app.periodic(cron="*/5 * * * *")
@app.task(queue="etl")
def sweep_alert_rules_task(timestamp: int) -> None:
    if is_read_only_mode():
        logger.info("mode lecture seule : balayage d'alertes ignoré")
        return
    session_factory = _session_factory()
    with request_scoped_session(session_factory) as session:
        due = alerts_repo.list_due_rules(session)
        for item_id, tenant_id in due:
            evaluation = alerts_repo.create_evaluation(
                session, tenant_id=tenant_id, alert_rule_item_id=item_id
            )
            # Commit avant de déférer — même raison que run_pipeline_sweep_task.
            session.commit()
            evaluate_alert_task.defer(evaluation_id=evaluation.id, tenant_id=tenant_id)

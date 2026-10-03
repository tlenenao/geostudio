# SPDX-License-Identifier: Apache-2.0
"""AlertRule listing + evaluation history (design SP-16b §6). Create/
update/delete of the rule itself are handled entirely by the generic
/configs routes (app.configs.routes) — nothing bespoke needed there."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.alerts import repository as alerts_repo
from app.alerts.service import evaluate_alert_now_service
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_EVALUATIONS_MAX_LIMIT = 1000


class AlertRuleSummary(BaseModel):
    itemId: str
    title: str


class EvaluationStatus(BaseModel):
    id: str
    value: float | None
    state: str
    transitioned: bool
    error: str | None
    notifyStatus: str | None = None  # P20.01 : None | "delivered" | "failed"
    notifyError: str | None = None
    createdAt: str


@router.get("/datasets/{item_id}/alerts", response_model=list[AlertRuleSummary])
def list_alerts_for_dataset(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[AlertRuleSummary]:
    results: list[AlertRuleSummary] = []
    # Tenant-scoped at the SQL level (app.configs.repository.
    # list_configs_by_kind_and_tenant) — never the cross-tenant
    # list_configs_by_kind, which is reserved for system sweeps and must
    # never be reached from a route.
    for rule_item_id, config in configs_repo.list_configs_by_kind_and_tenant(
        session, kind="alert", tenant_id=user.tenant_id
    ):
        payload = config.alert
        if payload is None or payload.datasetItemId != item_id:
            continue
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=rule_item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=rule_item_id)
        if item is None:
            continue
        results.append(AlertRuleSummary(itemId=rule_item_id, title=item.title))
    return results


def _require_alert_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="alert rule not found")


class EvaluateAlertResponse(BaseModel):
    evaluationId: str
    # Revue finale Vague C (point 4c) : `False` quand une évaluation
    # "pending" récente existait déjà et a été réutilisée telle quelle
    # (aucun second job déféré) — même fenêtre de déduplication que le
    # balayage périodique (app.alerts.repository._PENDING_RECLAIM_MINUTES).
    # Champ additif : un client qui l'ignore garde le comportement d'avant.
    created: bool = True


@router.post("/alerts/{item_id}/evaluate", response_model=EvaluateAlertResponse, status_code=202)
def evaluate_alert_now(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> EvaluateAlertResponse:
    # D04 (SP-C6, Tâche 39) : déclenchement manuel d'une évaluation, en plus
    # du balayage périodique (app.alerts.jobs.sweep_alert_rules_task).
    # Revue finale Vague C (point 4) : la séquence (garde `config.kind`,
    # garde d'écriture, dédoublonnage d'une évaluation pending récente) est
    # désormais partagée avec le tool MCP run_alert_rule via
    # evaluate_alert_now_service (app.alerts.service) — les deux surfaces
    # divergeaient avant cette extraction (cf. docstring du module).
    evaluation_id, created = evaluate_alert_now_service(session, user=user, item_id=item_id)
    return EvaluateAlertResponse(evaluationId=evaluation_id, created=created)


@router.get("/alerts/{item_id}/evaluations", response_model=list[EvaluationStatus])
def get_alert_evaluations(
    item_id: str,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[EvaluationStatus]:
    _require_alert_read_access(session, user=user, item_id=item_id)
    limit = min(limit, _EVALUATIONS_MAX_LIMIT)
    rows = alerts_repo.list_evaluations(
        session, tenant_id=user.tenant_id, alert_rule_item_id=item_id, limit=limit, offset=offset
    )
    return [
        EvaluationStatus(
            id=r.id,
            value=r.value,
            state=r.state,
            transitioned=r.transitioned,
            error=r.error,
            notifyStatus=r.notify_status,
            notifyError=r.notify_error,
            createdAt=r.created_at.isoformat(),
        )
        for r in rows
    ]

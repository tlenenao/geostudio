# SPDX-License-Identifier: Apache-2.0
"""Couche de service partagée REST<->MCP pour le déclenchement manuel d'une
évaluation d'AlertRule (D04, SP-C6 Tâche 39) — extraite en revue finale
Vague C (point 4), même patron que app.pipelines.service.run_pipeline_service
(SP-43 Étape 8) : POST /alerts/{item_id}/evaluate (app.alerts.routes) et le
tool MCP run_alert_rule (app.mcp.tools.alerts) dupliquaient la même
séquence avec 3 divergences, fermées ici :

  a. la route REST ne vérifiait jamais `config.kind == "alert"` — un item
     en écriture quelconque (app, carte…) pouvait créer une
     `alert_evaluation` et déférer un job voué à échouer ;
  b. permissions divergentes : REST exigeait "write", le tool MCP
     seulement "read". Politique retenue ici pour les deux surfaces :
     "write" — déclencher une évaluation consomme des ressources (job
     procrastinate + notifications de canal potentielles), au même titre
     que run_pipeline_service exige "write" pour /pipelines/{id}/run,
     jamais "read" pour une action qui a un effet de bord ;
  c. aucune déduplication d'une évaluation "pending" récente : le balayage
     périodique en a une (app.alerts.repository.list_due_rules /
     _PENDING_RECLAIM_MINUTES — une évaluation "pending" plus jeune que
     cette fenêtre est présumée en cours, pas bloquée) ; le déclenchement
     manuel en profite maintenant identiquement."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.alerts import jobs as alerts_jobs
from app.alerts import repository as alerts_repo
from app.alerts.repository import _PENDING_RECLAIM_MINUTES
from app.configs import repository as configs_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def _require_alert_rule_config(session: Session, item_id: str) -> None:
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "alert":
        raise HTTPException(status_code=404, detail="alert rule not found")


def _require_alert_write_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="write", item=facts):
        raise HTTPException(status_code=404, detail="alert rule not found")


def evaluate_alert_now_service(session: Session, *, user: User, item_id: str) -> tuple[str, bool]:
    """Retourne `(evaluation_id, created)`. `created=False` signale une
    évaluation "pending" déjà en cours (créée il y a moins de
    `_PENDING_RECLAIM_MINUTES`), réutilisée telle quelle plutôt que
    dupliquée — aucun second job n'est déféré dans ce cas."""
    _require_alert_rule_config(session, item_id)
    _require_alert_write_access(session, user=user, item_id=item_id)

    latest = alerts_repo.get_latest_evaluation(
        session, tenant_id=user.tenant_id, alert_rule_item_id=item_id
    )
    if latest is not None and latest.state == "pending":
        created_at = latest.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        if (datetime.now(UTC) - created_at) < timedelta(minutes=_PENDING_RECLAIM_MINUTES):
            return latest.id, False

    evaluation = alerts_repo.create_evaluation(
        session, tenant_id=user.tenant_id, alert_rule_item_id=item_id
    )
    # Commit avant de déférer — même raison que sweep_alert_rules_task.
    session.commit()
    alerts_jobs.evaluate_alert_task.defer(evaluation_id=evaluation.id, tenant_id=user.tenant_id)
    return evaluation.id, True

# SPDX-License-Identifier: Apache-2.0
"""Validation directe du kind="report" pour app.configs. Reproduit exactement
app.configs.alert_validation/bookmark_validation : bookmarkItemId désigne
toujours un item de resourceType "bookmark", et app.configs importe déjà
app.items, donc aucune dépendance croisée interdite entre modules à
contourner (design SP-17b §Modèle de données)."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_report_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "report":
        return
    payload = config.report
    assert payload is not None  # garanti par BuilderConfig._require_kind_payload

    if len(payload.refreshPolicy.cron.split()) != 5:
        # REV-275 : jumelle de P18.08 — le balayage tourne toutes les 5 min, un cron
        # à 6 champs n'a aucun sens. Écriture seulement (configs existantes relisibles).
        raise HTTPException(
            status_code=422,
            detail=f"cron must have exactly 5 fields: {payload.refreshPolicy.cron!r}",
        )

    facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId
    )
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Même message pour non-trouvé et non-lisible : ne pas divulguer
        # l'existence du bookmark, même convention que app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="bookmark not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    assert target is not None  # get_access_facts vient d'en confirmer l'existence
    if target.resourceType != "bookmark":
        raise HTTPException(status_code=422, detail="bookmark not found")

    # c01-014 : le rendu s'exécute avec les droits du propriétaire du rapport ; qui modifie
    # destinataires/canaux doit donc lui-même pouvoir lire l'app rendue (pas seulement le bookmark).
    bookmark_config = configs_repo.get_config_by_item(session, payload.bookmarkItemId)
    bookmark = bookmark_config.config.bookmark if bookmark_config is not None else None
    if bookmark is not None:
        app_facts = items_repo.get_access_facts(
            session, tenant_id=user.tenant_id, item_id=bookmark.appId
        )
        if app_facts is None or not can(session, user_id=user.id, action="read", item=app_facts):
            raise HTTPException(status_code=422, detail="target app not readable")

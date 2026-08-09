# SPDX-License-Identifier: Apache-2.0
"""Validation directe du kind="report" pour app.configs. Reproduit exactement
app.configs.alert_validation/bookmark_validation : bookmarkItemId désigne
toujours un item de resourceType "bookmark", et app.configs importe déjà
app.items, donc aucune dépendance croisée interdite entre modules à
contourner (design SP-17b §Modèle de données)."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_report_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "report":
        return
    payload = config.report
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Même message pour non-trouvé et non-lisible : ne pas divulguer
        # l'existence du bookmark, même convention que app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="bookmark not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "bookmark":
        raise HTTPException(status_code=422, detail="bookmark not found")

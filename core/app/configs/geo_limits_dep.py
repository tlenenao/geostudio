# SPDX-License-Identifier: Apache-2.0
"""Dépendance FastAPI : limites géographiques de l'appelant (GAP-27, REV-121).

Vit dans app.configs (comme guest_access) : elle a besoin du GuestActor, que
app.sharing (plus bas dans le contrat de couches) ne peut pas importer.
Résolution : utilisateur authentifié → ses limites ; invité d'un lien de partage
→ celles du CRÉATEUR du lien (la délégation n'excède jamais le délégant) ;
anonyme → toute collection portant une limite devient invisible (spec §2.1)."""

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.sharing.geo_limits import resolve_geo_limits


def get_request_geo_limits(
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
) -> dict[str, list[dict]]:
    if user is not None:
        return resolve_geo_limits(session, tenant_id=user.tenant_id, user_id=user.id)
    if guest is not None:
        return resolve_geo_limits(session, tenant_id=guest.tenant_id, user_id=guest.created_by)
    return resolve_geo_limits(session, tenant_id=None, user_id=None)

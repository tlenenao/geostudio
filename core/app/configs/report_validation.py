# SPDX-License-Identifier: Apache-2.0
"""Direct kind="report" validation for app.configs. Mirrors
app.configs.alert_validation/bookmark_validation exactly: bookmarkItemId
always refers to an item of resourceType "bookmark", and app.configs already
imports app.items, so there is no forbidden cross-module dependency to route
around (SP-17b design §Modèle de données)."""
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
        # Same message for not-found and not-readable: don't leak bookmark
        # existence, same convention as app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="bookmark not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.bookmarkItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "bookmark":
        raise HTTPException(status_code=422, detail="bookmark not found")

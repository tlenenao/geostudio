# SPDX-License-Identifier: Apache-2.0
"""Direct kind="alert" validation for app.configs. Mirrors
app.configs.bookmark_validation exactly: datasetItemId always refers to an
item of resourceType "dataset", and app.configs already imports app.items
(routes.py's _require_access), so there is no forbidden cross-module
dependency to route around. The condition expression itself is already
validated at the Pydantic level (AlertCondition._require_valid_expr,
Task 2) — nothing to re-check here."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_alert_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "alert":
        return
    payload = config.alert
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=payload.datasetItemId
    )
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak dataset
        # existence, same convention as app.configs.bookmark_validation.
        raise HTTPException(status_code=422, detail="dataset not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.datasetItemId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "dataset":
        raise HTTPException(status_code=422, detail="dataset not found")

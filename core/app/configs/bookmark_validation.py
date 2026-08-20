# SPDX-License-Identifier: Apache-2.0
"""Direct kind="bookmark" validation for app.configs. Unlike dataset_validation.py,
no registry indirection is needed here: appId always refers to an app/dashboard
item, and app.configs already imports app.items (see routes.py's _require_access),
so there is no forbidden cross-module dependency to route around (SP-14m §3).
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def validate_bookmark_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "bookmark":
        return
    payload = config.bookmark
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.appId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak app
        # existence, same convention as app.collections.dataset_validation.
        raise HTTPException(status_code=422, detail="app not found")

    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=payload.appId)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType not in ("app", "dashboard"):
        raise HTTPException(status_code=422, detail="app not found")

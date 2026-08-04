# SPDX-License-Identifier: Apache-2.0
"""Registers the kind="dataset" validator for app.configs (see
app.configs.dataset_validation for why this indirection exists). Imported for
its side effect by app.main, which is the only layer allowed to know about
both app.collections and app.configs.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.dataset_validation import register_dataset_validator
from app.configs.schemas import BuilderConfig
from app.sharing.authorization import can
from app.users.models import User


def _validate_dataset_payload(session: Session, config: BuilderConfig, user: User) -> None:
    payload = config.dataset
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=payload.collectionId,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail="collection not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        # Same message as the not-found branch: don't leak collection existence.
        raise HTTPException(status_code=422, detail="collection not found")


register_dataset_validator("collection", _validate_dataset_payload)

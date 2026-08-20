# SPDX-License-Identifier: Apache-2.0
"""Registers the kind="dataset" validator for source="arcgis" payloads
(SP-14k). Same registry indirection as app.collections.dataset_validation
(see app.configs.dataset_validation for why) — app.main imports this module
for its side effect, alongside app.collections's registration."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.dataset_validation import register_dataset_validator
from app.configs.schemas import BuilderConfig
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def _validate_arcgis_dataset_payload(session: Session, config: BuilderConfig, user: User) -> None:
    payload = config.dataset
    assert payload is not None
    assert payload.arcgisItemId is not None
    record = harvest_repo.get_feature_layer_record(
        session,
        tenant_id=user.tenant_id,
        item_id=payload.arcgisItemId,
    )
    if record is None or record.external_url is None:
        raise HTTPException(status_code=422, detail="arcgis layer not found")
    facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=payload.arcgisItemId
    )
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Même message que la branche introuvable : ne pas révéler l'existence de l'item.
        raise HTTPException(status_code=422, detail="arcgis layer not found")


register_dataset_validator("arcgis", _validate_arcgis_dataset_payload)

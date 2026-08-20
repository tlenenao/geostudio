# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="dataset" payloads without
importing app.collections or app.harvest (forbidden by the layered-architecture
contract: both sit above app.configs). Validators are registered per
`DatasetPayload.source` by the modules that own each source's semantics
(app.collections for "collection", app.harvest for "arcgis" — SP-14k);
app.main wires both imports together at startup.
"""

from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

DatasetValidator = Callable[[Session, BuilderConfig, User], None]

_validators: dict[str, DatasetValidator] = {}


def register_dataset_validator(source: str, validator: DatasetValidator) -> None:
    _validators[source] = validator


def _validate_source_pipeline(session: Session, source_pipeline_id: str, *, user: User) -> None:
    facts = items_repo.get_access_facts(
        session, tenant_id=user.tenant_id, item_id=source_pipeline_id
    )
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Same message for not-found and not-readable: don't leak pipeline
        # existence, same convention as app.configs.alert_validation.
        raise HTTPException(status_code=422, detail="pipeline not found")
    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=source_pipeline_id)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "pipeline":
        raise HTTPException(status_code=422, detail="pipeline not found")


def validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    payload = config.dataset
    assert payload is not None
    validator = _validators.get(payload.source)
    assert validator is not None, f"no dataset validator registered for source={payload.source!r}"
    validator(session, config, user)
    if payload.sourcePipelineId is not None:
        _validate_source_pipeline(session, payload.sourcePipelineId, user=user)

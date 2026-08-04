# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="dataset" payloads without
importing app.collections or app.harvest (forbidden by the layered-architecture
contract: both sit above app.configs). Validators are registered per
`DatasetPayload.source` by the modules that own each source's semantics
(app.collections for "collection", app.harvest for "arcgis" — SP-14k);
app.main wires both imports together at startup.
"""
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User

DatasetValidator = Callable[[Session, BuilderConfig, User], None]

_validators: dict[str, DatasetValidator] = {}


def register_dataset_validator(source: str, validator: DatasetValidator) -> None:
    _validators[source] = validator


def validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    payload = config.dataset
    assert payload is not None
    validator = _validators.get(payload.source)
    assert validator is not None, f"no dataset validator registered for source={payload.source!r}"
    validator(session, config, user)

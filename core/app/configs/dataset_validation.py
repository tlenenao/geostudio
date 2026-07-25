# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="dataset" payloads without
importing app.collections (forbidden by the layered-architecture contract:
app.collections sits above app.configs). The concrete validator is registered
by app.collections at import time; app.main wires the import together.
"""
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User

DatasetValidator = Callable[[Session, BuilderConfig, User], None]

_validator: DatasetValidator | None = None


def register_dataset_validator(validator: DatasetValidator) -> None:
    global _validator
    _validator = validator


def validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    assert _validator is not None, "no dataset validator registered (app.collections not imported)"
    _validator(session, config, user)

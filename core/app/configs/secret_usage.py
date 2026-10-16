# SPDX-License-Identifier: Apache-2.0
"""Contrôle d'usage des secrets à l'écriture d'une config (REV-331/342). Une config de
pipeline ou d'alerte référence un secret par son nom mais s'exécute sous l'identité de son
propriétaire : sans ce contrôle, un éditeur d'un objet partagé exploite un secret auquel il
n'a pas droit (confused deputy). app.configs est sous app.secrets : même patron de
registre que pipeline_validation — app.pipelines.config_validation (importé par app.main)
enregistre le vrai contrôle."""

from collections.abc import Callable, Iterable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.users.models import User

SecretUsageChecker = Callable[[Session, User, str], bool]

_checker: SecretUsageChecker | None = None


def register_secret_usage_checker(checker: SecretUsageChecker) -> None:
    global _checker
    _checker = checker


def assert_secrets_usable(session: Session, user: User, names: Iterable[str | None]) -> None:
    """422 si `user` ne peut pas utiliser l'un des secrets existants cités. Un nom qui ne
    désigne aucun secret reste accepté (brouillon écrit avant le secret ; échec à l'exécution)."""
    wanted = sorted({n for n in names if n})
    if not wanted:
        return
    if _checker is None:  # fail-closed : jamais d'écriture sans contrôle branché
        raise RuntimeError("secret usage checker not registered")
    for name in wanted:
        if not _checker(session, user, name):
            raise HTTPException(
                status_code=422, detail=f"secret '{name}' is not usable by the current user"
            )

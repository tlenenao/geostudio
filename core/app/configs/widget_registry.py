# SPDX-License-Identifier: Apache-2.0
"""Types de widget acceptés à l'écriture d'une config (REV-278a) : les types
natifs du shell (liste `builtin_widget_types.json`, tenue en parité avec le
registre React par shell/src/builder/widgets/builtinWidgetTypes.test.ts) ou
l'id d'une extension activée du tenant (l'id sous lequel le shell enregistre
un widget d'extension)."""

import json
import logging
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.document_validation import document_warnings, widget_nodes
from app.configs.repository import ConfigRead
from app.configs.schemas import BuilderConfig
from app.extensions.models import Extension

_logger = logging.getLogger(__name__)

BUILTIN_WIDGET_TYPES: frozenset[str] = frozenset(
    json.loads((Path(__file__).parent / "builtin_widget_types.json").read_text(encoding="utf-8"))
)


def widget_type_errors(session: Session, config: BuilderConfig, *, tenant_id: str) -> list[str]:
    layouts = ([config.layout] if config.layout else []) + [p.layout for p in config.pages]
    nodes = widget_nodes([lay.model_dump() for lay in layouts])
    unknown = [n for n in nodes if n["widget"] not in BUILTIN_WIDGET_TYPES]
    if not unknown:
        return []
    registered = set(
        session.scalars(
            select(Extension.id).where(
                Extension.tenant_id == tenant_id,
                Extension.enabled.is_(True),
                Extension.id.in_({n["widget"] for n in unknown}),
            )
        )
    )
    return [
        f"widget '{n.get('id') or '<sans id>'}': unknown widget type '{n['widget']}'"
        for n in unknown
        if n["widget"] not in registered
    ]


def validate_widget_types(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    errs = widget_type_errors(session, config, tenant_id=tenant_id)
    if errs:
        raise HTTPException(status_code=422, detail="; ".join(errs))


def with_warnings(session: Session, read: ConfigRead, *, tenant_id: str) -> ConfigRead:
    """`ConfigRead` enrichi de ce qu'une écriture refuserait aujourd'hui
    (REV-278/305) ; la lecture, elle, n'est jamais refusée."""
    try:
        warnings = document_warnings(read.config) + widget_type_errors(
            session, read.config, tenant_id=tenant_id
        )
    except Exception:
        # REV-305 : le calcul des avertissements ne doit jamais empêcher une
        # lecture. Si le calcul échoue, retourner la config sans avertissements.
        _logger.warning("failed to compute config warnings", exc_info=True)
        warnings = []
    return read.model_copy(update={"warnings": warnings})

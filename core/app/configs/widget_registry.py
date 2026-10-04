# SPDX-License-Identifier: Apache-2.0
"""Types de widget acceptés à l'écriture d'une config (REV-278a) : les types
natifs du shell (liste `builtin_widget_types.json`, tenue en parité avec le
registre React par shell/src/builder/widgets/builtinWidgetTypes.test.ts) ou
l'id d'une extension activée du tenant (l'id sous lequel le shell enregistre
un widget d'extension)."""

import json
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.configs.document_validation import _widget_nodes
from app.configs.schemas import BuilderConfig
from app.extensions.models import Extension

BUILTIN_WIDGET_TYPES: frozenset[str] = frozenset(
    json.loads((Path(__file__).parent / "builtin_widget_types.json").read_text(encoding="utf-8"))
)


def widget_type_errors(session: Session, config: BuilderConfig, *, tenant_id: str) -> list[str]:
    layouts = ([config.layout] if config.layout else []) + [p.layout for p in config.pages]
    nodes = _widget_nodes([lay.model_dump() for lay in layouts])
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
        f"widget '{n['id']}': unknown widget type '{n['widget']}'"
        for n in unknown
        if n["widget"] not in registered
    ]


def validate_widget_types(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    errs = widget_type_errors(session, config, tenant_id=tenant_id)
    if errs:
        raise HTTPException(status_code=422, detail="; ".join(errs))

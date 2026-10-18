# SPDX-License-Identifier: Apache-2.0
"""Contexte d'audit ambiant (AUD-103) : champs ajoutés à toute ligne `audit_log`
écrite pendant un appel d'outil MCP (`turnId` du tour copilote, `origin`), pour
relier une création/modification métier au tour qui l'a provoquée sans changer la
signature des dizaines d'appelants de `write_audit`."""

import hashlib
import json
from contextvars import ContextVar
from typing import Any

audit_extra: ContextVar[dict[str, Any] | None] = ContextVar("audit_extra", default=None)


def _jsonable(value: Any) -> Any:
    # Les kwargs d'outil MCP sont déjà validés : modèles pydantic, pas des dicts bruts.
    dump = getattr(value, "model_dump", None)
    return dump(mode="json") if callable(dump) else str(value)


def args_sha256(arguments: Any) -> str:
    """Empreinte stable d'arguments d'outil (JSON canonique, clés triées)."""
    raw = json.dumps(arguments, sort_keys=True, ensure_ascii=False, default=_jsonable)
    return hashlib.sha256(raw.encode()).hexdigest()

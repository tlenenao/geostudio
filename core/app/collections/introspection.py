# SPDX-License-Identifier: Apache-2.0
"""Types d'introspection + exceptions. L'implémentation Postgres réelle
(pg_catalog) arrive dans introspection_pg (task 7) ; les routes reçoivent
l'introspecteur par dépendance injectable."""

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.orm import Session

FieldType = Literal[
    "string", "integer", "number", "boolean", "date", "datetime", "enum", "list", "unsupported"
]


class TableNotFound(Exception):
    pass


class UnsupportedTable(Exception):
    """Table existante mais non enregistrable (PK composite, 2 géométries,
    vue matérialisée…) — reason est montré tel quel dans le 400."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: FieldType
    required: bool
    max_length: int | None = None
    enum_values: list[str] | None = None
    list_item_type: FieldType | None = None


@dataclass(frozen=True)
class TableInfo:
    table_name: str
    pk_column: str
    geometry_column: str | None
    geometry_type: str | None
    srid: int | None
    columns: list[ColumnInfo] = field(default_factory=list)


Introspector = Callable[[Session, str], TableInfo]


def hide_sensitive_columns(info: TableInfo, sensitive_fields: list[str]) -> TableInfo:
    """Retire du TableInfo introspecté les colonnes marquées sensibles
    (GAP-22) — appelé côté masqué, AVANT toute construction de requête
    SQL nommant ces colonnes : sous gis_rls_masked, nommer une colonne
    jamais grantée fait échouer toute l'instruction (permission denied),
    elle n'est jamais silencieusement omise par Postgres."""
    if not sensitive_fields:
        return info
    hidden = set(sensitive_fields)
    return dataclasses.replace(info, columns=[c for c in info.columns if c.name not in hidden])

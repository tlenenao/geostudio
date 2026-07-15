# SPDX-License-Identifier: Apache-2.0
"""Types d'introspection + exceptions. L'implémentation Postgres réelle
(pg_catalog) arrive dans introspection_pg (task 7) ; les routes reçoivent
l'introspecteur par dépendance injectable."""
from dataclasses import dataclass, field
from typing import Callable, Literal

from sqlalchemy.orm import Session

FieldType = Literal[
    "string", "integer", "number", "boolean", "date", "datetime", "enum", "unsupported"
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


@dataclass(frozen=True)
class TableInfo:
    table_name: str
    pk_column: str
    geometry_column: str | None
    geometry_type: str | None
    srid: int | None
    columns: list[ColumnInfo] = field(default_factory=list)


Introspector = Callable[[Session, str], TableInfo]

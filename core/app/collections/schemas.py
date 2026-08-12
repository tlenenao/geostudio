# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    # 50 = 63 (limite d'identifiant Postgres) − len("ix_" + "_tenant_id") :
    # garantit que le nom d'index tenant_id généré par le DDL tient en 63 octets
    # sans troncature (cf. app/collections/ddl.py).
    tableName: str = Field(min_length=1, max_length=50)
    title: str | None = None
    description: str = ""
    isPublic: bool = False


class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    isPublic: bool | None = None
    editable: bool | None = None


class EmptyCollectionColumn(BaseModel):
    # 59 = 63 (limite d'identifiant Postgres) - len('ix__tenant_id') marge la
    # plus courte possible côté nom de colonne ; en pratique une colonne
    # inférée par le wizard ne colle jamais à cette limite.
    name: str = Field(min_length=1, max_length=59)
    sqlType: Literal["text", "integer", "bigint", "double precision", "boolean", "date", "timestamptz"]


class EmptyCollectionCreate(BaseModel):
    title: str = Field(min_length=1)
    columns: list[EmptyCollectionColumn] = Field(default_factory=list)
    geometryType: Literal[
        "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon",
    ] | None = None
    srid: int | None = None

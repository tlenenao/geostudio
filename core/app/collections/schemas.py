# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CollectionCreate(BaseModel):
    # 50 = 63 (limite d'identifiant Postgres) − len("ix_" + "_tenant_id") :
    # garantit que le nom d'index tenant_id généré par le DDL tient en 63 octets
    # sans troncature (cf. app/collections/ddl.py).
    tableName: str = Field(min_length=1, max_length=50)
    title: str | None = None
    description: str = ""
    isPublic: bool = False


class CollectionPermissions(BaseModel):
    """Miroir d'`ItemPermissions` (`app/items/schemas.py`) pour les
    collections. Calculé depuis `decide()`, jamais recalculé côté client.

    `delete` n'est PAS le verdict générique de `decide()` : `unregister_collection`
    (DELETE /collections/{id}) est gardé par `require_privilege(...,
    "admin.collections.manage")` seul, pas par `can()`/`decide()`. MAIS le
    calcul de `delete` ici (`app/collections/repository.py::_collection_permissions`)
    reflète encore aujourd'hui `actor_is_admin` (la colonne synchronisée
    `User.is_admin`), PAS le privilège `admin.collections.manage` lui-même —
    un rôle personnalisé qui détiendrait ce privilège sans être le rôle
    prédéfini "admin" verrait donc `delete: false` ici alors que la route
    DELETE le laisserait effectivement passer. Écart architectural connu,
    documenté comme suivi non bloquant plutôt que corrigé unilatéralement
    (le même arbitrage se pose sur d'autres surfaces `is_admin`-dérivées,
    ex. extensions) — ne pas réconcilier ce docstring silencieusement avec
    le code sans trancher la question plus large en amont.
    """

    read: bool
    write: bool
    delete: bool
    share: bool


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
    sqlType: Literal[
        "text", "integer", "bigint", "double precision", "boolean", "date", "timestamptz"
    ]

    @field_validator("name")
    @classmethod
    def _reject_reserved_names(cls, v: str) -> str:
        # Noms déjà utilisés par create_empty_collection dans le DDL généré
        # (id serial PRIMARY KEY, tenant_id text NOT NULL, geom geometry(...))
        # — une collision produirait un DBAPIError Postgres non catché (500)
        # plutôt qu'un 422 propre.
        if v in {"id", "tenant_id", "geom"}:
            raise ValueError(f"column name '{v}' is reserved")
        return v


class EmptyCollectionCreate(BaseModel):
    title: str = Field(min_length=1)
    columns: list[EmptyCollectionColumn] = Field(default_factory=list)
    geometryType: (
        Literal[
            "Point",
            "MultiPoint",
            "LineString",
            "MultiLineString",
            "Polygon",
            "MultiPolygon",
        ]
        | None
    ) = None
    srid: int | None = None

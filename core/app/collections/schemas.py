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
    "admin.collections.manage")` seul, pas par `can()`/`decide()`. Le calcul de
    `delete` ici (`app/collections/repository.py::_collection_permissions`)
    reflète directement ce même privilège via `has_privilege()`
    (`app/roles/guards.py`), pas `actor_is_admin`/`User.is_admin` — un rôle
    sur mesure qui détiendrait `admin.collections.manage` sans être le rôle
    prédéfini "admin" voit donc `delete: true` ici exactement quand la route
    DELETE le laisserait effectivement passer (SP-35, corrige l'écart
    documenté par SP-31 — l'ancien comportement retournait `actor_is_admin`
    ici).

    `read`, lui, reste le verdict brut de `decide()` (action "read") — il ne
    dit RIEN sur le fait que la réponse qui porte ce bloc `permissions` a été
    servie avec succès. Depuis le correctif `delete` ci-dessus et l'extension
    du bypass `can_manage_collections` à GET/PATCH/DELETE et
    /schema/sharing (fix wave de revue finale SP-35), une réponse 200 tout à
    fait légitime peut porter `read: false` : un porteur du privilège
    `admin.collections.manage` qui n'est ni propriétaire ni bénéficiaire d'un
    partage voit son 404 de visibilité levé par `can_manage_collections`,
    donc reçoit bien la collection, alors que `decide()` — qui ignore ce
    privilège — continue de répondre `False` à la question read. Ce n'est pas
    une incohérence à corriger : `read` répond uniquement « `decide()`
    autoriserait-il un accès classique (propriétaire/partage/public) ? »,
    pas « cette réponse a-t-elle été servie ? ».
    """

    read: bool
    write: bool
    delete: bool
    share: bool


class AttachmentFieldSpec(BaseModel):
    """Un champ `attachment` déclaré sur une collection (chantier 4.12) —
    pas une colonne SQL réelle, juste un slot nommé fusionné dans
    GET /collections/{id}/schema (app/collections/schema_json.py)."""

    key: str
    label: str


class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    isPublic: bool | None = None
    editable: bool | None = None
    attachmentFields: list[AttachmentFieldSpec] | None = None


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

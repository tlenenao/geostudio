# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field

Cardinality = Literal["one_to_one", "one_to_many", "many_to_many"]


class RelationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    cardinality: Cardinality
    parentCollectionId: str
    childCollectionId: str
    parentKey: str | None = None  # défaut : PK du parent
    childKey: str | None = None  # 1-1/1-N : colonne FK (obligatoire) ; N-N : défaut PK de l'enfant
    linkCollectionId: str | None = None  # N-N seulement
    linkParentKey: str | None = None
    linkChildKey: str | None = None
    onDelete: Literal["restrict", "cascade"] = "restrict"


class RelationOut(BaseModel):
    id: str
    name: str
    cardinality: Cardinality
    parentCollectionId: str
    childCollectionId: str
    parentKey: str
    childKey: str
    linkCollectionId: str | None
    linkParentKey: str | None
    linkChildKey: str | None
    onDelete: Literal["restrict", "cascade"]


class RelatedRecords(BaseModel):
    relation: RelationOut
    direction: Literal["children", "parents"]
    collectionId: str  # collection des enregistrements liés
    features: list[dict]
    numberReturned: int
    numberMatched: int | None = None

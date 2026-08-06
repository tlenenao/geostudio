# SPDX-License-Identifier: Apache-2.0
"""Catalogue des opérations du Pipeline : 8 op de données pures livrées en
Phase 1 (SP-15a — la fourchette 6-8 op de l'étude de faisabilité §5), + 5 op
de transformation spatiale étage 1 et 1 writer (`writer.dataset`) livrés en
Phase 3 étage 1 (SP-15c). Chaque op porte un manifeste de params typé
(Pydantic), publié en JSON Schema par GET /pipelines/ops pour que SP-15b
réutilise le mécanisme WcWidgetManifest/generatedPropsPanel (SP-8a) sans
redesign (design SP-15a §5).

filter.expr/derive.expr/aggregate.metrics[*]/h3Aggregate.metrics[*] sont des
chaînes SQL DuckDB bornées, PAS du CEL (correction du design SP-15a §5.1 —
aucun moteur CEL ne tourne côté serveur) : elles ne sont validées
syntaxiquement qu'à l'exécution (app.pipelines.expr_validation), jamais ici
— ce module ne valide que la FORME des params, pas la sémantique des
expressions."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReaderCollectionParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})


class TransformFilterParams(BaseModel):
    expr: str


class TransformSelectParams(BaseModel):
    columns: dict[str, str | None] = Field(default_factory=dict)


class TransformDeriveParams(BaseModel):
    column: str
    expr: str


class TransformAggregateParams(BaseModel):
    groupBy: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)


class TransformJoinParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"


class WriterCollectionParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})


class WriterExportParams(BaseModel):
    format: Literal["geojson", "csv"]
    key: str


class TransformBufferParams(BaseModel):
    distance: float
    unit: Literal["meters", "native"] = "meters"


class TransformReprojectParams(BaseModel):
    targetCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")


class TransformIntersectionParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    how: Literal["inner", "left"] = "inner"
    outputGeometry: Literal["left", "intersection"] = "left"


class TransformCountWithinParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    countColumn: str = "count"
    predicate: Literal["intersects", "contains"] = "intersects"


class TransformH3AggregateParams(BaseModel):
    resolution: int = Field(..., ge=0, le=15)
    metrics: dict[str, str]


class WriterDatasetParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    datasetId: str | None = None    # pk d'un item BuilderConfig(kind="dataset") existant
    title: str | None = None        # requis si datasetId est None

    @model_validator(mode="after")
    def _require_title_for_new_dataset(self) -> "WriterDatasetParams":
        if self.datasetId is None and not (self.title and self.title.strip()):
            raise ValueError("title is required when datasetId is not provided")
        return self


OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "transform.buffer": "transform",
    "transform.reproject": "transform",
    "transform.intersection": "transform",
    "transform.countWithin": "transform",
    "transform.h3Aggregate": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "transform.buffer": TransformBufferParams,
    "transform.reproject": TransformReprojectParams,
    "transform.intersection": TransformIntersectionParams,
    "transform.countWithin": TransformCountWithinParams,
    "transform.h3Aggregate": TransformH3AggregateParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def ops_catalog() -> dict[str, dict]:
    return {
        op: {"kind": OP_KINDS[op], "paramsSchema": model.model_json_schema()}
        for op, model in OP_PARAMS.items()
    }

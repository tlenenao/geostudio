# SPDX-License-Identifier: Apache-2.0
"""Catalogue des 8 opérations de données pures livrées en Phase 1 (SP-15a) —
la fourchette 6-8 op de l'étude de faisabilité §5. Chaque op porte un
manifeste de params typé (Pydantic), publié en JSON Schema par
GET /pipelines/ops pour que SP-15b réutilise le mécanisme
WcWidgetManifest/generatedPropsPanel (SP-8a) sans redesign (design §5).

filter.expr/derive.expr/aggregate.metrics[*] sont des chaînes SQL DuckDB
bornées, PAS du CEL (correction du design §5.1 — aucun moteur CEL ne
tourne côté serveur) : elles ne sont validées syntaxiquement qu'à
l'exécution (app.pipelines.expr_validation), jamais ici — ce module ne
valide que la FORME des params, pas la sémantique des expressions."""
from typing import Literal

from pydantic import BaseModel, Field


class ReaderCollectionParams(BaseModel):
    collectionId: str


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
    withCollectionId: str
    on: str
    how: Literal["inner", "left"] = "inner"


class WriterCollectionParams(BaseModel):
    collectionId: str


class WriterExportParams(BaseModel):
    format: Literal["geojson", "csv"]
    key: str


OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
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

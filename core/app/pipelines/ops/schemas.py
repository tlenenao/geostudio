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
from typing import Any, Literal

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
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"


class WriterCollectionParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    mode: Literal["append", "replace"] = Field(
        default="append",
        description=(
            "\"replace\" supprime TOUTES les données existantes de la "
            "collection cible avant d'écrire — irréversible, à réserver à "
            "une collection dédiée à ce pipeline."
        ),
    )


class WriterExportParams(BaseModel):
    format: Literal["geojson", "csv"]
    key: str


class TransformBufferParams(BaseModel):
    distance: float
    unit: Literal["meters", "native"] = "meters"


class TransformReprojectParams(BaseModel):
    targetCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")


class TransformIntersectionParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    how: Literal["inner", "left"] = "inner"
    outputGeometry: Literal["left", "intersection"] = "left"


class TransformCountWithinParams(BaseModel):
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})
    countColumn: str = "count"
    predicate: Literal["intersects", "contains"] = "intersects"


class TransformMergeParams(BaseModel):
    """Empile deux flux ligne à ligne (UNION ALL BY NAME, design SP-15g §3.2).
    Comme les 3 op binaires ci-dessus, sa seconde entrée vient soit de
    `withCollectionId` (collection brute), soit d'une arête `role="secondary"`
    (sortie déjà calculée d'une autre branche du pipeline) — jamais les deux à
    la fois, jamais ni l'un ni l'autre (app.pipelines.config_validation)."""
    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})


class TransformH3AggregateParams(BaseModel):
    resolution: int = Field(..., ge=0, le=15)
    metrics: dict[str, str]


class WriterDatasetParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    datasetId: str | None = None    # pk d'un item BuilderConfig(kind="dataset") existant
    title: str | None = None        # requis si datasetId est None
    mode: Literal["append", "replace"] = Field(
        default="append",
        description=(
            "\"replace\" supprime TOUTES les données existantes de la "
            "collection cible avant d'écrire — irréversible, à réserver à "
            "une collection dédiée à ce pipeline."
        ),
    )

    @model_validator(mode="after")
    def _require_title_for_new_dataset(self) -> "WriterDatasetParams":
        if self.datasetId is None and not (self.title and self.title.strip()):
            raise ValueError("title is required when datasetId is not provided")
        return self


class TransformQgisParams(BaseModel):
    """Op générique pour tout algorithme QGIS Processing de l'allowlist
    gelée (app.pipelines.ops.qgis_algorithms.QGIS_ALGORITHMS, design SP-15d
    §5/§10). `params` ne doit JAMAIS contenir INPUT/OUTPUT — le runtime les
    injecte (chemins scratch, design §6). `outputSrid` doit être renseigné
    explicitement quand l'algorithme change le CRS (ex. gdal:warpreproject
    via son propre param TARGET_CRS) ; laissé à None, le SRID de sortie est
    supposé identique à l'entrée — vrai pour la quasi-totalité des 50 op de
    l'allowlist, faux pour un algorithme de reprojection. Aucune conversion
    automatique d'unité : un DISTANCE/TOLERANCE d'un algorithme QGIS est
    dans les unités du CRS natif de la couche d'entrée, jamais auto-converti
    en mètres (vérifié empiriquement en design, §2)."""
    algorithmId: str
    params: dict[str, Any] = Field(default_factory=dict)
    outputSrid: str | None = Field(default=None, pattern=r"^[A-Za-z]+:\d+$")

    @model_validator(mode="after")
    def _check_allowlisted_and_required_params(self) -> "TransformQgisParams":
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

        schema = QGIS_ALGORITHMS.get(self.algorithmId)
        if schema is None:
            raise ValueError(f"algorithme non autorisé : {self.algorithmId}")
        required = {
            name for name, p in schema["parameters"].items() if not p["optional"]
        } - {"INPUT", "OUTPUT"}
        missing = required - self.params.keys()
        if missing:
            raise ValueError(
                f"{self.algorithmId} : paramètres requis manquants {sorted(missing)}"
            )
        return self


class ReaderConnectorRestParams(BaseModel):
    """Lecture d'une ressource REST paginée (design SP-15f §2). `secretName`
    référence un secret api_key/bearer_token/basic_auth/
    oauth2_client_credentials (SP-15e) ; None = endpoint public non
    authentifié. `recordsPath` est un chemin pointé vers le tableau
    d'enregistrements dans le corps de réponse (ex. "data.items") ; None =
    le corps de réponse EST le tableau."""
    baseUrl: str = Field(..., pattern=r"^https?://")
    path: str = ""
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    recordsPath: str | None = None
    paginator: Literal["none", "page_number", "cursor", "offset"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)
    secretName: str | None = None


class ReaderConnectorPostgresParams(BaseModel):
    """Lecture d'une requête SQL libre sur un Postgres distant (design
    SP-15f §2). `secretName` référence toujours un secret postgres_dsn
    (SP-15e) — pas de notion de DSN non authentifié, contrairement à REST.
    `query` n'est validée SELECT-only qu'à l'exécution (app.pipelines.connector_runtime),
    jamais ici (forme seulement) ni à la sauvegarde (design §6)."""
    secretName: str
    query: str


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
    "transform.qgis": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
    "writer.dataset": "writer",
    "reader.connector.rest": "reader",
    "reader.connector.postgres": "reader",
}
OP_KINDS["transform.merge"] = "transform"

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
    "transform.qgis": TransformQgisParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
    "writer.dataset": WriterDatasetParams,
    "reader.connector.rest": ReaderConnectorRestParams,
    "reader.connector.postgres": ReaderConnectorPostgresParams,
}
OP_PARAMS["transform.merge"] = TransformMergeParams

# Op dont la seconde entrée peut venir soit de `withCollectionId`, soit d'une
# arête `role="secondary"` (design SP-15g §2.2/§4.2). Exporté (pas
# `_`-préfixé) : importé directement par app.pipelines.config_validation,
# même package app.pipelines, aucune frontière de couches à traverser.
BINARY_OPS = {
    "transform.join", "transform.intersection", "transform.countWithin", "transform.merge",
}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def ops_catalog() -> dict[str, dict]:
    return {
        op: {
            "kind": OP_KINDS[op],
            "paramsSchema": model.model_json_schema(),
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
        for op, model in OP_PARAMS.items()
    }

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
            '"replace" supprime TOUTES les données existantes de la '
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
    """Empile deux flux ligne à ligne (UNION ALL BY NAME) : les colonnes
    communes fusionnent par nom, celles propres à un seul flux sont
    complétées à vide pour l'autre. La seconde entrée vient soit de
    `withCollectionId`, soit d'une connexion secondaire sur le canevas —
    jamais les deux à la fois, jamais ni l'une ni l'autre.

    Design SP-15g §3.2. Comme les 3 op binaires ci-dessus, cette contrainte
    sur la seconde entrée (soit `withCollectionId`, une collection brute,
    soit une arête `role="secondary"`, sortie déjà calculée d'une autre
    branche du pipeline) est vérifiée par app.pipelines.config_validation."""

    withCollectionId: str | None = Field(None, json_schema_extra={"format": "collection-id"})


class TransformH3AggregateParams(BaseModel):
    resolution: int = Field(..., ge=0, le=15)
    metrics: dict[str, str]


class WriterDatasetParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    datasetId: str | None = None  # pk d'un item BuilderConfig(kind="dataset") existant
    title: str | None = None  # requis si datasetId est None
    mode: Literal["append", "replace"] = Field(
        default="append",
        description=(
            '"replace" supprime TOUTES les données existantes de la '
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
    """Exécute un algorithme QGIS Processing de la liste autorisée. Renseignez
    `outputSrid` explicitement si l'algorithme change le système de
    coordonnées (ex. une reprojection) ; laissé vide, la sortie garde le
    système de coordonnées de l'entrée. Attention : les distances/tolérances
    d'un algorithme QGIS sont dans les unités du système de coordonnées de
    la couche d'entrée, jamais converties automatiquement en mètres.

    Allowlist gelée : app.pipelines.ops.qgis_algorithms.QGIS_ALGORITHMS
    (design SP-15d §5/§10). `params` ne doit JAMAIS contenir INPUT/OUTPUT —
    le runtime les injecte (chemins scratch, design §6). La règle
    « pas de conversion d'unité automatique » est vraie pour la quasi-totalité
    des 50 op de l'allowlist, fausse pour un algorithme de reprojection
    (vérifié empiriquement en design, §2)."""

    algorithmId: str
    params: dict[str, Any] = Field(default_factory=dict)
    outputSrid: str | None = Field(default=None, pattern=r"^[A-Za-z]+:\d+$")

    @model_validator(mode="after")
    def _check_allowlisted_and_required_params(self) -> "TransformQgisParams":
        from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS

        schema = QGIS_ALGORITHMS.get(self.algorithmId)
        if schema is None:
            raise ValueError(f"algorithme non autorisé : {self.algorithmId}")
        required = {name for name, p in schema["parameters"].items() if not p["optional"]} - {
            "INPUT",
            "OUTPUT",
        }
        missing = required - self.params.keys()
        if missing:
            raise ValueError(f"{self.algorithmId} : paramètres requis manquants {sorted(missing)}")
        return self


class ReaderConnectorRestParams(BaseModel):
    """Lecture d'une ressource REST paginée, avec authentification optionnelle
    (clé API, jeton, identifiants, ou OAuth2 client_credentials) et
    pagination configurable. `recordsPath` pointe vers le tableau
    d'enregistrements dans le corps de réponse (ex. "data.items") ; laissé
    vide, le corps de réponse EST directement le tableau.

    Design SP-15f §2. `secretName` référence un secret api_key/bearer_token/
    basic_auth/oauth2_client_credentials (SP-15e) ; None = endpoint public
    non authentifié."""

    baseUrl: str = Field(..., pattern=r"^https?://")
    path: str = ""
    method: Literal["GET", "POST"] = "GET"
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    recordsPath: str | None = None
    paginator: Literal["none", "page_number", "cursor", "offset"] = "none"
    paginatorConfig: dict[str, Any] = Field(default_factory=dict)
    secretName: str | None = Field(default=None, json_schema_extra={"format": "secret-name"})


class ReaderConnectorPostgresParams(BaseModel):
    """Lecture d'une requête SQL libre (SELECT uniquement) sur un Postgres
    distant, via un secret de connexion dédié. Fonctionne aussi contre un
    cluster Amazon Redshift, mêmes identifiants — attention : le SQL
    Redshift diverge du SQL PostgreSQL sur plusieurs points (types/fonctions
    non supportés), une requête acceptée ici peut malgré tout échouer côté
    Redshift avec une erreur explicite.

    Design SP-15f §2. `secretName` référence toujours un secret postgres_dsn
    (SP-15e) — pas de notion de DSN non authentifié, contrairement à REST.
    `query` n'est validée SELECT-only qu'à l'exécution
    (app.pipelines.connector_runtime), jamais ici (forme seulement) ni à la
    sauvegarde (design §6) — heuristique dialecte DuckDB, cf. limite
    Redshift ci-dessus.

    Compatibilité Redshift (GAP-16, design 2026-09-06 §5.4) : Redshift
    expose le protocole de câblage PostgreSQL (AWS, « Amazon Redshift is
    based on PostgreSQL ») — pointez le DSN d'un secret postgres_dsn vers
    l'endpoint du cluster (port 5439 par défaut) plutôt que vers un Postgres
    ordinaire."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    query: str


class ReaderConnectorSnowflakeParams(BaseModel):
    """Lecture d'une requête SQL libre (SELECT uniquement) sur un entrepôt
    Snowflake distant, via un secret de connexion dédié. Attention : la
    plupart des requêtes SnowSQL courantes passent (QUALIFY, accesseur
    semi-structuré `:`, LATERAL FLATTEN, ILIKE, UNION), mais SAMPLE (n)/
    TOP n/MINUS sont rejetées — à reformuler en LIMIT/EXCEPT.

    GAP-16, pendant de ReaderConnectorPostgresParams. `secretName` référence
    toujours un secret snowflake_dsn — pas de notion de DSN non authentifié,
    même contrat que reader.connector.postgres. `query` n'est validée
    SELECT-only qu'à l'exécution (app.pipelines.connector_runtime), jamais
    ici (forme seulement) ni à la sauvegarde (design §6) — même heuristique
    que pour Postgres, avec la même limite documentée en §5.3 (le texte est
    parsé avec le dialecte SQL DuckDB, pas le dialecte SnowSQL réel, d'où la
    liste de constructions rejetées ci-dessus)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
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
    "reader.connector.snowflake": "reader",
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
    "reader.connector.snowflake": ReaderConnectorSnowflakeParams,
}
OP_PARAMS["transform.merge"] = TransformMergeParams

# Op dont la seconde entrée peut venir soit de `withCollectionId`, soit d'une
# arête `role="secondary"` (design SP-15g §2.2/§4.2). Exporté (pas
# `_`-préfixé) : importé directement par app.pipelines.config_validation,
# même package app.pipelines, aucune frontière de couches à traverser.
BINARY_OPS = {
    "transform.join",
    "transform.intersection",
    "transform.countWithin",
    "transform.merge",
}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def _user_facing_description(description: str) -> str:
    """N'expose que le premier paragraphe d'un docstring de classe (avant le
    premier saut de ligne vide) comme description utilisateur du catalogue.

    Correctif revue finale GAP-16 (Important I2) : `model_json_schema()`
    reprend tel quel le docstring Python complet d'une classe de params dans
    sa clé `description` — pour 5 op (les connecteurs + transform.qgis/
    transform.merge), ce docstring contient du jargon développeur (noms de
    classes, chemins de module, renvois "design §n"/"SPnn") qui n'a rien à
    faire dans le tooltip de palette lu par
    shell/src/builder/pipeline/PipelinePalette.tsx. Le docstring de classe
    reste une documentation développeur complète (paragraphes suivants) ;
    seul le premier paragraphe — rédigé pour être compris par l'auteur d'un
    pipeline — atteint le catalogue exposé par GET /pipelines/ops."""
    return description.split("\n\n", 1)[0].strip()


def ops_catalog() -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for op, model in OP_PARAMS.items():
        schema = model.model_json_schema()
        if schema.get("description"):
            schema["description"] = _user_facing_description(schema["description"])
        catalog[op] = {
            "kind": OP_KINDS[op],
            "paramsSchema": schema,
            "acceptsSecondaryInput": op in BINARY_OPS,
        }
    return catalog

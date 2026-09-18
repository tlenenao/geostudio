# SPDX-License-Identifier: Apache-2.0
"""Manifestes de params typés (Pydantic) par op de pipeline : 8 op de
données pures livrées en Phase 1 (SP-15a), + 5 op de transformation
spatiale étage 1, 1 writer (`writer.dataset`) et 3 connecteurs livrés
ensuite. Chaque classe ci-dessous est publiée en JSON Schema par
`app.pipelines.ops.contracts.ops_catalog()` (GET /pipelines/ops) — le
registre par op (kind/moteur/licence/compilateur/catalogue) vit dans ce
module contracts.py, pas ici : ce fichier ne fait plus que fournir les
classes de forme des params, importées par contracts.py pour construire
`OPERATIONS` (chantier OperationContract, docs/superpowers/specs/
2026-09-16-operation-contract-design.md).

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


class TransformScaleGeometryParams(BaseModel):
    """Mise à l'échelle de la géométrie autour de l'origine (0, 0) — PAS
    autour du centre de la géométrie (vérifié empiriquement contre DuckDB
    spatial réel)."""

    xs: float
    ys: float


class TransformSwapCoordinatesParams(BaseModel):
    """Permute X et Y de la géométrie (ex. données saisies en latitude/longitude
    au lieu de longitude/latitude)."""


class TransformTranslateGeometryParams(BaseModel):
    """Translation de la géométrie.

    Géométrie 3D (avec Z) refusée : ST_Translate de l'extension spatiale
    DuckDB corrompt les coordonnées d'une géométrie avec Z (vérifié
    empiriquement, design vague 1 transformers DuckDB §0)."""

    dx: float
    dy: float


class TransformRotateGeometryParams(BaseModel):
    """Rotation de la géométrie autour de son propre centroïde.

    PAS autour de l'origine (0, 0) : ST_Rotate de DuckDB tourne nativement
    autour de l'origine, ce nœud recentre avant/après. Géométrie 3D refusée,
    même limite que transform.translateGeometry (ce nœud compose
    ST_Translate en interne, design vague 1 transformers DuckDB §0)."""

    radians: float


class TransformCreateGeometryParams(BaseModel):
    """Remplace la géométrie de chaque ligne par une géométrie WKT littérale
    (ex. "POINT(2.35 48.85)"). Utile pour créer une géométrie constante ou
    tester un pipeline sans source spatiale réelle."""

    wkt: str


class TransformRoundCoordinatesParams(BaseModel):
    """Réduit la précision des coordonnées de la géométrie à une taille de
    grille donnée (ex. gridSize=0.0001 ≈ 11 m en EPSG:4326).

    PAS un nombre de décimales : une taille de grille (mêmes unités que le
    système de coordonnées courant)."""

    gridSize: float = Field(..., gt=0)


class TransformConcatCoordinatesParams(BaseModel):
    """Construit la géométrie (un point) à partir de deux colonnes attribut
    X/Y existantes — remplace la géométrie courante."""

    xColumn: str
    yColumn: str


class TransformExtractCoordinatesParams(BaseModel):
    """X et Y de la géométrie → deux colonnes attribut séparées."""

    xColumn: str = "x"
    yColumn: str = "y"


class TransformExtractElevationParams(BaseModel):
    """Composante Z de la géométrie → colonne attribut (NULL si la géométrie
    n'a pas de Z)."""

    column: str = "elevation"


class TransformExtractDimensionParams(BaseModel):
    """Dimension de COORDONNÉES de la géométrie (2 ou 3 selon la présence
    d'un Z) → colonne attribut.

    Distinct de la dimension topologique (point/ligne/polygone) : ST_Dimension
    de DuckDB retourne cette dernière (0/1/2), pas ce que ce nœud expose
    (vérifié empiriquement, design vague 1 transformers DuckDB §0)."""

    column: str = "dimension"


class TransformCountVerticesParams(BaseModel):
    """Nombre de sommets de la géométrie → colonne attribut."""

    column: str = "vertexCount"


class TransformExtractSridParams(BaseModel):
    """SRID (code EPSG) du système de coordonnées courant du pipeline →
    colonne attribut constante.

    Le SRID est un état porté par le runtime du pipeline, pas un attribut de
    la géométrie elle-même : DuckDB spatial ne stocke aucun SRID sur le type
    GEOMETRY (vérifié empiriquement, design vague 1 transformers DuckDB
    §0)."""

    column: str = "srid"


class TransformSetSridParams(BaseModel):
    """Réassigne le SRID du pipeline SANS reprojeter les coordonnées — à
    utiliser quand les coordonnées sont correctes mais le SRID détecté à la
    lecture est faux.

    Pour reprojeter réellement les coordonnées, utiliser transform.reproject.
    Ne couvre pas le retrait de SRID (CoordinateSystemRemover de la matrice
    FME) : le SRID est un entier obligatoire dans ce runtime, jamais absent
    (design vague 1 transformers DuckDB §0)."""

    targetSrid: int = Field(..., gt=0)


class TransformReprojectAttributeParams(BaseModel):
    """Reprojette une paire de coordonnées portée par DEUX COLONNES ATTRIBUT
    (pas la géométrie de la feature) — distinct de transform.reproject qui
    reprojette la géométrie. Écrase xColumn/yColumn en place."""

    xColumn: str
    yColumn: str
    sourceCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")
    targetCrs: str = Field(..., pattern=r"^[A-Za-z]+:\d+$")


class TransformFormatCoordinatesParams(BaseModel):
    """Formate une colonne attribut numérique (coordonnée en degrés
    décimaux) : soit arrondie à une précision donnée (reste numérique), soit
    convertie en texte degrés/minutes/secondes (DMS, sans indicateur
    d'hémisphère — à concaténer séparément si besoin)."""

    sourceColumn: str
    targetColumn: str
    format: Literal["decimalDegrees", "dms"] = "decimalDegrees"
    precision: int = Field(4, ge=0, le=10)


class ReaderFileParams(BaseModel):
    """reader.file (design desktop-etl §3) : chemin local absolu, lu via
    ST_Read() (DuckDB spatial/GDAL) — jamais une collection. srid optionnel :
    si absent, détecté depuis le CRS du fichier (st_crs()), repli sur 4326
    si le fichier n'en porte aucun (même repli que table_info.srid or 4326
    pour reader.collection)."""

    path: str
    srid: int | None = None


class WriterFileParams(BaseModel):
    """writer.file (design desktop-etl §3) : chemin local absolu, écrit via
    COPY ... FORMAT GDAL DRIVER <driver> — n'importe quel driver vectoriel
    GDAL (GPKG par défaut, vérifié empiriquement ; GeoJSON aussi vérifié).
    Les drivers non vectoriels (ex. CSV) échouent à l'écriture d'une colonne
    géométrie — pas garanti par ce schéma, mais par COPY lui-même à
    l'exécution."""

    path: str
    driver: str = "GPKG"

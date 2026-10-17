# SPDX-License-Identifier: Apache-2.0
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel as _PydanticBaseModel
from pydantic import ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.analytics.aggregate import (
    METRIC_AGGS,
    AggregateRequestBody,
    UnknownAggregateField,
    _validate_p,
)
from app.configs.alert_condition import validate_condition_expr


class BaseModel(_PydanticBaseModel):
    """Base des documents de config : à l'ÉCRITURE (corps de requête, MCP), une
    clé inconnue est rejetée (422) au lieu d'être supprimée en silence
    (c08-002). À la RELECTURE d'une config stockée (repository, rollback,
    balayages cron), `context={"lenient": True}` la tolère : une clé retirée ou
    ajoutée depuis l'écriture ne doit jamais rendre une config illisible. Les
    bornes de valeur vivent dans app.configs.document_validation."""

    @model_validator(mode="before")
    @classmethod
    def _reject_unknown_keys(cls, data: Any, info: ValidationInfo) -> Any:
        if isinstance(data, dict) and not (info.context or {}).get("lenient"):
            known = set(cls.model_fields)
            for f in cls.model_fields.values():
                known |= {a for a in (f.alias, f.validation_alias) if isinstance(a, str)}
            if extra := sorted(str(k) for k in data if k not in known):
                raise ValueError(f"unknown keys: {', '.join(extra)}")
        return data


class DataSource(BaseModel):
    id: str
    type: str
    service: str
    layer: str
    # GAP-19 (SDK d'embedding) : une source de données peut référencer un
    # item "dataset" (app.configs.guest_access en a besoin pour résoudre la
    # portée d'un jeton de lien de partage) plutôt qu'une couche directe.
    # Champ additif, rétrocompatible — BuilderConfig est stocké en JSON
    # (ConfigRevision.data), aucune migration nécessaire.
    datasetId: str | None = None
    query: dict = Field(default_factory=dict)


class LayoutItem(BaseModel):
    id: str | None = None
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)
    layouts: dict[str, dict] | None = None
    visibleWhen: str | None = None
    # REV-285(h) : rang stable du widget parmi ceux de son type (nom accessible
    # « Table 2 »). Additif ; absent des configs antérieures (repli côté shell).
    ordinal: int | None = None


class Layout(BaseModel):
    type: Literal["grid"]
    breakpoints: dict = Field(default_factory=dict)
    items: list[LayoutItem] = Field(default_factory=list)


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # P10.01 : identifiant d'action conservé à l'aller-retour (retrait/édition individuels).
    id: str | None = None
    from_: str = Field(alias="from")
    event: str
    to: str
    action: str
    when: str | None = None
    payload: dict | None = None


class Page(BaseModel):
    id: str
    name: str
    layout: Layout
    onEnter: list[Message] = Field(default_factory=list)


class Variable(BaseModel):
    id: str
    name: str
    type: Literal["string", "number", "bool", "date", "record", "list"] = "string"
    initialValue: str | bool | float | dict | list | None = ""


class MapView(BaseModel):
    center: tuple[float, float]
    zoom: float
    pitch: float | None = None
    bearing: float | None = None


class BaseMap(BaseModel):
    style: str


class PopupField(BaseModel):
    name: str
    label: str | None = None


class PopupConfig(BaseModel):
    """Contenu du popup d'une couche (SP-24). `template` non vide l'emporte sur
    titleField/fields — un seul mode s'applique à la fois."""

    titleField: str | None = None
    fields: list[PopupField] | None = None
    template: str | None = None
    # SP-40 : champ « pièce jointe » de la collection listé dans le popup.
    attachmentField: str | None = None


class ClusterConfig(BaseModel):
    """ARC-01 : regroupement de points (MapLibre `cluster: true`) d'une couche `feature`."""

    radius: float | None = None
    maxZoom: float | None = None
    label: bool | None = None


class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck", "tiles3d"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None
    popup: PopupConfig | None = None
    symbology: dict | None = None
    # Lien vers la collection servie en tuiles par le cœur : c'est lui qui
    # donne au shell le schéma des champs (popup) et, plus tard, le domaine
    # des valeurs (symbologie SP-25).
    collectionId: str | None = None
    geometryKind: Literal["point", "line", "polygon"] | None = None
    pkColumn: str | None = None
    renderAs: Literal["fill", "circle", "line"] | None = None
    # REV-304 : champ date filtré par le contexte temps (widget carte).
    timeField: str | None = None
    cluster: ClusterConfig | None = None


class MapTerrain(BaseModel):
    tilesUrl: str
    encoding: Literal["terrarium"] = "terrarium"
    exaggeration: float | None = None


class MapTimePlayer(BaseModel):
    """ARC-09b : lecteur temps de l'éditeur de carte (pilote le filtre `datetime`
    des couches ayant `timeField`). Mêmes bornes que le widget `timePlayer`."""

    start: str  # AAAA-MM-JJ
    end: str
    stepDays: int = Field(1, ge=1, le=3660)
    windowDays: int = Field(7, ge=1, le=3660)
    intervalMs: int = Field(1000, ge=500, le=10000)
    windowIndex: int = Field(0, ge=0)


class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)
    terrain: MapTerrain | None = None
    timePlayer: MapTimePlayer | None = None


class DatasetColumnMeta(BaseModel):
    label: str | None = None
    description: str | None = None
    format: str | None = None  # libre (ex. "currency", "percent", "date"),
    # interprété côté widget consommateur


_METRIC_KEY = re.compile(r"^[a-z][A-Za-z0-9_]{0,63}$")
MAX_DATASET_METRICS = 50


class DatasetMetric(BaseModel):
    """REV-119 / GAP-25 : métrique nommée d'un dataset (field + agg, résolue en
    `AggregateMeasure` avant exécution ; pas de CEL libre : un seul moteur)."""

    field: str | None = None  # requis sauf agg == "count"
    agg: str
    p: float | None = None  # centile en %, uniquement agg == "percentile"
    label: str | None = None
    format: str | None = None  # libre, comme DatasetColumnMeta.format
    unit: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "DatasetMetric":
        if self.agg not in METRIC_AGGS:
            raise ValueError(f"unknown agg '{self.agg}'")
        if self.agg != "count" and not self.field:
            raise ValueError(f"agg '{self.agg}' requires a field")
        try:
            _validate_p(self.agg, self.p, "p")
        except UnknownAggregateField as exc:
            raise ValueError(exc.message) from exc
        return self


class DatasetCrossFilterLinkAttribute(BaseModel):
    mode: Literal["attribute"] = "attribute"
    targetDatasetId: str
    sourceField: str
    targetField: str


class DatasetCrossFilterLinkSpatial(BaseModel):
    mode: Literal["spatial"] = "spatial"
    targetDatasetId: str
    precision: Literal["bbox", "exact"] = "bbox"


DatasetCrossFilterLink = Annotated[
    DatasetCrossFilterLinkAttribute | DatasetCrossFilterLinkSpatial,
    Field(discriminator="mode"),
]


class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None  # requis si source == "collection"
    arcgisItemId: str | None = None  # requis si source == "arcgis" (SP-14k) : item "external"
    # moissonné en mode référence (SP-12d)
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None  # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False  # A29 : refetch auto sur déplacement carte (SP-14b)
    crossFilterLinks: list[DatasetCrossFilterLink] = Field(default_factory=list)  # SP-14n
    metrics: dict[str, DatasetMetric] = Field(default_factory=dict)  # REV-119
    sourcePipelineId: str | None = None  # SP-14o : pipeline qui alimente ce
    # dataset via writer.dataset, si créé par l'assistant de requête
    # visuelle plutôt qu'à la main ; référence validée dans
    # app.configs.dataset_validation, pas ici (un model_validator Pydantic
    # n'a pas accès à la Session/l'utilisateur courant).

    @field_validator("metrics")
    @classmethod
    def _check_metric_keys(cls, v: dict[str, DatasetMetric]) -> dict[str, DatasetMetric]:
        if len(v) > MAX_DATASET_METRICS:
            raise ValueError(f"at most {MAX_DATASET_METRICS} metrics")
        for key in v:
            if not _METRIC_KEY.match(key):
                raise ValueError(f"invalid metric key '{key}'")
        return v

    @model_validator(mode="after")
    def _require_source_id(self) -> "DatasetPayload":
        if self.source == "collection" and self.collectionId is None:
            raise ValueError("collection source requires collectionId")
        if self.source == "arcgis" and self.arcgisItemId is None:
            raise ValueError("arcgis source requires arcgisItemId")
        if self.source == "collection" and self.arcgisItemId is not None:
            raise ValueError("collection source must not set arcgisItemId")
        if self.source == "arcgis" and self.collectionId is not None:
            raise ValueError("arcgis source must not set collectionId")
        return self


class BookmarkTimeRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class BookmarkCrossFilterEntry(BaseModel):
    field: str
    # The shell's CrossFilterValue mirror type (AnalyticsContext.tsx) also
    # allows a {from, to} range shape — written by the built-in "Curseur"
    # range-slider widget (sliderFilter.tsx). Reuse BookmarkTimeRange rather
    # than inventing a second range type.
    value: str | list[str] | BookmarkTimeRange
    originSourceId: str


class BookmarkPayload(BaseModel):
    appId: str
    pageId: str
    timeRange: BookmarkTimeRange | None = None
    extent: tuple[float, float, float, float] | None = None
    crossFilter: dict[str, BookmarkCrossFilterEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_non_empty_page_id(self) -> "BookmarkPayload":
        if not self.pageId.strip():
            raise ValueError("bookmark pageId must not be empty")
        return self


class PipelineNode(BaseModel):
    id: str
    kind: Literal["reader", "transform", "writer"]
    op: str
    x: float = 0
    y: float = 0  # idiome LayoutItem, inutilisé tant qu'il n'y a pas de
    # canvas (SP-15b) — posé maintenant pour ne pas migrer
    # le schéma plus tard (design SP-15a §4.1)
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None  # CEL, routage conditionnel — accepté mais non
    # interprété par le compilateur avant Phase 3/4
    role: Literal["primary", "secondary"] | None = None  # None ≡ "primary" ;
    # "secondary" = seconde entrée d'un op binaire (SP-15g §2.2), sans
    # effet sur tout autre op (rejeté à la validation, app.pipelines.
    # config_validation)


class PipelineCanvasNote(BaseModel):
    id: str
    label: str
    x: float = 0
    y: float = 0
    width: float = 200
    height: float = 120


class PipelineRefreshPolicy(BaseModel):
    enabled: bool = False
    cron: str
    # AUD-084 : fuseau IANA d'interprétation du cron (06:00 « heure de Paris »).
    timezone: str = "UTC"

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, v: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"fuseau horaire inconnu : {v!r}") from exc
        return v

    @model_validator(mode="after")
    def _require_valid_cron(self) -> "PipelineRefreshPolicy":
        import croniter

        # Le contrôle des 5 champs (j06b-012) vit dans validate_pipeline_payload
        # (écriture seulement) : ici il rendrait illisible toute config déjà
        # enregistrée avec un cron à 6 champs.
        if not croniter.croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")
        return self


class PipelineParameter(BaseModel):
    """Paramètre de run publié (ARC-K2/F3) : saisi au lancement, référencé par
    `{{param.nom}}` dans les params de nœud (cf. app.configs.pipeline_params).
    Valeurs conservées en clair (historique des runs, audit) : pas de secrets ici."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["string", "number", "integer", "boolean", "date"] = "string"
    default: Any | None = None
    required: bool = False

    @model_validator(mode="after")
    def _default_matches_type(self) -> "PipelineParameter":
        if self.default is not None:
            from app.configs.pipeline_params import PipelineParamError, coerce_value

            try:
                coerce_value(self.name, self.type, self.default)
            except PipelineParamError as exc:
                raise ValueError(f"default invalide : {exc}") from exc
        return self


# Writers à effet de bord EXTERNE et non idempotent (un message par ligne, hors transaction
# du run, irréversible) : un retry/une reprise les rejouerait depuis la ligne 1 (revue finale
# FME, I1). Les autres writers externes sont rejouables car idempotents : postgres
# update/delete (WHERE borné aux clés), ftp/topojson/file/export (écrasement du même chemin).
# Tout nouveau writer doit être classé : test_every_writer_is_classified_for_replay.
EXTERNAL_EFFECT_WRITER_OPS = frozenset(
    {
        "writer.email",
        "writer.slack",
        "writer.trello",
        "writer.servicebus",
        "writer.azurequeue",
        "writer.sns",
        "writer.kinesis",
        "writer.rabbitmq",
    }
)


class PipelineRetryPolicy(BaseModel):
    """Politique de reprise (ARC-K2/F5) : `max` reprises automatiques après un
    échec (0 = aucune, mais les points de reprise restent écrits pour une
    reprise manuelle), délai fixe ou exponentiel (`delaySeconds` * 2^(n-1))."""

    max: int = Field(0, ge=0, le=10)
    backoff: Literal["fixed", "exponential"] = "exponential"
    delaySeconds: int = Field(30, ge=1, le=3600)


class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)
    refreshPolicy: PipelineRefreshPolicy | None = None
    notes: list[PipelineCanvasNote] = Field(default_factory=list)
    parameters: list[PipelineParameter] = Field(default_factory=list)
    retry: PipelineRetryPolicy | None = None

    @model_validator(mode="after")
    def _validate_graph(self) -> "PipelinePayload":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("pipeline node ids must be unique")
        id_set = set(ids)
        for edge in self.edges:
            if edge.from_ not in id_set:
                raise ValueError(f"edge references unknown node '{edge.from_}'")
            if edge.to not in id_set:
                raise ValueError(f"edge references unknown node '{edge.to}'")
        if not any(n.kind == "reader" for n in self.nodes):
            raise ValueError("pipeline requires at least one reader node")
        if not any(n.kind == "writer" for n in self.nodes):
            raise ValueError("pipeline requires at least one writer node")
        names = [p.name for p in self.parameters]
        if len(names) != len(set(names)):
            raise ValueError("pipeline parameter names must be unique")
        from app.configs.pipeline_params import misplaced_param_refs, param_refs

        for n in self.nodes:
            bad = misplaced_param_refs(n.params, op=n.op)
            if bad:
                raise ValueError(
                    f"nœud '{n.id}' : {{{{param.x}}}} interdit dans le(s) champ(s) "
                    f"{', '.join(sorted(bad))} (risque d'injection) ; réservé aux expressions "
                    "(expr, metrics, *Expr) et aux champs de donnée (collectionId, path…). "
                    "La requête native d'un connecteur ne peut pas être paramétrée."
                )
        unknown = set().union(*(param_refs(n.params) for n in self.nodes)) - set(names)
        if unknown:
            raise ValueError(f"unknown parameter reference(s): {', '.join(sorted(unknown))}")
        if self.retry is not None and self.retry.max > 0 and self.append_writers():
            raise ValueError(
                "reprise automatique (retry.max > 0) impossible avec un writer à effet "
                f"externe non idempotent ({', '.join(self.append_writers())}) : un rejeu "
                "renverrait des messages déjà partis"
            )
        return self

    def append_writers(self) -> list[str]:
        """Ids des writers NON REJOUABLES, donc incompatibles avec un retry/une reprise :
        writers à effet externe irréversible (`EXTERNAL_EFFECT_WRITER_OPS`). Les writers
        collection/dataset, même en `append`, écrivent dans la transaction du run, annulée
        à l'échec : rejouables (AUD-083)."""
        return [
            n.id for n in self.nodes if n.kind == "writer" and n.op in EXTERNAL_EFFECT_WRITER_OPS
        ]


class AlertCondition(BaseModel):
    # Bounded DuckDB scalar SQL expression, binding `value` — see
    # app.configs.alert_condition (design SP-16b §4: no CEL engine exists
    # server-side, only client-side cel-js for visibleWhen/computed
    # columns).
    expr: str

    @model_validator(mode="after")
    def _require_valid_expr(self) -> "AlertCondition":
        import duckdb

        conn = duckdb.connect(":memory:")
        try:
            validate_condition_expr(conn, self.expr)
        except Exception as exc:
            raise ValueError(f"invalid condition expression: {exc}") from exc
        finally:
            conn.close()
        return self


class AlertChannelWebhook(BaseModel):
    kind: Literal["webhook"] = "webhook"
    url: str
    # P20.04 : secret `bearer_token` du coffre servant de clé HMAC-SHA256 ;
    # l'en-tête X-GeoStudio-Signature permet au récepteur d'authentifier
    # l'émetteur. Absent = livraison non signée (comportement historique).
    signingSecretName: str | None = None


class AlertChannelEmail(BaseModel):
    kind: Literal["email"] = "email"
    to: str
    smtpSecretName: str


AlertChannel = Annotated[
    AlertChannelWebhook | AlertChannelEmail,
    Field(discriminator="kind"),
]


class AlertRulePayload(BaseModel):
    datasetItemId: str
    query: AggregateRequestBody
    condition: AlertCondition
    refreshPolicy: PipelineRefreshPolicy
    channels: list[AlertChannel] = Field(default_factory=list)
    messageTemplate: str = "Alert {ruleName}: value={value} ({state})"

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "AlertRulePayload":
        if not self.channels:
            raise ValueError("alert rule requires at least one channel")
        return self

    @model_validator(mode="after")
    def _require_valid_message_template(self) -> "AlertRulePayload":
        # Must call .format(...) with the exact same keyword shape as
        # app.alerts.jobs._render_message (ruleName/value/state/
        # datasetName) — app.configs sits BELOW app.alerts in the layers
        # contract, so this can't import _render_message to guarantee
        # agreement; keep the two in sync by hand if either one's
        # placeholder set changes. Rejecting an unknown placeholder or a
        # malformed brace here (422 at save time) is what stops a rule from
        # being saved successfully but then failing every single
        # notification attempt forever.
        try:
            self.messageTemplate.format(ruleName="x", value=1.0, state="firing", datasetName="y")
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"invalid messageTemplate: {exc}") from exc
        return self

    @model_validator(mode="after")
    def _require_single_scalar_query(self) -> "AlertRulePayload":
        # v1 scope (design SP-16b §1 non-buts, §2): one scalar per rule, no
        # per-group/multi-series alerting.
        if self.query.groupBy:
            raise ValueError(
                "alert query must not use groupBy (v1 supports a single scalar per rule)"
            )
        if self.query.split is not None:
            raise ValueError(
                "alert query must not use split (v1 supports a single scalar per rule)"
            )
        if self.query.bucket is not None or self.query.bins is not None:
            raise ValueError(
                "alert query must not use bucket/bins (v1 supports a single scalar per rule)"
            )
        if self.query.measures is not None and len(self.query.measures) > 1:
            raise ValueError(
                "alert query must have at most one measure (v1 supports a single scalar per rule)"
            )
        # `p` (le centile) fait partie de la validité d'une requête d'agrégat,
        # mais _validate_p n'est appelé qu'à l'exécution (par
        # _validate_fields, qui a besoin du schéma de la collection). Le
        # rejouer ici — sur la requête simple ET sur l'unique mesure — est ce
        # qui empêche une règle `percentile` sans `p` de s'enregistrer puis
        # d'échouer en 400 à chaque tick de son cron, pour toujours (même
        # raison d'être que _require_valid_message_template ci-dessus).
        try:
            _validate_p(self.query.agg, self.query.p, "p")
            for i, m in enumerate(self.query.measures or []):
                _validate_p(m.agg, m.p, f"measures[{i}].p")
        except UnknownAggregateField as exc:
            raise ValueError(f"invalid alert query: {exc.field}: {exc.message}") from exc
        return self


class ReportRetry(BaseModel):
    """AUD-058 : un rendu en erreur est rejoué (nouveau run) avant le prochain cron, puis
    la panne est notifiée une seule fois, après le dernier essai."""

    maxAttempts: int = Field(default=2, ge=1, le=5)  # essais au total, premier compris
    delayMinutes: int = Field(default=15, ge=1, le=1440)


class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    # AUD-058 : le rapport n'était que PDF.
    format: Literal["pdf", "png"] = "pdf"
    retry: ReportRetry | None = None
    refreshPolicy: (
        PipelineRefreshPolicy  # réutilisé tel quel, même forme que la planification pipeline/alerte
    )
    channels: list[AlertChannel] = Field(
        default_factory=list
    )  # réutilisé tel quel depuis AlertRule (SP-16b)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self


class Tileset3DPayload(BaseModel):
    sourceKey: str
    tilesetJsonPath: str
    totalBytes: int
    entryCount: int


class Terrain3DPayload(BaseModel):
    sourceKey: str  # clé S3 du COG converti — jamais celle de l'upload brut
    originalFilename: str


class AtlasField(BaseModel):
    label: str = Field(max_length=100)
    # Gabarit CEL `${record.champ}` (même syntaxe que les popups de carte).
    template: str = Field(max_length=500)


class AtlasConfig(BaseModel):
    """ARC-30 : atlas = une page PDF par entité de la source `dataSourceId`.
    Les champs sont des gabarits CEL évalués par entité côté shell (rendu par
    le worker d'export). `maxPages` borne le nombre de pages d'un rendu."""

    dataSourceId: str = Field(max_length=200)
    titleTemplate: str | None = Field(default=None, max_length=500)
    fields: list[AtlasField] = Field(default_factory=list, max_length=50)
    maxPages: int = Field(default=50, ge=1, le=200)
    # AUD-057 : tri reproductible (`champ` ou `-champ` pour décroissant) ; absent = ordre du cœur.
    sortBy: str | None = Field(default=None, max_length=128, pattern=r"^-?[A-Za-z_][A-Za-z0-9_]*$")


class PrintLayout(BaseModel):
    pageSize: Literal["a4", "a3"] = "a4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    title: str | None = None
    showLegend: bool = True
    cartouche: str | None = None
    # ARC-16 : éléments de gabarit. Défaut False — les exports enregistrés avant
    # ne changent pas. `logo` est un data URI (jamais une URL : le navigateur du
    # worker n'a alors aucune requête sortante à faire, donc pas de SSRF).
    scaleBar: bool = False
    northArrow: bool = False
    # AUD-058 : résolution de rendu (la carte WebGL était figée à 96 dpi). Plafonnée côté
    # worker (côté long <= 8192 px).
    dpi: Literal[96, 150, 300, 600] = 150
    freeText: str | None = Field(default=None, max_length=2000)
    logo: str | None = Field(default=None, max_length=400_000)
    # ARC-30 : mise en page en série (atlas). Absent = export d'une seule page.
    atlas: AtlasConfig | None = None

    @field_validator("logo")
    @classmethod
    def _logo_is_inline_image(cls, v: str | None) -> str | None:
        if v is not None and not re.match(
            r"^data:image/(png|jpeg|svg\+xml|webp);base64,[A-Za-z0-9+/=]+$", v
        ):
            raise ValueError("logo must be a base64 data URI (png, jpeg, svg or webp)")
        return v


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal[
        "app",
        "dashboard",
        "map",
        "site",
        "dataset",
        "bookmark",
        "pipeline",
        "alert",
        "report",
        "tileset3d",
        "terrain3d",
    ]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout | None = None
    messages: list[Message] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    navigationMode: Literal["tabs", "story"] = "tabs"
    interactions: Literal["auto", "manual"] | None = None
    variables: list[Variable] = Field(default_factory=list)
    map: MapConfig | None = None
    dataset: DatasetPayload | None = None
    bookmark: BookmarkPayload | None = None
    pipeline: PipelinePayload | None = None
    alert: AlertRulePayload | None = None
    report: ReportSchedulePayload | None = None
    tileset3d: Tileset3DPayload | None = None
    terrain3d: Terrain3DPayload | None = None
    printLayout: PrintLayout | None = None

    @model_validator(mode="after")
    def _require_kind_payload(self) -> "BuilderConfig":
        if self.kind in ("app", "dashboard", "site") and self.layout is None:
            raise ValueError(f"{self.kind} config requires a layout")
        if self.kind == "map" and self.map is None:
            raise ValueError("map config requires a map")
        if self.kind == "dataset" and self.dataset is None:
            raise ValueError("dataset config requires a dataset payload")
        if self.kind == "bookmark" and self.bookmark is None:
            raise ValueError("bookmark config requires a bookmark payload")
        if self.kind == "pipeline" and self.pipeline is None:
            raise ValueError("pipeline config requires a pipeline payload")
        if self.kind == "alert" and self.alert is None:
            raise ValueError("alert config requires an alert payload")
        if self.kind == "report" and self.report is None:
            raise ValueError("report config requires a report payload")
        if self.kind == "tileset3d" and self.tileset3d is None:
            raise ValueError("tileset3d config requires a tileset3d payload")
        if self.kind == "terrain3d" and self.terrain3d is None:
            raise ValueError("terrain3d config requires a terrain3d payload")
        return self


def app_config_json_schema() -> dict:
    """Schéma JSON de BuilderConfig — source unique, consommée par
    GET /schemas/app-config (schemas_routes.py) et la ressource MCP
    schema://app-config (mcp/tools/__init__.py). Les deux existaient
    jusqu'ici en deux implémentations parallèles qui rappelaient chacune
    model_json_schema() indépendamment (GAP-38, SP-42)."""
    return BuilderConfig.model_json_schema()

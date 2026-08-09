# SPDX-License-Identifier: Apache-2.0
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.analytics.aggregate import AggregateRequestBody
from app.configs.alert_condition import validate_condition_expr


class DataSource(BaseModel):
    id: str
    type: str
    service: str
    layer: str
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


class Layout(BaseModel):
    type: Literal["grid"]
    breakpoints: dict = Field(default_factory=dict)
    items: list[LayoutItem] = Field(default_factory=list)


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

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


class BaseMap(BaseModel):
    style: str


class MapLayer(BaseModel):
    id: str
    title: str
    visible: bool = True
    kind: Literal["vector", "raster", "feature", "deck"]
    tilesUrl: str | None = None
    sourceLayer: str | None = None
    url: str | None = None
    opacity: float | None = None
    deckType: str | None = None
    dataUrl: str | None = None
    paint: dict | None = None
    props: dict | None = None


class MapConfig(BaseModel):
    basemap: BaseMap
    view: MapView
    layers: list[MapLayer] = Field(default_factory=list)


class DatasetColumnMeta(BaseModel):
    label: str | None = None
    description: str | None = None
    format: str | None = None  # libre (ex. "currency", "percent", "date"),
                                 # interprété côté widget consommateur


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
    collectionId: str | None = None    # requis si source == "collection"
    arcgisItemId: str | None = None    # requis si source == "arcgis" (SP-14k) : item "external"
                                        # moissonné en mode référence (SP-12d)
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte (SP-14b)
    crossFilterLinks: list[DatasetCrossFilterLink] = Field(default_factory=list)  # SP-14n

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
    x: int = 0
    y: int = 0                    # idiome LayoutItem, inutilisé tant qu'il n'y a pas de
                                   # canvas (SP-15b) — posé maintenant pour ne pas migrer
                                   # le schéma plus tard (design SP-15a §4.1)
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None       # CEL, routage conditionnel — accepté mais non
                                   # interprété par le compilateur avant Phase 3/4
    role: Literal["primary", "secondary"] | None = None  # None ≡ "primary" ;
        # "secondary" = seconde entrée d'un op binaire (SP-15g §2.2), sans
        # effet sur tout autre op (rejeté à la validation, app.pipelines.
        # config_validation)


class PipelineRefreshPolicy(BaseModel):
    enabled: bool = False
    cron: str

    @model_validator(mode="after")
    def _require_valid_cron(self) -> "PipelineRefreshPolicy":
        import croniter
        if not croniter.croniter.is_valid(self.cron):
            raise ValueError(f"invalid cron expression: {self.cron!r}")
        return self


class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)
    refreshPolicy: PipelineRefreshPolicy | None = None

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
        return self


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
            raise ValueError("alert query must not use groupBy (v1 supports a single scalar per rule)")
        if self.query.split is not None:
            raise ValueError("alert query must not use split (v1 supports a single scalar per rule)")
        if self.query.bucket is not None or self.query.bins is not None:
            raise ValueError("alert query must not use bucket/bins (v1 supports a single scalar per rule)")
        if self.query.measures is not None and len(self.query.measures) > 1:
            raise ValueError("alert query must have at most one measure (v1 supports a single scalar per rule)")
        return self


class ReportSchedulePayload(BaseModel):
    bookmarkItemId: str
    refreshPolicy: PipelineRefreshPolicy  # réutilisé tel quel, même forme que la planification pipeline/alerte
    channels: list[AlertChannel] = Field(default_factory=list)  # réutilisé tel quel depuis AlertRule (SP-16b)

    @model_validator(mode="after")
    def _require_at_least_one_channel(self) -> "ReportSchedulePayload":
        if not self.channels:
            raise ValueError("report schedule requires at least one channel")
        return self


class PrintLayout(BaseModel):
    pageSize: Literal["a4", "a3"] = "a4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    title: str | None = None
    showLegend: bool = True
    showScaleBar: bool = True
    showNorthArrow: bool = False
    cartouche: str | None = None


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert", "report"]
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
        return self

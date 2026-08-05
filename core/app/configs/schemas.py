# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None    # requis si source == "collection"
    arcgisItemId: str | None = None    # requis si source == "arcgis" (SP-14k) : item "external"
                                        # moissonné en mode référence (SP-12d)
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte (SP-14b)

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


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark"]
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
        return self

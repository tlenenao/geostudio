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


class Layout(BaseModel):
    type: Literal["grid"]
    breakpoints: dict = Field(default_factory=dict)
    items: list[LayoutItem] = Field(default_factory=list)


class Page(BaseModel):
    id: str
    name: str
    layout: Layout


class Variable(BaseModel):
    id: str
    name: str
    initialValue: str


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    event: str
    to: str
    action: str


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


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout | None = None
    messages: list[Message] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    variables: list[Variable] = Field(default_factory=list)
    map: MapConfig | None = None

    @model_validator(mode="after")
    def _require_kind_payload(self) -> "BuilderConfig":
        if self.kind in ("app", "dashboard") and self.layout is None:
            raise ValueError(f"{self.kind} config requires a layout")
        if self.kind == "map" and self.map is None:
            raise ValueError("map config requires a map")
        return self

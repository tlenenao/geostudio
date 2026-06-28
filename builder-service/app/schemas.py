from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataSource(BaseModel):
    id: str
    type: str
    service: str
    layer: str
    query: dict = Field(default_factory=dict)


class LayoutItem(BaseModel):
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)


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


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout
    messages: list[Message] = Field(default_factory=list)

from pydantic import BaseModel, Field


class ItemRead(BaseModel):
    pk: str
    resourceType: str
    title: str
    abstract: str
    owner: str
    thumbnailUrl: str | None
    date: str
    configId: str | None
    isPublished: bool


class ItemPage(BaseModel):
    items: list[ItemRead]
    total: int
    page: int
    pageSize: int


class ItemUpdatePatch(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    isPublished: bool | None = Field(default=None)

from pydantic import BaseModel, Field


class CollectionCreate(BaseModel):
    tableName: str = Field(min_length=1, max_length=63)
    title: str | None = None
    description: str = ""
    isPublic: bool = False


class CollectionPatch(BaseModel):
    title: str | None = None
    description: str | None = None
    isPublic: bool | None = None
    editable: bool | None = None

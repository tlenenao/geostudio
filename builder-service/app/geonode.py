import uuid
from typing import Protocol


class ItemClient(Protocol):
    def create_item(self, title: str, type: str, owner: str) -> str:
        """Create a shareable item in the content backend, returning its id."""
        ...


class StubItemClient:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_item(self, title: str, type: str, owner: str) -> str:
        self.created.append({"title": title, "type": type, "owner": owner})
        return "item-" + uuid.uuid4().hex

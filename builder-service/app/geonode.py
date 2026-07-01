import uuid
from typing import Protocol

import httpx


class ItemClient(Protocol):
    def create_item(self, title: str, type: str, owner: str) -> str:
        """Create a shareable item in the content backend, returning its id."""
        ...

    def delete_item(self, item_id: str) -> None:
        """Delete the linked item in the content backend."""
        ...


class StubItemClient:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self.deleted: list[str] = []

    def create_item(self, title: str, type: str, owner: str) -> str:
        self.created.append({"title": title, "type": type, "owner": owner})
        return "item-" + uuid.uuid4().hex

    def delete_item(self, item_id: str) -> None:
        self.deleted.append(item_id)


class GeoNodeItemClient:
    def __init__(
        self, base_url: str, token: str, http: httpx.Client | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = http or httpx.Client()

    def create_item(self, title: str, type: str, owner: str) -> str:
        response = self._http.post(
            f"{self._base_url}/api/v2/resources",
            json={"title": title, "resource_type": type, "owner": owner},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        return str(response.json()["resource"]["pk"])

    def delete_item(self, item_id: str) -> None:
        response = self._http.delete(
            f"{self._base_url}/api/v2/resources/{item_id}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()

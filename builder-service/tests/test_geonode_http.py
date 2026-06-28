import httpx

from app.geonode import GeoNodeItemClient, ItemClient


def test_geonode_client_posts_and_returns_pk():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = httpx.Request(
            request.method, request.url, content=request.content
        ).content
        return httpx.Response(201, json={"resource": {"pk": 42}})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client: ItemClient = GeoNodeItemClient(
        base_url="https://geonode.example", token="t0ken", http=http
    )

    item_id = client.create_item(title="My App", type="app", owner="alice")

    assert item_id == "42"
    assert captured["url"] == "https://geonode.example/api/v2/resources"
    assert captured["auth"] == "Bearer t0ken"

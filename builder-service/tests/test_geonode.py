from app.geonode import ItemClient, StubItemClient


def test_stub_creates_item_and_records_call():
    client: ItemClient = StubItemClient()
    item_id = client.create_item(title="My App", type="app", owner="alice")
    assert item_id.startswith("item-")
    assert client.created == [{"title": "My App", "type": "app", "owner": "alice"}]

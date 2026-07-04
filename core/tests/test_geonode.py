from app.geonode import ItemClient, StubItemClient


def test_stub_creates_item_and_records_call():
    client: ItemClient = StubItemClient()
    item_id = client.create_item(title="My App", type="app", owner="alice")
    assert item_id.startswith("item-")
    assert client.created == [{"title": "My App", "type": "app", "owner": "alice"}]


def test_stub_delete_item_records_call():
    client = StubItemClient()
    item_id = client.create_item(title="X", type="app", owner="alice")
    client.delete_item(item_id)
    assert client.deleted == [item_id]

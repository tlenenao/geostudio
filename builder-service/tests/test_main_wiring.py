from app.main import create_app
from app import routes
from app.geonode import GeoNodeItemClient, StubItemClient


def test_create_app_wires_real_geonode_client_when_env_set(monkeypatch):
    monkeypatch.setenv("GEONODE_BASE_URL", "https://geonode.example")
    monkeypatch.setenv("GEONODE_TOKEN", "t0ken")
    app = create_app()
    provider = app.dependency_overrides[routes.get_item_client]
    assert isinstance(provider(), GeoNodeItemClient)


def test_create_app_falls_back_to_stub_when_env_absent(monkeypatch):
    monkeypatch.delenv("GEONODE_BASE_URL", raising=False)
    monkeypatch.delenv("GEONODE_TOKEN", raising=False)
    app = create_app()
    # No override registered for the item client -> the route default (stub) is used.
    assert routes.get_item_client not in app.dependency_overrides
    assert isinstance(routes.get_item_client(), StubItemClient)

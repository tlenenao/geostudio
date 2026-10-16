# SPDX-License-Identifier: Apache-2.0
"""REV-359 : tuiles 3D, terrain et icônes lisibles par l'anonyme sur contenu public,
jamais sur contenu privé (le 401 devient 404 « introuvable », jamais une fuite)."""

import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient
from pytest_httpserver import HTTPServer
from sqlalchemy import select

from app import db
from app.auth.dependency import get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.models import ConfigRevision
from app.configs.schemas import BuilderConfig, Terrain3DPayload
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.items import repository as items_repo
from app.main import create_app
from app.mapicons import repository as icons_repo
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user


class _S3:
    def get_object(self, Bucket, Key):  # noqa: N803
        if Key != "k/icon.png":
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")

        class _B:
            def read(self):
                return b"PNG"

        return {"Body": _B()}


@pytest.fixture()
def env(monkeypatch, httpserver: HTTPServer):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    ids = {}
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ids["tenant"] = tenant.id
        alice = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        for name, public in (("pub", True), ("priv", False)):
            item = items_repo.create_item(
                s, tenant_id=tenant.id, owner_id=alice.id, resource_type="terrain3d", title=name
            )
            configs_repo.create_config(
                s,
                BuilderConfig(
                    kind="terrain3d",
                    terrain3d=Terrain3DPayload(sourceKey="k/dem.tif", originalFilename="d.tif"),
                ),
                item_id=item.id,
                tenant_id=tenant.id,
            )
            if public:
                items_repo.set_is_public(s, tenant_id=tenant.id, item_id=item.id, is_public=True)
            ids[name] = item.id
        # une icône citée seulement par l'item public ; une autre jamais citée
        for name in ("used", "unused"):
            icon = icons_repo.create_icon(
                s,
                tenant_id=tenant.id,
                created_by=alice.id,
                title=name,
                category="c",
                s3_key="k/icon.png",
                content_type="image/png",
            )
            ids[name] = icon.id
        pub_cfg = configs_repo.get_config_by_item(s, ids["pub"])
        rev = s.scalars(select(ConfigRevision).where(ConfigRevision.config_id == pub_cfg.id)).one()
        rev.data = {**rev.data, "uses": ids["used"]}
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user_optional] = lambda: None
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: _S3()
    app.dependency_overrides[terrain3d_routes.get_titiler_url] = lambda: httpserver.url_for("")
    httpserver.expect_request("/cog/tiles/0/0/0.png").respond_with_data(
        b"tile", content_type="image/png"
    )
    return TestClient(app), ids


def test_anonymous_terrain_tile_of_public_item_is_served(env):
    client, ids = env
    r = client.get(f"/v1/terrain3d/{ids['pub']}/tiles/0/0/0.png")
    assert r.status_code == 200


def test_anonymous_terrain_tile_of_private_item_is_404(env):
    client, ids = env
    assert client.get(f"/v1/terrain3d/{ids['priv']}/tiles/0/0/0.png").status_code == 404


def test_anonymous_tileset_of_private_item_is_404_not_401(env):
    client, ids = env
    assert client.get(f"/v1/tileset3d/{ids['priv']}/tileset.json").status_code == 404


def test_anonymous_tileset_of_public_item_passes_the_auth_gate(env):
    # l'item de test porte une config terrain3d : « tileset not found » prouve
    # que la porte d'accès (404 « item not found ») est franchie sans 401.
    client, ids = env
    r = client.get(f"/v1/tileset3d/{ids['pub']}/tileset.json")
    assert r.status_code == 404
    assert "tileset not found" in r.text


def test_anonymous_icon_used_by_public_item_is_served(env):
    client, ids = env
    r = client.get(f"/v1/map-icons/{ids['used']}/file")
    assert r.status_code == 200 and r.content == b"PNG"


def test_anonymous_icon_not_referenced_by_public_item_is_404(env):
    client, ids = env
    assert client.get(f"/v1/map-icons/{ids['unused']}/file").status_code == 404


def _as_guest(client, ids, *allowed):
    from app.configs.guest_access import GuestActor, get_share_link_actor

    guest = GuestActor(
        tenant_id=ids["tenant"],
        item_id=allowed[0],
        share_link_id="l",
        created_by="u",
        allowed_item_ids=frozenset(allowed),
        allowed_collection_ids=frozenset(),
    )
    client.app.dependency_overrides[get_share_link_actor] = lambda: guest


def test_guest_token_reads_only_icons_of_the_shared_resource(env):
    # REV-367 b : le jeton invité ne lit pas « toute icône du tenant ».
    client, ids = env
    _as_guest(client, ids, ids["pub"])
    assert client.get(f"/v1/map-icons/{ids['used']}/file").status_code == 200
    assert client.get(f"/v1/map-icons/{ids['unused']}/file").status_code == 404
    _as_guest(client, ids, ids["priv"])  # item partagé qui ne cite pas l'icône
    assert client.get(f"/v1/map-icons/{ids['used']}/file").status_code == 404

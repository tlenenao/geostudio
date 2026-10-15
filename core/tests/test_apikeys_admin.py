# SPDX-License-Identifier: Apache-2.0
"""REV-366 : un admin liste/révoque les clés d'API d'un autre compte ; la rétrogradation de rôle
révoque les clés."""

from app.roles.repository import ensure_built_in_roles
from tests.test_secrets_routes import _as, env  # noqa: F401


def _make_key(client, name="agent"):
    r = client.post("/v1/api-keys", json={"name": name, "expiresInDays": 30})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_admin_lists_and_revokes_another_users_key(env):  # noqa: F811
    app, client, _S, admin, regular = env
    _as(app, regular)
    key_id = _make_key(client)
    _as(app, admin)
    listed = client.get("/v1/admin/api-keys", params={"user": regular.id})
    assert listed.status_code == 200 and [k["id"] for k in listed.json()] == [key_id]
    # la liste personnelle de l'admin ne contient pas la clé d'autrui
    assert client.get("/v1/api-keys").json() == []
    revoked = client.delete(f"/v1/admin/api-keys/{key_id}")
    assert revoked.status_code == 200 and revoked.json()["revokedAt"] is not None
    assert client.delete("/v1/admin/api-keys/unknown").status_code == 404


def test_non_admin_cannot_use_admin_api_key_routes(env):  # noqa: F811
    app, client, _S, admin, regular = env
    _as(app, admin)
    key_id = _make_key(client)
    _as(app, regular)
    assert client.get("/v1/admin/api-keys", params={"user": admin.id}).status_code == 403
    assert client.delete(f"/v1/admin/api-keys/{key_id}").status_code == 403
    # et la route personnelle ne permet toujours pas de révoquer la clé d'autrui
    assert client.delete(f"/v1/api-keys/{key_id}").status_code == 404


def test_demotion_revokes_the_users_keys(env):  # noqa: F811
    app, client, Session, admin, regular = env
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=regular.tenant_id)
        creator_id, reader_id = roles["creator"].id, roles["reader"].id
    _as(app, admin)
    assert client.patch(f"/v1/users/{regular.id}", json={"roleId": creator_id}).status_code == 200
    _as(app, regular)
    key_id = _make_key(client)
    _as(app, admin)
    # promotion lecteur -> créateur : les clés restent actives
    assert (
        client.get("/v1/admin/api-keys", params={"user": regular.id}).json()[0]["revokedAt"] is None
    )
    assert client.patch(f"/v1/users/{regular.id}", json={"roleId": reader_id}).status_code == 200
    keys = client.get("/v1/admin/api-keys", params={"user": regular.id}).json()
    assert [k["id"] for k in keys] == [key_id] and keys[0]["revokedAt"] is not None

# SPDX-License-Identifier: Apache-2.0
"""GET /v1/collections/{id}/profile (REV-117) — mêmes fixtures que /aggregate."""

from shapely.geometry import Point

from tests.test_features_aggregate_routes import (  # noqa: F401
    _as,
    _register,
    _write_partition,
    env,
)


def _rows(n=2):
    return [
        {
            "id": i,
            "region": "Nord",
            "pop": 10 * i,
            "_op": "insert",
            "_lsn": 1,
            "_ts": 1.0,
            "geometry": Point(i, i),
        }
        for i in range(1, n + 1)
    ]


def test_profile_returns_columns_and_geometry(env):  # noqa: F811
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=col["id"], rows=_rows())

    response = client.get(f"/v1/collections/{col['id']}/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["rowCount"] == 2 and body["pending"] is False and body["asOf"]
    cols = {c["name"]: c for c in body["columns"]}
    assert cols["pop"]["max"] == 20.0
    assert cols["region"]["topValues"] == [{"value": "Nord", "count": 2}]
    assert body["geometry"]["bbox"] == [1.0, 1.0, 2.0, 2.0]


def test_profile_is_pending_when_lake_is_empty(env):  # noqa: F811
    app, client, admin, _r, _tmp, _tenant_id = env
    col = _register(app, client, admin)
    body = client.get(f"/v1/collections/{col['id']}/profile").json()
    assert body["pending"] is True and body["rowCount"] == 0 and body["columns"] == []


def test_profile_on_private_collection_by_non_owner_returns_404(env):  # noqa: F811
    app, client, admin, regular, _tmp, _tenant_id = env
    col = _register(app, client, admin, public=False)
    _as(app, regular)
    assert client.get(f"/v1/collections/{col['id']}/profile").status_code == 404


def test_profile_masks_sensitive_field_without_privilege(env):  # noqa: F811
    app, client, admin, regular, tmp_path, tenant_id = env
    col = _register(app, client, admin, public=True)
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=col["id"], rows=_rows())
    client.patch(f"/v1/collections/{col['id']}", json={"sensitiveFields": ["pop"]})

    _as(app, regular)
    masked = client.get(f"/v1/collections/{col['id']}/profile").json()
    assert "pop" not in {c["name"] for c in masked["columns"]}

    _as(app, admin)  # data.view_sensitive : non masqué
    full = client.get(f"/v1/collections/{col['id']}/profile").json()
    assert "pop" in {c["name"] for c in full["columns"]}

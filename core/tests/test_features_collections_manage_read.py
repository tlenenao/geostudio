# SPDX-License-Identifier: Apache-2.0
"""REV-185 : admin.collections.manage ouvre la LECTURE (items, feature unitaire,
agrégat, 2 exports, tuiles, pièces jointes) d'une collection privée non
partagée — jamais l'écriture. Sans le privilège : 404 non-fuyant partout."""

from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import set_user_role
from tests.test_features_export_routes import _as, _register, _seed, env  # noqa: F401

FEATURE = {
    "type": "Feature",
    "properties": {"region": "Nord", "pop": 10},
    "geometry": {"type": "Point", "coordinates": [0, 0]},
}


def _manager(Session, regular):
    """`regular` rechargé avec un rôle sur mesure porteur du seul privilège
    admin.collections.manage (is_admin reste False)."""
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        role = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s, tenant_id=tenant.id, user_id=regular.id, role_id=role.id, role_slug=role.slug
        )
        s.commit()
        user = s.get(User, regular.id)
        assert user is not None and user.is_admin is False
        s.expunge(user)
    return user


def _read_calls(col_id):
    agg = {"groupBy": "region", "agg": "sum", "field": "pop"}
    return [
        ("GET", f"/v1/collections/{col_id}/items", None),
        ("GET", f"/v1/collections/{col_id}/items/1", None),
        ("POST", f"/v1/collections/{col_id}/aggregate", agg),
        ("POST", f"/v1/collections/{col_id}/export?format=csv", agg),
        ("GET", f"/v1/collections/{col_id}/export/items?format=geojson", None),
        ("GET", f"/v1/collections/{col_id}/items/1/attachments", None),
        # z=99 : le 400 (coords invalides) n'est atteint QU'APRÈS la porte de lecture.
        ("GET", f"/v1/collections/{col_id}/tiles/99/0/0.mvt", None),
    ]


def _seeded_private_collection(env):  # noqa: F811
    app, client, admin, regular, tmp_path, tenant_id, Session = env
    col = _register(app, client, admin, public=False)
    _seed(tmp_path, tenant_id, col["id"])
    assert client.post(f"/v1/collections/{col['id']}/items", json=FEATURE).status_code == 201
    return app, client, regular, Session, col["id"]


def _call(client, method, url, body):
    return client.get(url) if method == "GET" else client.post(url, json=body)


def test_privilege_alone_reads_a_private_collection_everywhere(env):  # noqa: F811
    app, client, regular, Session, col_id = _seeded_private_collection(env)
    _as(app, _manager(Session, regular))
    for method, url, body in _read_calls(col_id):
        resp = _call(client, method, url, body)
        assert resp.status_code != 404, f"{method} {url} -> 404 malgré admin.collections.manage"
        assert resp.status_code in (200, 400), f"{method} {url} -> {resp.status_code}"


def test_without_the_privilege_every_read_is_a_404(env):  # noqa: F811
    app, client, regular, _Session, col_id = _seeded_private_collection(env)
    _as(app, regular)
    for method, url, body in _read_calls(col_id):
        assert _call(client, method, url, body).status_code == 404, f"{method} {url}"


def test_privilege_does_not_open_writes(env):  # noqa: F811
    # _get_writable inchangé (décision REV-185) : le voile 404 reste sur l'écriture.
    app, client, regular, Session, col_id = _seeded_private_collection(env)
    _as(app, _manager(Session, regular))
    assert client.post(f"/v1/collections/{col_id}/items", json=FEATURE).status_code == 404

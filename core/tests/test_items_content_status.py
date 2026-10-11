# SPDX-License-Identifier: Apache-2.0
"""ARC-05 : statut de contenu (none|authoritative|deprecated) + catégories."""

from app import db
from app.items.models import Item
from tests.test_items_permissions import env  # noqa: F401
from tests.test_items_publish_privilege import _give_custom_role


def _set(env, item_id, **fields):  # noqa: F811
    with db.request_scoped_session(env["session_factory"]) as s:
        item = s.get(Item, item_id)
        for k, v in fields.items():
            setattr(item, k, v)


def _add_published(env, item_id, title, **fields):  # noqa: F811
    with db.request_scoped_session(env["session_factory"]) as s:
        s.add(
            Item(
                id=item_id,
                tenant_id=s.get(Item, "pub").tenant_id,
                owner_id=s.get(Item, "pub").owner_id,
                resource_type="map",
                title=title,
                is_published=True,
                **fields,
            )
        )


def test_default_is_none_and_read_exposes_fields(env):  # noqa: F811
    r = env["as_user"](env["owner"]).get("/v1/items/shared").json()
    assert r["contentStatus"] == "none" and r["categories"] == []


def test_patch_requires_catalog_manage_and_validates(env):  # noqa: F811
    owner = env["as_user"](env["owner"])
    r = owner.patch(
        "/v1/items/shared", json={"contentStatus": "authoritative", "categories": ["Eau"]}
    )
    assert r.status_code == 200, r.text
    assert r.json()["contentStatus"] == "authoritative" and r.json()["categories"] == ["Eau"]
    assert owner.patch("/v1/items/shared", json={"contentStatus": "bogus"}).status_code == 422
    # Rôle sur mesure sans catalog.manage : titre OK, statut refusé (403).
    limited = _give_custom_role(env, env["owner"], ["maps.manage"])
    client = env["as_user"](limited)
    assert client.patch("/v1/items/shared", json={"title": "t"}).status_code == 200
    r = client.patch("/v1/items/shared", json={"contentStatus": "deprecated"})
    assert r.status_code == 403 and "catalog.manage" in r.text


def test_status_filter_boost_and_facet(env):  # noqa: F811
    _add_published(env, "ref", "Zzz référence", content_status="authoritative")
    _add_published(env, "dep", "Aaa déprécié", content_status="deprecated")
    client = env["as_user"](env["owner"])
    items = client.get("/v1/items?scope=all&pageSize=50&sort=title_asc").json()["items"]
    titles = [i["title"] for i in items]
    assert titles[0] == "Zzz référence"  # boost « Référence » devant le tri titre
    only = client.get("/v1/items?scope=all&status=authoritative").json()
    assert [i["pk"] for i in only["items"]] == ["ref"] and only["total"] == 1
    facets = client.get("/v1/items/facets?scope=all").json()
    assert {f["status"]: f["count"] for f in facets["statuses"]} == {
        "none": 2,
        "authoritative": 1,
        "deprecated": 1,
    }


def test_deprecated_excluded_from_public_catalog_by_default(env):  # noqa: F811
    _add_published(env, "dep", "Déprécié", content_status="deprecated")
    client = env["as_user"](env["stranger"])
    public = {i["pk"] for i in client.get("/v1/public/items").json()["items"]}
    assert "dep" not in public and "pub" in public
    scoped = {i["pk"] for i in client.get("/v1/items?scope=public&pageSize=50").json()["items"]}
    assert "dep" not in scoped
    explicit = client.get("/v1/items?scope=public&status=deprecated").json()["items"]
    assert [i["pk"] for i in explicit] == ["dep"]

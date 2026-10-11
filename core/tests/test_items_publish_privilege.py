# SPDX-License-Identifier: Apache-2.0
"""ARC-07 / REV-335 : publier un item exige `share` ET le privilège `items.publish`."""

from sqlalchemy import select

from app import db
from app.roles.models import Role
from app.roles.privileges import BUILT_IN_ROLE_PRIVILEGES, Privilege
from app.users.models import User
from tests.test_items_permissions import env  # noqa: F401


def _give_custom_role(env, user, privileges):  # noqa: F811
    with db.request_scoped_session(env["session_factory"]) as s:
        role = Role(
            id="custom-r",
            tenant_id=user.tenant_id,
            name="Sur mesure",
            slug="custom-r",
            is_built_in=False,
            privileges=privileges,
        )
        s.add(role)
        s.flush()
        fresh = s.scalar(select(User).where(User.id == user.id))
        fresh.role_id = role.id
        fresh.is_admin = False
        s.flush()
        s.expunge(fresh)
        return fresh


def test_privilege_granted_to_admin_and_creator_only():
    assert Privilege.ITEMS_PUBLISH.value in BUILT_IN_ROLE_PRIVILEGES["admin"]
    assert Privilege.ITEMS_PUBLISH.value in BUILT_IN_ROLE_PRIVILEGES["creator"]
    for slug in ("analyst", "reader"):
        assert Privilege.ITEMS_PUBLISH.value not in BUILT_IN_ROLE_PRIVILEGES[slug]


def test_editor_cannot_publish_via_patch(env):  # noqa: F811  (REV-335)
    r = env["as_user"](env["editor"]).patch("/v1/items/shared", json={"isPublished": True})
    assert r.status_code == 403, r.text


def test_owner_without_items_publish_cannot_publish_or_go_public(env):  # noqa: F811
    owner = _give_custom_role(env, env["owner"], [Privilege.MAPS_MANAGE.value])
    client = env["as_user"](owner)
    r = client.patch("/v1/items/shared", json={"isPublished": True})
    assert r.status_code == 403 and "items.publish" in r.text
    r = client.put("/v1/items/shared/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403 and "items.publish" in r.text
    # Un PATCH qui ne change pas la publication reste permis.
    assert client.patch("/v1/items/shared", json={"title": "ok"}).status_code == 200
    assert client.patch("/v1/items/shared", json={"isPublished": False}).status_code == 200


def test_owner_with_items_publish_can_publish_and_go_public(env):  # noqa: F811
    owner = _give_custom_role(
        env, env["owner"], [Privilege.MAPS_MANAGE.value, Privilege.ITEMS_PUBLISH.value]
    )
    client = env["as_user"](owner)
    assert client.patch("/v1/items/shared", json={"isPublished": True}).status_code == 200
    r = client.put("/v1/items/shared/sharing", json={"public": True, "groups": []})
    assert r.status_code == 204, r.text

# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811  (fixtures importées d'un autre module de test)
"""L8 T5 : kit de collecte privé et public (jumelles : même masquage GAP-22, aucune donnée)."""

import pytest
from sqlalchemy import text

from app.users.repository import get_or_create_user
from tests.test_public_submit_postgis import _anon, _as, pg_app  # noqa: F401

pytestmark = pytest.mark.postgis


@pytest.fixture()
def kit_env(pg_app):  # noqa: F811
    client, app, admin, Session, s3 = pg_app
    with Session() as s:
        stranger = get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="b",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        s.commit()
        s.expunge(stranger)
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "demo_sub"}).status_code == 201
    r = client.patch(
        "/v1/collections/demo_sub",
        json={
            "title": "Relevé voirie",
            "sensitiveFields": ["surface"],
            "geometryRequired": True,
            "attachmentFields": [
                {"key": "photo", "label": "Photo", "kind": "image"},
                {"key": "pj_secrete", "label": "Secrète", "kind": "file", "sensitive": True},
            ],
            "fieldDomains": {
                "categorie": {"type": "list", "values": ["a", "b"]},
                "gravite": {"type": "range", "min": 1, "max": 5},
            },
            "attributeRules": [
                {
                    "id": "grav-ok",
                    "kind": "constraint",
                    "field": "gravite",
                    "expression": "gravite == null || gravite > 0",
                    "message": "Gravité invalide",
                },
                {
                    "id": "secret-rule",
                    "kind": "constraint",
                    "field": "surface",
                    "expression": "surface == null || surface > 0.0",
                    "message": "Surface invalide",
                },
            ],
        },
    )
    assert r.status_code == 200, r.text
    return client, app, admin, stranger, Session


def test_private_kit_contains_what_an_offline_form_needs(kit_env):
    client, _app, _admin, _s, _S = kit_env
    res = client.get("/v1/collections/demo_sub/collect-kit")
    assert res.status_code == 200
    kit = res.json()
    names = {f["name"]: f for f in kit["schema"]["fields"]}
    assert names["photo"]["kind"] == "image" and names["photo"]["type"] == "attachment"
    assert names["categorie"]["domain"]["values"] == ["a", "b"]
    assert kit["schema"]["geometry"]["type"] == "Point"
    assert kit["geometryRequired"] is True
    assert {r["id"] for r in kit["rules"]} >= {"grav-ok"}
    assert names["nom"]["required"] is True
    assert res.headers["etag"] == f'"{kit["etag"]}"'
    # l'admin (propriétaire) voit les champs sensibles : le kit est celui de SON schéma
    assert "surface" in names and "pj_secrete" in names


def test_etag_revalidation_returns_304_and_a_change_invalidates_it(kit_env):
    client, _app, _admin, _s, _S = kit_env
    first = client.get("/v1/collections/demo_sub/collect-kit")
    etag = first.headers["etag"]
    same = client.get("/v1/collections/demo_sub/collect-kit", headers={"If-None-Match": etag})
    assert same.status_code == 304 and same.content == b""
    client.patch("/v1/collections/demo_sub", json={"geometryRequired": False})
    changed = client.get("/v1/collections/demo_sub/collect-kit", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag


def test_masked_reader_sees_no_sensitive_field_rule_or_attachment(kit_env):
    client, app, _admin, stranger, _S = kit_env
    client.patch("/v1/collections/demo_sub", json={"isPublic": True})
    _as(app, stranger)
    kit = client.get("/v1/collections/demo_sub/collect-kit")
    assert kit.status_code == 200
    body = kit.text
    names = {f["name"] for f in kit.json()["schema"]["fields"]}
    assert "surface" not in names and "pj_secrete" not in names
    assert "secret-rule" not in body and "Surface invalide" not in body
    # jumelle : le schéma servi à ce même lecteur masque la même colonne
    schema = client.get("/v1/collections/demo_sub/schema").json()
    assert "surface" not in {f["name"] for f in schema["fields"]}


def test_private_kit_requires_read_access(kit_env):
    client, app, _admin, stranger, _S = kit_env
    _as(app, stranger)  # collection non publique, non partagée
    assert client.get("/v1/collections/demo_sub/collect-kit").status_code == 404
    _anon(app)
    assert client.get("/v1/collections/demo_sub/collect-kit").status_code in (401, 403, 404)


def _token(client):
    r = client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "f", "expiresInDays": 30, "maxSubmissions": 3},
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_public_kit_hides_table_name_sensitive_fields_and_takes_no_slot(kit_env):
    client, app, _admin, _s, Session = kit_env
    token = _token(client)
    _anon(app)
    res = client.get(f"/v1/public/submit/{token}/kit")
    assert res.status_code == 200
    kit = res.json()
    body = res.text
    names = {f["name"] for f in kit["schema"]["fields"]}
    assert "surface" not in names and "pj_secrete" not in names and "photo" in names
    assert "demo_sub" not in body  # ni nom de table ni identifiant de collection
    assert "collectionId" not in kit and "secret-rule" not in body
    assert kit["geometryRequired"] is True
    with Session() as s:
        assert s.scalar(text("SELECT submission_count FROM submission_tokens")) == 0
    again = client.get(
        f"/v1/public/submit/{token}/kit", headers={"If-None-Match": res.headers["etag"]}
    )
    assert again.status_code == 304


def test_public_kit_and_challenge_answer_404_and_410_like_the_post(kit_env):
    client, app, _admin, _s, _S = kit_env
    token = _token(client)
    tid = client.get("/v1/collections/demo_sub/submission-tokens").json()["tokens"][0]["id"]
    _anon(app)
    for path in ("kit", "challenge"):
        assert client.get(f"/v1/public/submit/gss_{'1' * 12}_bad/{path}").status_code == 404
    _as(app, kit_env[2])
    assert client.delete(f"/v1/collections/demo_sub/submission-tokens/{tid}").status_code == 204
    _anon(app)
    for path in ("kit", "challenge"):
        assert client.get(f"/v1/public/submit/{token}/{path}").status_code == 410

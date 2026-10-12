# SPDX-License-Identifier: Apache-2.0
"""ARC-14 : règles CEL déclarées via PATCH, appliquées par POST/PUT, masquées GAP-22."""

import pytest

from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo
from tests.test_features_routes_write import _as, _register
from tests.test_features_routes_write import env as _env  # noqa: F401

INFO = TableInfo(
    table_name="incidents",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="titre", type="string", required=True),
        ColumnInfo(name="largeur", type="number", required=False),
        ColumnInfo(name="longueur", type="number", required=False),
        ColumnInfo(name="surface", type="number", required=False),
        ColumnInfo(name="secret", type="number", required=False),
    ],
)
RULES = {
    "attributeRules": [
        {
            "id": "surface-calc",
            "kind": "calculation",
            "field": "surface",
            "expression": "largeur * longueur",
        },
        {
            "id": "surface-positive",
            "kind": "constraint",
            "field": "surface",
            "expression": "surface > 0.0",
            "message": "La surface doit être strictement positive.",
        },
    ]
}


@pytest.fixture()
def ctx(_env):  # noqa: F811
    app, client, Session, admin, regular, repo = _env
    app.dependency_overrides[collections_routes.get_introspector] = lambda: lambda s, t: INFO
    _register(app, client, admin)
    r = client.patch("/v1/collections/incidents", json=RULES)
    assert r.status_code == 200, r.text
    return app, client, admin, regular, repo


def _feat(**props):
    return {"type": "Feature", "properties": {"titre": "x", **props}, "geometry": None}


def test_constraint_rejects_with_its_message(ctx):
    _app, client, *_ = ctx
    r = client.post("/v1/collections/incidents/items", json=_feat(surface=-1.0))
    assert r.status_code == 400
    err = r.json()["errors"][0]
    assert (err["field"], err["code"]) == ("surface", "constraint_violation")
    assert err["message"] == "La surface doit être strictement positive."


def test_calculation_feeds_field_on_insert(ctx):
    *_, repo = ctx
    _app, client, *_ = ctx
    r = client.post("/v1/collections/incidents/items", json=_feat(largeur=2.0, longueur=4.0))
    assert r.status_code == 201, r.text
    assert repo.state["rows"][2]["surface"] == 8.0


def test_put_enforces_rules_too(ctx):
    _app, client, *_ = ctx
    r = client.put("/v1/collections/incidents/items/1", json=_feat(surface=0.0))
    assert r.status_code == 400


def test_patch_rejects_bad_rules(ctx):
    _app, client, *_ = ctx
    base = {"id": "r", "kind": "constraint", "expression": "surface > 0.0", "message": "m"}
    for bad in (
        {**base, "expression": "surface >"},  # CEL invalide
        {**base, "field": "nope"},  # champ inconnu
        {**base, "message": ""},  # message requis
        {"id": "c", "kind": "calculation", "expression": "1"},  # cible requise
        {**base, "id": "Bad Id"},
    ):
        r = client.patch("/v1/collections/incidents", json={"attributeRules": [bad]})
        assert r.status_code == 422, bad
    dup = {"attributeRules": [base, base]}
    assert client.patch("/v1/collections/incidents", json=dup).status_code == 422


def test_rule_on_sensitive_field_hidden_from_masked_reader(ctx):
    app, client, admin, regular, _repo = ctx
    rule = {
        "id": "secret-pos",
        "kind": "constraint",
        "field": "secret",
        "expression": "secret > 0.0",
        "message": "m",
    }
    rules = [*RULES["attributeRules"], rule]
    assert (
        client.patch("/v1/collections/incidents", json={"attributeRules": rules}).status_code == 200
    )
    assert (
        client.patch("/v1/collections/incidents", json={"sensitiveFields": ["secret"]}).status_code
        == 200
    )
    client.patch("/v1/collections/incidents", json={"isPublic": True})
    assert len(client.get("/v1/collections/incidents").json()["attributeRules"]) == 3
    _as(app, regular)
    ids = [r["id"] for r in client.get("/v1/collections/incidents").json()["attributeRules"]]
    assert ids == ["surface-calc", "surface-positive"]

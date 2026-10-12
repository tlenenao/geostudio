# SPDX-License-Identifier: Apache-2.0
"""ARC-13 : domaines/sous-types déclarés via PATCH, appliqués par POST/PUT, exposés au schéma."""

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
        ColumnInfo(name="categorie", type="string", required=False),
        ColumnInfo(name="gravite", type="integer", required=False),
        ColumnInfo(name="secret", type="string", required=False),
        ColumnInfo(name="when", type="date", required=False),
    ],
)
DOMAINS = {
    "fieldDomains": {
        "gravite": {"type": "range", "min": 1, "max": 5},
        "secret": {"type": "list", "values": ["a", "b"]},
    },
    "subtypes": {
        "field": "categorie",
        "items": [
            {"value": "voirie", "label": "Voirie", "defaults": {"gravite": 3}},
            {"value": "eclairage", "label": "Éclairage", "defaults": {}},
        ],
    },
}


@pytest.fixture()
def ctx(_env):  # noqa: F811
    app, client, Session, admin, regular, repo = _env
    app.dependency_overrides[collections_routes.get_introspector] = lambda: lambda s, t: INFO
    _register(app, client, admin)
    r = client.patch("/v1/collections/incidents", json=DOMAINS)
    assert r.status_code == 200, r.text
    return app, client, admin, regular, repo


def _feat(**props):
    return {"type": "Feature", "properties": {"titre": "x", **props}, "geometry": None}


def test_out_of_domain_is_400_field_code(ctx):
    _app, client, *_ = ctx
    r = client.post("/v1/collections/incidents/items", json=_feat(gravite=9))
    assert r.status_code == 400
    errs = r.json()["errors"]
    assert {"field": "gravite", "code": "out_of_domain"} == {
        k: errs[0][k] for k in ("field", "code")
    }


def test_subtype_default_written_on_create(ctx):
    *_, repo = ctx
    app, client, *_ = ctx
    r = client.post("/v1/collections/incidents/items", json=_feat(categorie="voirie"))
    assert r.status_code == 201, r.text
    assert repo.state["rows"][2]["gravite"] == 3


def test_put_validates_domain_too(ctx):
    _app, client, *_ = ctx
    r = client.put("/v1/collections/incidents/items/1", json=_feat(categorie="autre"))
    assert r.status_code == 400


def test_schema_and_collection_expose_domains(ctx):
    _app, client, *_ = ctx
    schema = client.get("/v1/collections/incidents/schema").json()
    grav = next(f for f in schema["fields"] if f["name"] == "gravite")
    assert grav["domain"] == {"type": "range", "min": 1.0, "max": 5.0}
    assert schema["subtypes"]["field"] == "categorie"
    assert client.get("/v1/collections/incidents").json()["fieldDomains"]["gravite"]


def test_patch_rejects_domain_on_unknown_or_mismatched_field(ctx):
    _app, client, *_ = ctx
    bad = {"fieldDomains": {"nope": {"type": "list", "values": ["a"]}}}
    assert client.patch("/v1/collections/incidents", json=bad).status_code == 422
    bad = {"fieldDomains": {"titre": {"type": "range", "min": 0}}}
    assert client.patch("/v1/collections/incidents", json=bad).status_code == 422
    bad = {"subtypes": {"field": "when", "items": [{"value": "x", "label": "X"}]}}
    assert client.patch("/v1/collections/incidents", json=bad).status_code == 422
    bad = {"fieldDomains": {"gravite": {"type": "range", "min": 5, "max": 1}}}
    assert client.patch("/v1/collections/incidents", json=bad).status_code == 422


def test_subtypes_cleared_with_explicit_null(ctx):
    _app, client, *_ = ctx
    assert client.patch("/v1/collections/incidents", json={"subtypes": None}).status_code == 200
    assert client.get("/v1/collections/incidents").json()["subtypes"] is None


def test_sensitive_field_domain_hidden_from_masked_reader(ctx):
    app, client, admin, regular, _repo = ctx
    # le propriétaire déclare "secret" sensible : un lecteur masqué ne voit plus son domaine
    sp = client.patch("/v1/collections/incidents", json={"sensitiveFields": ["secret"]})
    assert sp.status_code == 200, sp.text
    client.patch("/v1/collections/incidents", json={"isPublic": True})
    admin_view = client.get("/v1/collections/incidents").json()
    assert "secret" in admin_view["fieldDomains"]
    _as(app, regular)
    view = client.get("/v1/collections/incidents").json()
    assert "secret" not in view["fieldDomains"]
    schema = client.get("/v1/collections/incidents/schema").json()
    assert "secret" not in {f["name"] for f in schema["fields"]}

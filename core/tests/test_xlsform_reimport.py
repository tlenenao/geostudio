# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811  (fixtures importées d'un autre module de test)
"""L8 T8 : réimport XLSForm sur une collection existante, avec rapport de différences.

Additif seulement : une colonne ajoutée est créée, les libellés/règles sont mis à jour, mais un
retypage ou une suppression de colonne est BLOQUÉ (jamais appliqué) et rapporté. Aucune 2e
collection, l'App existante n'est jamais écrasée."""

import pytest
from sqlalchemy import text

from tests.test_xlsform_import_postgis import _import, env  # noqa: F401
from tests.test_xlsform_parser import _book

pytestmark = pytest.mark.postgis

CHOICES = [("list_name", "name", "label"), ("etat", "bon", "Bon"), ("etat", "hs", "HS")]


def _form(rows=(), choices=CHOICES):
    base = [
        ("type", "name", "label", "required"),
        ("text", "nom", "Nom", "yes"),
        ("select_one etat", "etat", "État", None),
        ("geopoint", "pos", "Position", None),
    ]
    return _book([*base, *rows], choices=choices)


def _reimport(client, cid, content):
    return client.post(
        f"/v1/xlsform/import?collectionId={cid}",
        files={"file": ("f.xlsx", content, "application/octet-stream")},
    )


def _columns(Session, table):
    with Session() as s:
        return dict(
            s.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = :t"
                ),
                {"t": table},
            ).all()
        )


def _created(client):
    first = _import(client, _form()).json()
    return first["collectionId"], first["itemId"]


def test_identical_reimport_reports_no_difference_and_creates_nothing(env):
    client, Session, _as = env
    cid, _item = _created(client)
    n_before = len(client.get("/v1/collections").json()["collections"])
    r = _reimport(client, cid, _form())
    assert r.status_code == 200, r.text
    assert r.json()["differences"] == {"added": [], "changed": [], "blocked": []}
    assert r.json()["collectionId"] == cid
    assert len(client.get("/v1/collections").json()["collections"]) == n_before


def test_added_column_is_created_and_reported(env):
    client, Session, _as = env
    cid, _item = _created(client)
    r = _reimport(client, cid, _form([("integer", "age", "Âge", None)]))
    assert r.status_code == 200, r.text
    assert [d["name"] for d in r.json()["differences"]["added"]] == ["age"]
    assert r.json()["differences"]["blocked"] == []
    assert _columns(Session, cid)["age"] == "integer"


def test_changed_choice_label_updates_the_domain_and_is_reported(env):
    client, Session, _as = env
    cid, _item = _created(client)
    new_choices = [
        ("list_name", "name", "label"),
        ("etat", "bon", "Très bon"),
        ("etat", "hs", "HS"),
    ]
    r = _reimport(client, cid, _form(choices=new_choices))
    assert r.status_code == 200, r.text
    assert [d["name"] for d in r.json()["differences"]["changed"]] == ["etat"]
    col = client.get(f"/v1/collections/{cid}").json()
    assert col["fieldDomains"]["etat"]["labels"]["bon"] == "Très bon"


def test_retyped_and_removed_columns_are_blocked_never_applied(env):
    client, Session, _as = env
    cid, _item = _created(client)
    # `nom` devient un entier, `etat` disparaît
    content = _book(
        [
            ("type", "name", "label"),
            ("integer", "nom", "Nom"),
            ("geopoint", "pos", "Position"),
        ]
    )
    r = _reimport(client, cid, content)
    assert r.status_code == 200, r.text
    diff = r.json()["differences"]
    assert {d["name"] for d in diff["blocked"]} == {"nom", "etat"}
    assert diff["added"] == []
    cols = _columns(Session, cid)
    assert cols["nom"] == "text" and "etat" in cols  # rien n'a été modifié ni supprimé
    # les règles de l'existant n'ont pas été touchées par un import bloqué sur ces champs
    col = client.get(f"/v1/collections/{cid}").json()
    assert "etat" in col["fieldDomains"]


def test_geometry_type_change_is_blocked(env):
    client, Session, _as = env
    cid, _item = _created(client)
    content = _book(
        [("type", "name", "label"), ("text", "nom", "Nom"), ("geotrace", "pos", "Trace")]
    )
    r = _reimport(client, cid, content)
    assert r.status_code == 200, r.text
    assert any(d["name"] == "geometry" for d in r.json()["differences"]["blocked"])


def test_reimport_requires_write_access_on_the_collection(env):
    client, Session, as_ = env
    cid, _item = _created(client)
    as_("reader")
    assert _reimport(client, cid, _form()).status_code in (403, 404)
    as_("admin")
    assert _reimport(client, "query_inexistant", _form()).status_code == 404

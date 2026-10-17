# SPDX-License-Identifier: Apache-2.0
"""AUD-047 : fiche ISO 19139 par collection (bien formée, contenu INSPIRE minimal)."""

import xml.etree.ElementTree as ET

from app.dcat import routes as dcat_routes
from tests.test_ogc_discovery import _as, _register, env  # noqa: F401  (fixture)

NS = {"gmd": "http://www.isotc211.org/2005/gmd", "gco": "http://www.isotc211.org/2005/gco"}


def test_iso19139_metadata(env):  # noqa: F811
    app, client, admin, _regular, _repo = env
    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: (
        lambda session, info: [1.0, 45.0, 2.0, 46.0]
    )
    _register(app, client, admin, public=True)
    _as(app, admin)
    client.patch(
        "/v1/collections/incidents",
        json={
            "keywords": ["sécurité"],
            "inspireTheme": "hh",
            "license": "etalab-2.0",
            "contact": "sig@exemple.fr",
            "lineage": "Saisie terrain",
        },
    )
    r = client.get("/v1/collections/incidents/metadata")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    root = ET.fromstring(r.content)
    assert root.tag == "{http://www.isotc211.org/2005/gmd}MD_Metadata"
    assert root.findtext("gmd:fileIdentifier/gco:CharacterString", namespaces=NS) == "incidents"
    words = [e.text for e in root.iterfind(".//gmd:keyword/gco:CharacterString", NS)]
    assert "sécurité" in words and "Santé et sécurité des personnes" in words
    assert root.findtext(".//gmd:topicCategory/gmd:MD_TopicCategoryCode", namespaces=NS) == "health"
    west = root.findtext(".//gmd:westBoundLongitude/gco:Decimal", namespaces=NS)
    assert float(west) == 1.0
    assert "/v1/collections/incidents/items" in r.text


def test_iso19139_404_and_ogc_link(env):  # noqa: F811
    app, client, admin, _regular, _repo = env
    assert client.get("/v1/collections/nope/metadata").status_code == 404
    _register(app, client, admin, public=True)
    links = client.get("/v1/collections/incidents").json()["links"]
    assert any(
        link["rel"] == "describedby" and link["href"].endswith("/metadata") for link in links
    )


def test_iso19139_survives_aborted_transaction(env):  # noqa: F811
    """Revue L6 M1 : une DBAPIError à l'introspection avorte la transaction Postgres ;
    simulée ici en faisant échouer toute requête SQL suivante (SQLite ne le fait pas)."""
    from sqlalchemy import event
    from sqlalchemy.exc import DBAPIError

    from app.collections import routes as collections_routes

    app, client, admin, _regular, _repo = env
    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: (
        lambda session, info: [1.0, 45.0, 2.0, 46.0]
    )
    _register(app, client, admin, public=True)
    _as(app, None)  # anonyme : le tenant par défaut se résout par une requête SQL
    listeners = []

    def broken(session, table_name):
        engine = session.get_bind()

        def refuse(*_args, **_kw):
            raise DBAPIError("SELECT", {}, Exception("current transaction is aborted"))

        if not listeners:
            event.listen(engine, "before_cursor_execute", refuse)
            listeners.append((engine, refuse))
        raise DBAPIError("SELECT", {}, Exception("boom"))

    app.dependency_overrides[collections_routes.get_introspector] = lambda: broken
    try:
        r = client.get("/v1/collections/incidents/metadata")
    finally:
        for engine, fn in listeners:
            event.remove(engine, "before_cursor_execute", fn)
    assert r.status_code == 200, r.text
    assert "westBoundLongitude" not in r.text  # fiche sans emprise, pas 500

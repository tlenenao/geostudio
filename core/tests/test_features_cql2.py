# SPDX-License-Identifier: Apache-2.0
"""ARC-12 : CQL2-text (`filter`/`filter-lang`) sur GET /collections/{id}/items.
Suite de référence (PostGIS réel) + injection + compilation paramétrée (SQLite)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.introspection import ColumnInfo, TableInfo
from app.db import Base, make_session_factory, request_scoped_session
from app.features.cql2 import compile_cql2
from app.features.repository import FilterError
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

URL = "/v1/collections/demo_cql/items"
ROWS = [  # id attendu = rang (serial)
    ("alpha", 10, 1.5, True, "2024-01-01", "2024-01-01T00:00:00Z", 1, 1),
    ("bravo", 20, 2.5, False, "2024-06-15", "2024-06-15T12:00:00Z", 2, 2),
    ("Charlie", 30, 3.5, True, "2025-01-01", "2025-01-01T00:00:00Z", 3, 3),
    ("delta", 40, None, None, None, None, 10, 10),
    ("alpha beta", 50, 5.5, False, "2025-06-01", "2025-06-01T00:00:00Z", 20, 20),
]
SQ = "POLYGON((0 0, 0 5, 5 5, 5 0, 0 0))"
# (expression CQL2-text, ids attendus)
REFERENCE = [
    ("pop = 10", [1]),
    ("pop <> 10", [2, 3, 4, 5]),
    ("pop > 20", [3, 4, 5]),
    ("pop >= 20", [2, 3, 4, 5]),
    ("pop < 30", [1, 2]),
    ("pop <= 30", [1, 2, 3]),
    ("nom = 'alpha'", [1]),
    ("nom <> 'alpha'", [2, 3, 4, 5]),
    ("nom = 'it''s'", []),
    ("ratio > 2", [2, 3, 5]),
    ("ratio = 1.5", [1]),
    ("actif = true", [1, 3]),
    ("actif = FALSE", [2, 5]),
    ("NOT (actif = true)", [2, 5]),
    ("actif", [1, 3]),
    ("pop > 10 AND pop < 40", [2, 3]),
    ("pop < 20 OR pop > 40", [1, 5]),
    ("NOT (pop > 20)", [1, 2]),
    ("(pop = 10 OR pop = 20) AND actif = true", [1]),
    ("pop = 10 and nom = 'alpha'", [1]),
    ("nom LIKE 'alpha%'", [1, 5]),
    ("nom LIKE '%ta'", [4, 5]),
    ("nom NOT LIKE 'alpha%'", [2, 3, 4]),
    ("nom LIKE 'a_pha'", [1]),
    ("CASEI(nom) = CASEI('charlie')", [3]),
    ("nom IN ('alpha','bravo')", [1, 2]),
    ("nom NOT IN ('alpha','bravo')", [3, 4, 5]),
    ("pop IN (10, 30, 50)", [1, 3, 5]),
    ("pop BETWEEN 20 AND 40", [2, 3, 4]),
    ("pop NOT BETWEEN 20 AND 40", [1, 5]),
    ("ratio IS NULL", [4]),
    ("ratio IS NOT NULL", [1, 2, 3, 5]),
    ("jour > DATE('2024-12-31')", [3, 5]),
    ("jour = DATE('2024-06-15')", [2]),
    ("quand >= TIMESTAMP('2025-01-01T00:00:00Z')", [3, 5]),
    ("jour BETWEEN DATE('2024-01-01') AND DATE('2024-12-31')", [1, 2]),
    (f"S_INTERSECTS(geom, {SQ})", [1, 2, 3]),
    ("S_INTERSECTS(geom, BBOX(0,0,15,15))", [1, 2, 3, 4]),
    (f"S_WITHIN(geom, {SQ})", [1, 2, 3]),
    ("S_DISJOINT(geom, BBOX(0,0,15,15))", [5]),
    ("S_INTERSECTS(geom, POINT(2 2))", [2]),
    ('S_INTERSECTS(geom, {"type":"Point","coordinates":[3,3]})', [3]),
    ("T_AFTER(jour, DATE('2024-12-31'))", [3, 5]),
    ("T_BEFORE(quand, TIMESTAMP('2024-02-01T00:00:00Z'))", [1]),
    ("T_DURING(jour, INTERVAL('2024-01-01','2024-12-31'))", [1, 2]),
    ("T_DURING(quand, INTERVAL('2025-01-01T00:00:00Z','..'))", [3, 5]),
    ("T_EQUALS(jour, DATE('2024-06-15'))", [2]),
    ("30 < pop", [4, 5]),
    ('"pop" = 10', [1]),
]
BAD = [
    "1=1; DROP TABLE demo_cql",
    "pop = 10; DROP TABLE demo_cql",
    "pop = 10 -- x",
    "pop =",
    "nope = 1",
    "pop = 'abc'",
    "nom = 'x' OR (",
    "pop IN ()",
    "S_INTERSECTS(geom, POLYGON((0 0)))",
    'S_INTERSECTS(geom, {"type":"Point"})',
    "S_INTERSECTS(nom, POINT(1 1))",
    "jour > DATE('2024-13-45')",
    "FOO(pop)",
    "geom = 1",
    "(" * 200 + "pop = 1" + ")" * 200,
    "",
]


@pytest.fixture()
def client(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_cql"))
        conn.execute(
            text(
                "CREATE TABLE demo_cql (id serial PRIMARY KEY, nom text, pop integer, "
                "ratio double precision, actif boolean, jour date, quand timestamptz, "
                "geom geometry(Point, 4326))"
            )
        )
    Session_ = make_session_factory(pg_engine)
    with Session_() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session_) as session:
            yield session

    class _S3:
        def delete_object(self, *, Bucket, Key):
            pass

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    c = TestClient(app)
    assert c.post("/v1/collections", json={"tableName": "demo_cql"}).status_code == 201
    for nom, pop, ratio, actif, jour, quand, lon, lat in ROWS:
        r = c.post(
            URL,
            json={
                "type": "Feature",
                "properties": {
                    "nom": nom,
                    "pop": pop,
                    "ratio": ratio,
                    "actif": actif,
                    "jour": jour,
                    "quand": quand,
                },
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            },
        )
        assert r.status_code == 201, r.text
    yield c
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_cql"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


@pytest.mark.postgis
@pytest.mark.parametrize(("expr", "ids"), REFERENCE, ids=[e[0][:50] for e in REFERENCE])
def test_reference_expression(client, expr, ids):
    r = client.get(URL, params={"filter": expr, "filter-lang": "cql2-text"})
    assert r.status_code == 200, r.text
    assert sorted(f["id"] for f in r.json()["features"]) == ids


@pytest.mark.postgis
@pytest.mark.parametrize("expr", BAD)
def test_invalid_filter_is_400_and_harmless(client, expr):
    r = client.get(URL, params={"filter": expr})
    assert r.status_code == 400, r.text
    assert r.json()["errors"][0]["code"] == "invalid_filter"
    assert client.get(URL).status_code == 200  # la table existe toujours


@pytest.mark.postgis
def test_unsupported_filter_lang_and_combination(client):
    r = client.get(URL, params={"filter": "pop = 10", "filter-lang": "cql2-json"})
    assert r.status_code == 400
    # combiné (ET) avec un filtre d'égalité classique et un bbox
    r = client.get(URL, params={"filter": "pop > 10", "nom": "bravo", "bbox": "0,0,5,5"})
    assert [f["id"] for f in r.json()["features"]] == [2]


def test_conformance_declares_cql2():
    conf = TestClient(create_app()).get("/v1/conformance").json()["conformsTo"]
    assert "http://www.opengis.net/spec/ogcapi-features-3/1.0/conf/filter" in conf
    assert "http://www.opengis.net/spec/cql2/1.0/conf/cql2-text" in conf


def _info():
    cols = [
        ColumnInfo("id", "integer", True),
        ColumnInfo("nom", "string", False),
        ColumnInfo("pop", "integer", False),
    ]
    return TableInfo("t", "id", "geom", "Point", 4326, cols)


def test_compiled_sql_is_parameterised():
    with Session(create_engine("sqlite://")) as s:
        sql, params = compile_cql2(s, _info(), "nom = 'x'' OR 1=1 --' AND pop IN (1,2)")
    assert "OR 1=1" not in sql
    assert "x' OR 1=1 --" in params.values()
    with Session(create_engine("sqlite://")) as s, pytest.raises(FilterError) as exc:
        compile_cql2(s, _info(), "pop = 1; DROP TABLE t")
    assert exc.value.code == "invalid_filter"

# SPDX-License-Identifier: Apache-2.0
"""Limite géographique v2 (REV-121) : DÉCOUPAGE à la limite sur PostGIS réel. Une entité
qui intersecte la limite est visible, mais seule sa géométrie découpée sort — sur chaque
chemin de lecture (repository, bbox/geom_intersects, tuile, emprises) ; écriture et
mise à jour d'une entité à cheval : fail-closed (spec §5/§6/§9)."""

import json

import pytest
from shapely.geometry import box, shape
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.collections.ddl import alter_geometry_column, apply_collection_ddl
from app.collections.extent import table_extent
from app.collections.introspection_pg import introspect_table
from app.features import repository as repo
from app.features.rls import rls_scope
from app.features.tiles import build_agg_mvt_sql, build_mvt_sql, build_probe_sql
from app.sharing.geo_limits import GeoLimitStraddling, geo_source
from app.sql_ident import quote_ident
from app.stac.extent import rls_scoped_bbox_4326

pytestmark = pytest.mark.postgis

LIMIT_BOX = box(0, 0, 10, 10)
SQUARE = json.loads(json.dumps(LIMIT_BOX.__geo_interface__))
LIMITS = {"gl_poly": [SQUARE]}
FULL = {  # géométrie COMPLÈTE de l'entité à cheval : jamais (même partiellement) rendue
    "straddle": box(5, 5, 15, 15),
    "inside": box(2, 2, 4, 4),
    "outside": box(40, 40, 50, 50),
    "touch": box(10, 0, 20, 5),  # ne touche la limite que par un bord : invisible
}


@pytest.fixture()
def polys(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_poly, gl_line"))
        conn.execute(
            text(
                "CREATE TABLE gl_poly (id serial PRIMARY KEY, name text, "
                "geom geometry(Polygon, 4326))"
            )
        )
        for name, g in FULL.items():
            conn.execute(
                text("INSERT INTO gl_poly (name, geom) VALUES (:n, ST_GeomFromText(:w, 4326))"),
                {"n": name, "w": g.wkt},
            )
        conn.execute(text("INSERT INTO gl_poly (name, geom) VALUES ('nogeom', NULL)"))
        conn.execute(
            text("CREATE TABLE gl_line (id serial PRIMARY KEY, geom geometry(LineString, 4326))")
        )
        conn.execute(
            text(
                "INSERT INTO gl_line (geom) "
                "VALUES (ST_GeomFromText('LINESTRING(-5 5, 15 5)', 4326))"
            )
        )
    with pg_session_factory() as session:
        apply_collection_ddl(session, "gl_poly", tenant_id="default")
        apply_collection_ddl(session, "gl_line", tenant_id="default")
        session.commit()
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS gl_poly, gl_line"))


def _page(s, info, limits=LIMITS, **kw):
    with rls_scope(s, "default", geo_limits=limits):
        return repo.select_features(s, info, limit=50, offset=0, **kw)


def _within_limit(geometry: dict) -> bool:
    return LIMIT_BOX.buffer(1e-9).covers(shape(geometry))


def test_straddling_entity_is_visible_but_only_clipped(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        page = _page(s, info)
        by_name = {f["properties"]["name"]: f for f in page.features}
        # touch (contact de bord), outside, nogeom : invisibles ; straddle + inside : visibles
        assert sorted(by_name) == ["inside", "straddle"]
        assert page.number_matched == 2
        clipped = shape(by_name["straddle"]["geometry"])
        assert clipped.equals(box(5, 5, 10, 10))
        assert _within_limit(by_name["straddle"]["geometry"])
        assert shape(by_name["inside"]["geometry"]).equals(FULL["inside"])
        fid = by_name["straddle"]["id"]
        with rls_scope(s, "default", geo_limits=LIMITS):
            one = repo.get_feature(s, info, fid=str(fid))
        assert _within_limit(one["geometry"])


def test_filters_run_on_the_clipped_geometry(polys, pg_session_factory):
    """bbox/geom_intersects visant la partie CACHÉE de l'entité à cheval ne la ramènent pas
    (sinon sondage de la géométrie complète par dichotomie)."""
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        hidden_part = (11, 11, 14, 14)
        assert _page(s, info, bbox=hidden_part).features == []
        hidden_poly = json.loads(json.dumps(box(11, 11, 14, 14).__geo_interface__))
        page = _page(s, info, geom_intersects=hidden_poly, count_mode="exact")
        assert page.features == [] and page.number_matched == 0
        visible_part = (6, 6, 9, 9)
        assert [f["properties"]["name"] for f in _page(s, info, bbox=visible_part).features] == [
            "straddle"
        ]


def test_lines_are_clipped_and_stay_lines(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_line")
        page = _page(s, info, limits={"gl_line": [SQUARE]})
        (feat,) = page.features
        assert feat["geometry"]["type"] == "LineString"
        assert shape(feat["geometry"]).equals(
            shape({"type": "LineString", "coordinates": [[0, 5], [10, 5]]})
        )


def test_extents_are_those_of_the_clipped_geometry(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        with rls_scope(s, "default", geo_limits=LIMITS):
            assert table_extent(s, info) == [2.0, 2.0, 10.0, 10.0]
            assert rls_scoped_bbox_4326(s, info) == [2.0, 2.0, 10.0, 10.0]
        with rls_scope(s, "default", masked=True, geo_limits=LIMITS):
            assert rls_scoped_bbox_4326(s, info) == [2.0, 2.0, 10.0, 10.0]  # masqué : ok aussi
        # le miroir Python ne survit pas au scope : le code système (propriétaire) lit tout
        assert "geo_limits" not in s.info
        assert table_extent(s, info) == [2.0, 0.0, 50.0, 50.0]
        with rls_scope(s, "default"):  # non limité : emprise complète
            assert table_extent(s, info) == [2.0, 0.0, 50.0, 50.0]


def test_tile_queries_read_the_clipped_geometry(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        quote = lambda n: quote_ident(s, n)  # noqa: E731
        params = {
            "z": 0, "x": 0, "y": 0, "layer": "l", "extent": 4096, "buffer": 64,
            "srid": 4326, "max_features": 5000, "fid": "id", "cell": 1000.0,
        }  # fmt: skip
        with rls_scope(s, "default", geo_limits=LIMITS), geo_source(s, info) as src:
            tile, count = s.execute(text(build_mvt_sql(quote, info, src)), params).one()
            assert count == 2  # straddle + inside, ni touch ni outside
            assert s.execute(text(build_probe_sql(quote, info, src)), params).scalar() == 2
            assert s.execute(text(build_agg_mvt_sql(quote, info, src)), params).scalar()
            # la source elle-même : aucune coordonnée hors limite
            extent = s.execute(text(f"SELECT ST_Extent(geom)::text FROM {src}")).scalar()
            assert extent == "BOX(2 2,10 10)"
        assert bytes(tile)  # tuile non vide


def test_reader_that_ignores_geo_source_sees_no_straddling_entity(polys, pg_session_factory):
    """Fail-closed : lire la table de base sous limite ne montre que les entités
    ENTIÈREMENT contenues — jamais la géométrie complète d'une entité à cheval."""
    with pg_session_factory() as s:
        with rls_scope(s, "default", geo_limits=LIMITS):
            rows = s.execute(text("SELECT name, ST_AsText(geom) FROM gl_poly")).all()
        assert [r[0] for r in rows] == ["inside"]
        # le drapeau ne survit pas à geo_source : retour au mode strict
        info = introspect_table(s, "gl_poly")
        with rls_scope(s, "default", geo_limits=LIMITS):
            _ = repo.select_features(s, info, limit=5, offset=0)
            assert s.execute(text("SELECT count(*) FROM gl_poly")).scalar() == 1


def _fid(s, name):
    return s.execute(text("SELECT id FROM gl_poly WHERE name = :n"), {"n": name}).scalar()


def _db_wkt(s, name):
    return s.execute(
        text("SELECT ST_AsText(geom) FROM gl_poly WHERE name = :n"), {"n": name}
    ).scalar()


def test_update_of_a_straddling_entity_is_attributes_only(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        fid = str(_fid(s, "straddle"))
        before = _db_wkt(s, "straddle")
        # la version DÉCOUPÉE renvoyée telle quelle (aller-retour du shell) : attributs écrits,
        # géométrie complète conservée en base
        with rls_scope(s, "default", geo_limits=LIMITS):
            clipped = repo.get_feature(s, info, fid=fid)["geometry"]
            assert repo.replace_feature(
                s, info, fid=fid, properties={"name": "renamed"}, geometry=clipped
            )
            # sans géométrie : idem (jamais remise à NULL)
            assert repo.replace_feature(
                s, info, fid=fid, properties={"name": "renamed2"}, geometry=None
            )
        row = s.execute(
            text("SELECT name, ST_AsText(geom) FROM gl_poly WHERE id = :i"), {"i": int(fid)}
        ).one()
        assert row[0] == "renamed2" and row[1] == before
        # une autre géométrie : refusée, base intacte
        other = json.loads(json.dumps(box(6, 6, 9, 9).__geo_interface__))
        with pytest.raises(GeoLimitStraddling):
            with rls_scope(s, "default", geo_limits=LIMITS):
                repo.replace_feature(s, info, fid=fid, properties={"name": "x"}, geometry=other)
        s.rollback()
        assert (
            s.execute(
                text("SELECT ST_AsText(geom) FROM gl_poly WHERE id = :i"), {"i": int(fid)}
            ).scalar()
            == before
        )


def test_inside_entity_cannot_be_stretched_across_the_limit(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        fid = str(_fid(s, "inside"))
        stretched = json.loads(json.dumps(box(2, 2, 20, 20).__geo_interface__))
        with pytest.raises(DBAPIError) as exc:
            with rls_scope(s, "default", geo_limits=LIMITS):
                repo.replace_feature(s, info, fid=fid, properties={"name": "i"}, geometry=stretched)
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()
        with pytest.raises(DBAPIError) as exc:  # géométrie NULL : refusée aussi
            with rls_scope(s, "default", geo_limits=LIMITS):
                repo.replace_feature(s, info, fid=fid, properties={"name": "i"}, geometry=None)
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()


def test_insert_straddling_the_limit_is_refused(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        with pytest.raises(DBAPIError) as exc:
            with rls_scope(s, "default", geo_limits=LIMITS):
                repo.insert_feature(
                    s, info, properties={"name": "n"}, geometry=box(5, 5, 15, 15).__geo_interface__
                )
        assert getattr(exc.value.orig, "sqlstate", None) == "42501"
        s.rollback()
        with rls_scope(s, "default", geo_limits=LIMITS):
            assert repo.insert_feature(
                s, info, properties={"name": "ok"}, geometry=box(1, 1, 2, 2).__geo_interface__
            )
        s.rollback()


def test_delete_of_a_straddling_entity_is_refused_as_not_found(polys, pg_session_factory):
    with pg_session_factory() as s:
        info = introspect_table(s, "gl_poly")
        with rls_scope(s, "default", geo_limits=LIMITS):
            assert repo.delete_feature(s, info, fid=str(_fid(s, "straddle"))) is False
            assert repo.delete_feature(s, info, fid=str(_fid(s, "inside"))) is True
            assert repo.delete_all_features(s, info) == 0  # il ne reste que l'à-cheval
        s.rollback()
        assert _db_wkt(s, "straddle") is not None


def test_alter_geometry_column_recreates_the_policies(polys, pg_session_factory):
    with pg_session_factory() as s:
        # Postgres refuse un ALTER direct : une colonne citée par une policy
        with pytest.raises(DBAPIError):
            s.execute(
                text(
                    "ALTER TABLE gl_poly ALTER COLUMN geom TYPE geometry(Polygon, 3857) "
                    "USING ST_Transform(geom, 3857)"
                )
            )
        s.rollback()
        alter_geometry_column(s, "gl_poly", geometry_type="Polygon", srid=3857)
        s.commit()
        n = s.execute(
            text(
                "SELECT count(*) FROM pg_policies "
                "WHERE tablename='gl_poly' AND policyname LIKE 'geo_limit_%'"
            )
        ).scalar()
        assert n == 4
        info = introspect_table(s, "gl_poly")
        assert info.srid == 3857
        page = _page(s, info)  # la limite WGS84 est reprojetée dans le nouveau SRID
        assert sorted(f["properties"]["name"] for f in page.features) == ["inside", "straddle"]
        with rls_scope(s, "default", geo_limits=LIMITS):
            assert [r[0] for r in s.execute(text("SELECT name FROM gl_poly")).all()] == ["inside"]

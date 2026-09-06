# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.introspection import ColumnInfo, TableInfo
from app.stac.extent import rls_scoped_bbox_4326

NO_GEOM = TableInfo(
    table_name="t",
    pk_column="id",
    geometry_column=None,
    geometry_type=None,
    srid=None,
    columns=[ColumnInfo(name="id", type="integer", required=True)],
)


def test_no_geometry_column_returns_none_without_db():
    # Chemin toujours exécuté (aucun accès SQL) : geometry_column None → None.
    assert rls_scoped_bbox_4326(session=None, info=NO_GEOM) is None


@pytest.mark.postgis
def test_estimated_bbox_reprojected(pg_session_factory):
    info = TableInfo(
        table_name="stac_extent_t",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="id", type="integer", required=True)],
    )
    with pg_session_factory() as s:
        s.execute(text("DROP TABLE IF EXISTS stac_extent_t"))
        s.execute(
            text("CREATE TABLE stac_extent_t (id serial PRIMARY KEY, geom geometry(Point, 4326))")
        )
        s.execute(
            text(
                "INSERT INTO stac_extent_t (geom) VALUES "
                "(ST_SetSRID(ST_MakePoint(1.0, 44.0), 4326)), "
                "(ST_SetSRID(ST_MakePoint(2.0, 45.0), 4326))"
            )
        )
        s.execute(text("ANALYZE stac_extent_t"))
        s.commit()
        bbox = rls_scoped_bbox_4326(s, info)
        assert bbox is not None
        assert bbox[0] == pytest.approx(1.0, abs=0.01)
        assert bbox[1] == pytest.approx(44.0, abs=0.01)
        assert bbox[2] == pytest.approx(2.0, abs=0.01)
        assert bbox[3] == pytest.approx(45.0, abs=0.01)
        s.execute(text("DROP TABLE IF EXISTS stac_extent_t"))
        s.commit()


@pytest.mark.postgis
def test_estimated_bbox_reprojected_from_lambert93(pg_session_factory):
    # Preuve que la reprojection est réellement structurante : source en
    # Lambert-93 (EPSG:2154, mètres) — contrairement à
    # test_estimated_bbox_reprojected (source déjà 4326, transform identité,
    # ne détecterait pas un ST_Transform supprimé par erreur). Si
    # rls_scoped_bbox_4326 ne transformait pas, la bbox retournée resterait en
    # coordonnées métriques (~650000/~6860000), hors de tout intervalle
    # lon/lat valide — les assertions ci-dessous échoueraient toutes.
    info = TableInfo(
        table_name="stac_extent_lambert_t",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=2154,
        columns=[ColumnInfo(name="id", type="integer", required=True)],
    )
    with pg_session_factory() as s:
        s.execute(text("DROP TABLE IF EXISTS stac_extent_lambert_t"))
        s.execute(
            text(
                "CREATE TABLE stac_extent_lambert_t (id serial PRIMARY KEY, "
                "geom geometry(Point, 2154))"
            )
        )
        s.execute(
            text(
                "INSERT INTO stac_extent_lambert_t (geom) VALUES "
                "(ST_SetSRID(ST_MakePoint(650000, 6860000), 2154)), "
                "(ST_SetSRID(ST_MakePoint(652000, 6862000), 2154))"
            )
        )
        s.execute(text("ANALYZE stac_extent_lambert_t"))
        s.commit()
        bbox = rls_scoped_bbox_4326(s, info)
        assert bbox is not None
        assert -5.0 <= bbox[0] <= 10.0
        assert 41.0 <= bbox[1] <= 52.0
        assert -5.0 <= bbox[2] <= 10.0
        assert 41.0 <= bbox[3] <= 52.0
        s.execute(text("DROP TABLE IF EXISTS stac_extent_lambert_t"))
        s.commit()

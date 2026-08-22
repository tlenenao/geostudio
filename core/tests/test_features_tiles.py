# SPDX-License-Identifier: Apache-2.0
"""Helpers purs du service de tuiles MVT (spec SP-24 §3.1). Aucun accès base :
on teste la validation des coordonnées, la liste des colonnes de propriétés et
la forme du SQL produit — le SQL réel est exercé par
test_features_tiles_postgis.py."""

import pytest

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.tiles import (
    InvalidTileCoords,
    build_mvt_sql,
    mvt_feature_id_column,
    mvt_property_columns,
    validate_tile_coords,
)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _info(pk_type: str = "integer", **kwargs) -> TableInfo:
    defaults = dict(
        table_name="demo_incidents",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="id", type=pk_type, required=False),
            ColumnInfo(name="titre", type="string", required=True),
            ColumnInfo(name="tenant_id", type="string", required=True),
        ],
    )
    defaults.update(kwargs)
    return TableInfo(**defaults)


@pytest.mark.parametrize("coords", [(0, 0, 0), (1, 1, 1), (24, 0, 0), (2, 3, 3)])
def test_valid_coords_are_accepted(coords):
    assert validate_tile_coords(*coords) is None


@pytest.mark.parametrize(
    "coords",
    [(-1, 0, 0), (25, 0, 0), (0, 1, 0), (0, 0, 1), (1, 2, 0), (1, 0, 2), (2, -1, 0)],
)
def test_out_of_range_coords_are_rejected(coords):
    with pytest.raises(InvalidTileCoords):
        validate_tile_coords(*coords)


def test_tenant_id_never_becomes_a_tile_property():
    assert mvt_property_columns(_info()) == ["id", "titre"]


def test_integer_primary_key_becomes_the_mvt_feature_id():
    assert mvt_feature_id_column(_info(pk_type="integer")) == "id"


def test_non_integer_primary_key_yields_no_feature_id():
    # PostGIS ignore un feature_id non entier ; on préfère ne rien passer
    # plutôt que dépendre de sa clémence. Le shell retombe alors sur la
    # propriété de PK (cf. Task 10).
    assert mvt_feature_id_column(_info(pk_type="string")) is None


def test_sql_filters_on_the_untransformed_geometry_column():
    sql = build_mvt_sql(_quote, _info())
    # Le && porte sur t."geom" brut, jamais sur ST_Transform(t."geom", …) :
    # sinon l'index GiST de la Task 4 ne sert à rien (spec §3.2).
    assert 't."geom" && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)' in sql
    assert 'ST_Transform(t."geom", 3857) &&' not in sql


def test_sql_quotes_every_identifier_and_carries_the_columns():
    sql = build_mvt_sql(_quote, _info())
    assert 'public."demo_incidents"' in sql
    assert 't."titre" AS "titre"' in sql
    assert '"tenant_id"' not in sql
    assert "ST_AsMVT(" in sql
    assert "ST_AsMVTGeom(" in sql


def test_sql_drops_rows_whose_tile_geometry_is_null():
    assert "IS NOT NULL" in build_mvt_sql(_quote, _info())

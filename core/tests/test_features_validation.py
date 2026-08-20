# SPDX-License-Identifier: Apache-2.0
from app.collections.introspection import ColumnInfo, TableInfo
from app.features.validation import validate_feature

INFO = TableInfo(
    table_name="incidents",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="titre", type="string", required=True, max_length=200),
        ColumnInfo(
            name="gravite", type="enum", required=False, enum_values=["faible", "moyenne", "haute"]
        ),
        ColumnInfo(name="nb", type="integer", required=False),
        ColumnInfo(name="date_incident", type="date", required=False),
        ColumnInfo(name="resolu", type="boolean", required=False),
        ColumnInfo(name="payload", type="unsupported", required=False),
    ],
)


def _f(props, geometry=None):
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _codes(errors):
    return {(e["field"], e["code"]) for e in errors}


def test_valid_feature_passes():
    errors = validate_feature(
        INFO,
        _f(
            {
                "titre": "Nid de poule",
                "gravite": "haute",
                "nb": 3,
                "date_incident": "2026-07-10",
                "resolu": False,
            },
            {"type": "Point", "coordinates": [1.5, 45.2]},
        ),
    )
    assert errors == []


def test_not_a_feature():
    assert _codes(validate_feature(INFO, {"type": "Polygon"})) == {("", "invalid_feature")}


def test_unknown_property_and_pk_and_tenant_refused():
    errors = validate_feature(INFO, _f({"titre": "x", "inconnu": 1, "id": 9, "tenant_id": "y"}))
    assert ("inconnu", "unknown_property") in _codes(errors)
    assert ("id", "unknown_property") in _codes(errors)
    assert ("tenant_id", "unknown_property") in _codes(errors)


def test_missing_required():
    assert ("titre", "missing_required") in _codes(validate_feature(INFO, _f({"nb": 1})))


def test_type_checks():
    errors = validate_feature(
        INFO, _f({"titre": "x", "nb": "trois", "resolu": "oui", "date_incident": "pas-une-date"})
    )
    codes = _codes(errors)
    assert ("nb", "invalid_type") in codes
    assert ("resolu", "invalid_type") in codes
    assert ("date_incident", "invalid_type") in codes


def test_bool_is_not_an_integer():
    assert ("nb", "invalid_type") in _codes(validate_feature(INFO, _f({"titre": "x", "nb": True})))


def test_enum_and_unsupported():
    errors = validate_feature(INFO, _f({"titre": "x", "gravite": "extreme", "payload": {}}))
    assert ("gravite", "invalid_enum") in _codes(errors)
    assert ("payload", "unsupported_type") in _codes(errors)


def test_geometry_type_mismatch_and_unexpected():
    assert ("geometry", "geometry_mismatch") in _codes(
        validate_feature(INFO, _f({"titre": "x"}, {"type": "Polygon", "coordinates": []}))
    )
    no_geom = TableInfo(
        table_name="notes",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=None,
        columns=[ColumnInfo(name="titre", type="string", required=True)],
    )
    assert ("geometry", "unexpected_geometry") in _codes(
        validate_feature(no_geom, _f({"titre": "x"}, {"type": "Point", "coordinates": [0, 0]}))
    )


def test_geometry_is_optional():
    assert validate_feature(INFO, _f({"titre": "x"})) == []


def test_non_dict_geometry_is_error_not_crash():
    errors = validate_feature(INFO, _f({"titre": "x"}, "POINT(1 2)"))
    assert ("geometry", "geometry_mismatch") in _codes(errors)
    errors = validate_feature(INFO, _f({"titre": "x"}, []))
    assert ("geometry", "geometry_mismatch") in _codes(errors)


def test_null_properties_is_valid_rfc7946():
    errors = validate_feature(INFO, {"type": "Feature", "properties": None, "geometry": None})
    # properties:null = {} → seule l'exigence required s'applique
    assert _codes(errors) == {("titre", "missing_required")}

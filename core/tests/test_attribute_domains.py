# SPDX-License-Identifier: Apache-2.0
"""ARC-13 : domaines `list`/`range` et sous-types appliqués à l'écriture (pur, sans DB)."""

from dataclasses import replace

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.rules import apply_write_rules
from app.features.validation import validate_feature, validate_for_write

BASE = TableInfo(
    table_name="voirie",
    pk_column="id",
    geometry_column=None,
    geometry_type=None,
    srid=None,
    columns=[
        ColumnInfo(name="categorie", type="string", required=False),
        ColumnInfo(name="etat", type="string", required=False),
        ColumnInfo(name="vitesse", type="integer", required=False),
        ColumnInfo(name="largeur", type="number", required=False),
    ],
)
INFO = replace(
    BASE,
    domains={
        "etat": {"type": "list", "values": ["bon", "moyen", "mauvais"]},
        "largeur": {"type": "range", "min": 0, "max": 30},
    },
    subtypes={
        "field": "categorie",
        "items": [
            {
                "value": "route",
                "label": "Route",
                "defaults": {"vitesse": 50},
                "domains": {"vitesse": {"type": "range", "min": 30, "max": 90}},
            },
            {"value": "chemin", "label": "Chemin", "defaults": {"vitesse": 20}, "domains": {}},
        ],
    },
)


def _f(props):
    return {"type": "Feature", "properties": props, "geometry": None}


def _codes(errors):
    return {(e["field"], e["code"]) for e in errors}


def test_list_domain_rejects_outside_value():
    errs = validate_feature(INFO, _f({"etat": "ruiné"}))
    assert _codes(errs) == {("etat", "out_of_domain")}


def test_list_domain_accepts_inside_and_null():
    assert validate_feature(INFO, _f({"etat": "bon"})) == []
    assert validate_feature(INFO, _f({"etat": None})) == []


def test_range_domain_bounds_inclusive():
    assert validate_feature(INFO, _f({"largeur": 30})) == []
    assert validate_feature(INFO, _f({"largeur": 0})) == []
    assert _codes(validate_feature(INFO, _f({"largeur": 30.5}))) == {("largeur", "out_of_domain")}
    assert _codes(validate_feature(INFO, _f({"largeur": -1}))) == {("largeur", "out_of_domain")}


def test_subtype_value_must_be_declared():
    assert _codes(validate_feature(INFO, _f({"categorie": "autoroute"}))) == {
        ("categorie", "out_of_domain")
    }
    assert validate_feature(INFO, _f({"categorie": "route"})) == []


def test_subtype_domain_overrides_per_subtype():
    # vitesse 20 : hors domaine du sous-type "route" (30-90), accepté pour "chemin" (aucun domaine)
    assert _codes(validate_feature(INFO, _f({"categorie": "route", "vitesse": 20}))) == {
        ("vitesse", "out_of_domain")
    }
    assert validate_feature(INFO, _f({"categorie": "chemin", "vitesse": 20})) == []


def test_subtype_defaults_applied_when_missing_only():
    feat = _f({"categorie": "route"})
    apply_write_rules(INFO, feat)
    assert feat["properties"]["vitesse"] == 50
    feat = _f({"categorie": "route", "vitesse": 80})
    apply_write_rules(INFO, feat)
    assert feat["properties"]["vitesse"] == 80


def test_validate_for_write_applies_defaults_then_validates():
    feat = _f({"categorie": "chemin"})
    assert validate_for_write(INFO, feat) == []
    assert feat["properties"]["vitesse"] == 20


def test_no_domain_means_unchanged_behaviour():
    assert validate_feature(BASE, _f({"etat": "n'importe quoi"})) == []

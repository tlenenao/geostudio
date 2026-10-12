# SPDX-License-Identifier: Apache-2.0
"""ARC-14 : règles d'attributs CEL `calculation` / `constraint` (pur, sans DB)."""

from dataclasses import replace

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.cel_rules import cel_syntax_error
from app.features.validation import validate_for_write

BASE = TableInfo(
    table_name="parcelles",
    pk_column="id",
    geometry_column=None,
    geometry_type=None,
    srid=None,
    columns=[
        ColumnInfo(name="nom", type="string", required=False),
        ColumnInfo(name="surface", type="number", required=False),
        ColumnInfo(name="largeur", type="number", required=False),
        ColumnInfo(name="longueur", type="number", required=False),
        ColumnInfo(name="code", type="string", required=False),
    ],
)
RULES = [
    {
        "id": "surface-calc",
        "kind": "calculation",
        "field": "surface",
        "expression": "largeur * longueur",
        "mode": "default",
    },
    {
        "id": "code-calc",
        "kind": "calculation",
        "field": "code",
        "expression": "'P-' + nom",
        "mode": "derived",
    },
    {
        "id": "surface-positive",
        "kind": "constraint",
        "field": "surface",
        "expression": "surface > 0.0",
        "message": "La surface doit être strictement positive.",
    },
    {
        "id": "batch-only",
        "kind": "batch",
        "expression": "size(nom) < 3",
        "message": "Nom trop long (contrôle différé).",
    },
]
INFO = replace(BASE, rules=RULES)


def _f(props):
    return {"type": "Feature", "properties": props, "geometry": None}


def test_constraint_rejects_with_message():
    errs = validate_for_write(INFO, _f({"nom": "a", "surface": -2.0}))
    assert errs == [
        {
            "field": "surface",
            "code": "constraint_violation",
            "message": "La surface doit être strictement positive.",
        }
    ]


def test_constraint_passes_when_satisfied():
    assert validate_for_write(INFO, _f({"nom": "a", "surface": 4.0})) == []


def test_calculation_feeds_field_at_insert_then_constraint_sees_it():
    feat = _f({"nom": "a", "largeur": 2.0, "longueur": 3.0})
    assert validate_for_write(INFO, feat) == []
    assert feat["properties"]["surface"] == 6.0
    feat = _f({"nom": "a", "largeur": 0.0, "longueur": 3.0})  # surface calculée = 0 : refusée
    assert [e["code"] for e in validate_for_write(INFO, feat)] == ["constraint_violation"]


def test_default_calculation_does_not_override_given_value_but_derived_does():
    feat = _f({"nom": "a", "largeur": 2.0, "longueur": 3.0, "surface": 99.0, "code": "x"})
    validate_for_write(INFO, feat)
    assert feat["properties"]["surface"] == 99.0  # mode default : valeur fournie conservée
    assert feat["properties"]["code"] == "P-a"  # mode derived : toujours recalculé


def test_null_operand_is_not_a_violation():
    # surface absente et non calculable (largeur/longueur nulles) : règle non applicable
    assert validate_for_write(INFO, _f({"nom": "a"})) == []


def test_batch_rules_are_not_enforced_at_write():
    assert validate_for_write(INFO, _f({"nom": "abcdef", "surface": 1.0})) == []


def test_no_rules_means_unchanged_behaviour():
    assert validate_for_write(BASE, _f({"nom": "a", "surface": -2.0})) == []


def test_syntax_check():
    assert cel_syntax_error("surface > 0.0") is None
    assert cel_syntax_error("surface >") is not None

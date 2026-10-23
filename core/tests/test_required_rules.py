# SPDX-License-Identifier: Apache-2.0
"""L8 T4 : `required` (règle CEL générée) et géométrie requise, imposés par le point d'entrée
commun de tous les chemins d'écriture (REST, dépôt public, approbation, import, pipeline, MCP)."""

import ast
from dataclasses import replace
from pathlib import Path

from app.collections.introspection import ColumnInfo, TableInfo
from app.features.validation import validate_for_write

INFO = TableInfo(
    table_name="releves",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="nom", type="string", required=False)],
    rules=[
        {
            "id": "required-nom",
            "kind": "constraint",
            "field": "nom",
            "expression": "nom != null && nom != ''",
            "message": "Le champ « nom » est obligatoire.",
        }
    ],
)
POINT = {"type": "Point", "coordinates": [1.0, 45.0]}


def _f(props, geometry=POINT):
    return {"type": "Feature", "properties": props, "geometry": geometry}


def test_missing_required_property_is_rejected_with_field_and_message():
    for props in ({}, {"nom": None}, {"nom": ""}):
        errs = validate_for_write(INFO, _f(props))
        assert [(e["field"], e["code"]) for e in errs] == [("nom", "constraint_violation")], props
        assert "obligatoire" in errs[0]["message"]


def test_present_required_property_passes():
    assert validate_for_write(INFO, _f({"nom": "a"})) == []


def test_geometry_required_flag():
    strict = replace(INFO, geometry_required=True)
    errs = validate_for_write(strict, _f({"nom": "a"}, geometry=None))
    assert [(e["field"], e["code"]) for e in errs] == [("geometry", "missing_required")]
    assert validate_for_write(strict, _f({"nom": "a"})) == []
    # défaut : géométrie toujours optionnelle (comportement historique)
    assert validate_for_write(INFO, _f({"nom": "a"}, geometry=None)) == []


def test_every_write_path_goes_through_validate_for_write():
    # les chemins d'écriture partagent le même point d'entrée : un seul endroit à garder
    root = Path(__file__).resolve().parent.parent / "app"
    for rel in (
        "features/routes.py",
        "public_submit/routes.py",
        "ingestion/importer.py",
        "pipelines/collection_writer.py",
    ):
        tree = ast.parse((root / rel).read_text())
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "validate_for_write" in names, rel

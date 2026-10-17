# SPDX-License-Identifier: Apache-2.0
"""Revue finale de branche FME : gardes transverses parcourant tout le registre `OPERATIONS`
(I1 : classement de rejeu des writers ; I4 : aucune colonne de sortie ne remplace `geometry`)."""

import re
import typing

import pytest
from pydantic import ValidationError

from app.configs.schemas import EXTERNAL_EFFECT_WRITER_OPS
from app.pipelines.ops.contracts import OPERATIONS

# --- I1 ---------------------------------------------------------------------------------

# Writers rejouables par retry/reprise, avec la raison (tout writer absent d'ici doit être
# dans EXTERNAL_EFFECT_WRITER_OPS — un nouveau writer force donc une décision explicite).
REPLAY_SAFE_WRITERS = {
    "writer.collection": "transaction du run, annulée à l'échec (append compris, AUD-083)",
    "writer.dataset": "transaction du run, annulée à l'échec (append compris, AUD-083)",
    "writer.export": "objet d'export régénéré",
    "writer.file": "écrase le même fichier local",
    "writer.topojson": "écrase le même fichier local",
    "writer.ftp": "écrase le même chemin distant (fichier .part puis renommage)",
    "writer.connector.postgres.update": "UPDATE borné aux clés : idempotent",
    "writer.connector.postgres.delete": "DELETE borné aux clés : idempotent",
}


def test_every_writer_is_classified_for_replay():
    writers = {k for k, c in OPERATIONS.items() if c.kind == "writer"}
    assert not (EXTERNAL_EFFECT_WRITER_OPS & set(REPLAY_SAFE_WRITERS))
    assert writers == EXTERNAL_EFFECT_WRITER_OPS | set(REPLAY_SAFE_WRITERS)


# --- I4 ---------------------------------------------------------------------------------

_COLUMN_FIELD = re.compile(r"(Column|^column)$")

# Champs `*Column`/`column` LUS (jamais écrits) : `geometry` y est inoffensif.
INPUT_FIELDS = {
    "itemColumn",
    "urlColumn",
    "valueColumn",
    "sourceColumn",
    "typeColumn",
    "destLatColumn",
    "destLonColumn",
    "geometryColumn",  # AUD-082 : colonne source décodée des readers connecteurs
    ("transform.attributeRangeFilter", "column"),
    ("transform.mgrsToLatLong", "column"),  # écrit `geometry` par conception
    ("transform.textEncoder", "column"),
    ("transform.textDecoder", "column"),
    ("transform.htmlExtractor", "column"),
    ("transform.explodeList", "column"),
    ("transform.exposeAttributes", "column"),
}

# Ops du socle (antérieures au chantier FME) dont la colonne de sortie n'est pas gardée :
# `transform.derive` remplace délibérément une colonne par une expression (y compris la
# géométrie) ; les autres restent une dette hors périmètre de la revue FME.
BASE_UNGUARDED = {
    ("transform.derive", "column"),
    ("transform.concatCoordinates", "xColumn"),
    ("transform.concatCoordinates", "yColumn"),
    ("transform.extractCoordinates", "xColumn"),
    ("transform.extractCoordinates", "yColumn"),
    ("transform.reprojectAttribute", "xColumn"),
    ("transform.reprojectAttribute", "yColumn"),
    ("transform.extractElevation", "column"),
    ("transform.extractDimension", "column"),
    ("transform.countVertices", "column"),
    ("transform.extractSrid", "column"),
    ("transform.formatCoordinates", "targetColumn"),
    ("transform.validateAttributes", "nonNullResultColumn"),
    ("transform.validateAttributes", "uniqueResultColumn"),
    ("transform.detectChanges", "statusColumn"),
    ("transform.mergeChildren", "childrenColumn"),
    ("transform.httpCall", "responseColumn"),
    ("transform.httpCall", "statusCodeColumn"),
    ("transform.httpCall", "statusColumn"),
    ("transform.httpCall", "errorColumn"),
}


def _is_str(annotation) -> bool:
    args = typing.get_args(annotation)
    return annotation is str or (bool(args) and str in args)


def _output_fields():
    for op, c in OPERATIONS.items():
        if c.kind == "writer":  # colonnes de writers = colonnes lues (corps, clés…)
            continue
        for f, info in c.params_schema.model_fields.items():
            if not _COLUMN_FIELD.search(f) or not _is_str(info.annotation):
                continue
            if f in INPUT_FIELDS or (op, f) in INPUT_FIELDS or (op, f) in BASE_UNGUARDED:
                continue
            yield op, f


def test_output_fields_are_found():
    assert ("transform.textEncoder", "outputColumn") in set(_output_fields())


@pytest.mark.parametrize("op, field", sorted(_output_fields()))
@pytest.mark.parametrize("name", ["geometry", "GEOMETRY", ""])
def test_no_op_output_param_accepts_geometry(op, field, name):
    with pytest.raises(ValidationError) as exc:
        OPERATIONS[op].params_schema.model_validate({field: name})
    assert any(
        e["loc"][:1] == (field,) and e["type"] == "value_error" for e in exc.value.errors()
    ), exc.value.errors()

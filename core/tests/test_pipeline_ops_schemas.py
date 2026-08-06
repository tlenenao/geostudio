# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import OP_KINDS, OP_PARAMS, ops_catalog, parse_op_params


def test_all_eight_phase1_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


@pytest.mark.parametrize(
    "op,kind",
    [
        ("reader.collection", "reader"),
        ("transform.filter", "transform"),
        ("transform.select", "transform"),
        ("transform.derive", "transform"),
        ("transform.aggregate", "transform"),
        ("transform.join", "transform"),
        ("writer.collection", "writer"),
        ("writer.export", "writer"),
    ],
)
def test_op_kind_matches(op, kind):
    assert OP_KINDS[op] == kind


def test_parse_op_params_reader_collection():
    params = parse_op_params("reader.collection", {"collectionId": "villes"})
    assert params.collectionId == "villes"


def test_parse_op_params_missing_required_field_raises():
    with pytest.raises(ValidationError):
        parse_op_params("reader.collection", {})


def test_parse_op_params_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown op"):
        parse_op_params("transform.does-not-exist", {})


def test_transform_join_defaults_how_to_inner():
    params = parse_op_params("transform.join", {"withCollectionId": "x", "on": "code"})
    assert params.how == "inner"


def test_writer_export_requires_format_and_key():
    params = parse_op_params("writer.export", {"format": "csv", "key": "out.csv"})
    assert params.format == "csv"
    assert params.key == "out.csv"
    with pytest.raises(ValidationError):
        parse_op_params("writer.export", {"key": "out.csv"})


def test_ops_catalog_exposes_json_schema_per_op():
    catalog = ops_catalog()
    assert set(catalog) == set(OP_PARAMS)
    for op, entry in catalog.items():
        assert entry["kind"] == OP_KINDS[op]
        assert "properties" in entry["paramsSchema"]


def test_collection_referencing_fields_carry_collection_id_format_hint():
    catalog = ops_catalog()
    assert catalog["reader.collection"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"
    assert catalog["writer.collection"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"
    assert catalog["transform.join"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"


def test_non_collection_fields_carry_no_format_hint():
    catalog = ops_catalog()
    assert "format" not in catalog["transform.filter"]["paramsSchema"]["properties"]["expr"]
    assert "format" not in catalog["transform.join"]["paramsSchema"]["properties"]["on"]

# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import OP_KINDS, OP_PARAMS, ops_catalog, parse_op_params


def test_all_eight_phase1_ops_are_registered():
    # Phase 1 ops still present (this test continues to verify backward compat)
    phase1_ops = {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
    }
    assert phase1_ops.issubset(set(OP_PARAMS))
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


def test_all_fourteen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
        "transform.buffer", "transform.reproject", "transform.intersection",
        "transform.countWithin", "transform.h3Aggregate", "writer.dataset",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


@pytest.mark.parametrize(
    "op,kind",
    [
        ("transform.buffer", "transform"),
        ("transform.reproject", "transform"),
        ("transform.intersection", "transform"),
        ("transform.countWithin", "transform"),
        ("transform.h3Aggregate", "transform"),
        ("writer.dataset", "writer"),
    ],
)
def test_new_op_kind_matches(op, kind):
    assert OP_KINDS[op] == kind


def test_transform_buffer_defaults_unit_to_meters():
    params = parse_op_params("transform.buffer", {"distance": 500})
    assert params.unit == "meters"
    assert params.distance == 500


def test_transform_buffer_rejects_missing_distance():
    with pytest.raises(ValidationError):
        parse_op_params("transform.buffer", {})


def test_transform_reproject_accepts_epsg_pattern():
    params = parse_op_params("transform.reproject", {"targetCrs": "EPSG:3857"})
    assert params.targetCrs == "EPSG:3857"


def test_transform_reproject_rejects_malformed_crs():
    with pytest.raises(ValidationError):
        parse_op_params("transform.reproject", {"targetCrs": "not-a-crs"})


def test_transform_intersection_defaults():
    params = parse_op_params(
        "transform.intersection", {"withCollectionId": "x"},
    )
    assert params.how == "inner"
    assert params.outputGeometry == "left"


def test_transform_count_within_defaults():
    params = parse_op_params(
        "transform.countWithin", {"withCollectionId": "x"},
    )
    assert params.countColumn == "count"
    assert params.predicate == "intersects"


def test_transform_h3_aggregate_requires_resolution_and_metrics():
    params = parse_op_params(
        "transform.h3Aggregate", {"resolution": 9, "metrics": {"n": "COUNT(*)"}},
    )
    assert params.resolution == 9
    assert params.metrics == {"n": "COUNT(*)"}
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"metrics": {}})


def test_transform_h3_aggregate_rejects_resolution_out_of_bounds():
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"resolution": 16, "metrics": {}})
    with pytest.raises(ValidationError):
        parse_op_params("transform.h3Aggregate", {"resolution": -1, "metrics": {}})


def test_writer_dataset_requires_title_when_dataset_id_absent():
    params = parse_op_params(
        "writer.dataset", {"collectionId": "c1", "title": "My dataset"},
    )
    assert params.datasetId is None
    assert params.title == "My dataset"
    with pytest.raises(ValidationError):
        parse_op_params("writer.dataset", {"collectionId": "c1"})


def test_writer_dataset_allows_missing_title_when_dataset_id_present():
    params = parse_op_params(
        "writer.dataset", {"collectionId": "c1", "datasetId": "d1"},
    )
    assert params.datasetId == "d1"
    assert params.title is None


def test_new_collection_referencing_fields_carry_collection_id_format_hint():
    catalog = ops_catalog()
    assert catalog["transform.intersection"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"
    assert catalog["transform.countWithin"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"
    assert catalog["writer.dataset"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"

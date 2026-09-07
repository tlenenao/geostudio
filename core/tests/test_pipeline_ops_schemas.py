# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import (
    OP_KINDS,
    OP_PARAMS,
    WriterCollectionParams,
    WriterDatasetParams,
    ops_catalog,
    parse_op_params,
)


def test_all_eight_phase1_ops_are_registered():
    # Phase 1 ops still present (this test continues to verify backward compat)
    phase1_ops = {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "writer.collection",
        "writer.export",
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
    assert (
        catalog["reader.collection"]["paramsSchema"]["properties"]["collectionId"]["format"]
        == "collection-id"
    )
    assert (
        catalog["writer.collection"]["paramsSchema"]["properties"]["collectionId"]["format"]
        == "collection-id"
    )
    assert (
        catalog["transform.join"]["paramsSchema"]["properties"]["withCollectionId"]["format"]
        == "collection-id"
    )


def test_non_collection_fields_carry_no_format_hint():
    catalog = ops_catalog()
    assert "format" not in catalog["transform.filter"]["paramsSchema"]["properties"]["expr"]
    assert "format" not in catalog["transform.join"]["paramsSchema"]["properties"]["on"]


def test_all_nineteen_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "writer.collection",
        "writer.export",
        "transform.buffer",
        "transform.reproject",
        "transform.intersection",
        "transform.countWithin",
        "transform.h3Aggregate",
        "writer.dataset",
        "transform.qgis",
        "reader.connector.rest",
        "reader.connector.postgres",
        "transform.merge",
        "reader.connector.snowflake",
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
        "transform.intersection",
        {"withCollectionId": "x"},
    )
    assert params.how == "inner"
    assert params.outputGeometry == "left"


def test_transform_count_within_defaults():
    params = parse_op_params(
        "transform.countWithin",
        {"withCollectionId": "x"},
    )
    assert params.countColumn == "count"
    assert params.predicate == "intersects"


def test_transform_h3_aggregate_requires_resolution_and_metrics():
    params = parse_op_params(
        "transform.h3Aggregate",
        {"resolution": 9, "metrics": {"n": "COUNT(*)"}},
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
        "writer.dataset",
        {"collectionId": "c1", "title": "My dataset"},
    )
    assert params.datasetId is None
    assert params.title == "My dataset"
    with pytest.raises(ValidationError):
        parse_op_params("writer.dataset", {"collectionId": "c1"})


def test_writer_dataset_allows_missing_title_when_dataset_id_present():
    params = parse_op_params(
        "writer.dataset",
        {"collectionId": "c1", "datasetId": "d1"},
    )
    assert params.datasetId == "d1"
    assert params.title is None


def test_new_collection_referencing_fields_carry_collection_id_format_hint():
    catalog = ops_catalog()
    assert (
        catalog["transform.intersection"]["paramsSchema"]["properties"]["withCollectionId"][
            "format"
        ]
        == "collection-id"
    )
    assert (
        catalog["transform.countWithin"]["paramsSchema"]["properties"]["withCollectionId"]["format"]
        == "collection-id"
    )
    assert (
        catalog["writer.dataset"]["paramsSchema"]["properties"]["collectionId"]["format"]
        == "collection-id"
    )


def test_fifteenth_op_is_registered():
    assert "transform.qgis" in OP_PARAMS
    assert "transform.qgis" in OP_KINDS
    assert OP_KINDS["transform.qgis"] == "transform"


def test_transform_qgis_accepts_allowlisted_id_with_required_params():
    params = parse_op_params(
        "transform.qgis",
        {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}},
    )
    assert params.algorithmId == "native:centroids"
    assert params.params == {"ALL_PARTS": False}
    assert params.outputSrid is None


def test_transform_qgis_rejects_non_allowlisted_id():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:totallymadeup", "params": {}},
        )


def test_transform_qgis_rejects_missing_required_param():
    # native:centroids requires ALL_PARTS beyond INPUT/OUTPUT (design Task 2 —
    # INPUT/OUTPUT are runtime-injected, never authored, cf. spike finding
    # in test_pipeline_qgis_algorithms.py::test_centroids_required_params_...).
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {"algorithmId": "native:centroids", "params": {}},
        )


def test_transform_qgis_does_not_require_input_output_in_params():
    # INPUT/OUTPUT are required by native:simplifygeometries' own schema but
    # are filled in by the runtime (scratch file paths), never by the author.
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "native:simplifygeometries",
            "params": {"METHOD": 0, "TOLERANCE": 1.0},
        },
    )
    assert "INPUT" not in params.params
    assert "OUTPUT" not in params.params


def test_transform_qgis_accepts_optional_output_srid():
    params = parse_op_params(
        "transform.qgis",
        {
            "algorithmId": "gdal:warpreproject",
            "params": {
                "TARGET_CRS": "EPSG:2154",
                "DATA_TYPE": 0,
                "MULTITHREADING": False,
                "RESAMPLING": 0,
            },
            "outputSrid": "EPSG:2154",
        },
    )
    assert params.outputSrid == "EPSG:2154"


def test_transform_qgis_rejects_malformed_output_srid():
    with pytest.raises(ValidationError):
        parse_op_params(
            "transform.qgis",
            {
                "algorithmId": "native:dissolve",
                "params": {"SEPARATE_DISJOINT": False},
                "outputSrid": "not-a-crs",
            },
        )


def test_reader_connector_ops_are_kind_reader():
    assert OP_KINDS["reader.connector.rest"] == "reader"
    assert OP_KINDS["reader.connector.postgres"] == "reader"


def test_reader_connector_rest_minimal_params():
    params = parse_op_params("reader.connector.rest", {"baseUrl": "https://api.example.com/"})
    assert params.path == ""
    assert params.method == "GET"
    assert params.query == {}
    assert params.headers == {}
    assert params.recordsPath is None
    assert params.paginator == "none"
    assert params.paginatorConfig == {}
    assert params.secretName is None


def test_reader_connector_rest_rejects_non_http_base_url():
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.rest", {"baseUrl": "ftp://example.com/"})


def test_reader_connector_rest_full_params():
    params = parse_op_params(
        "reader.connector.rest",
        {
            "baseUrl": "https://api.example.com/",
            "path": "v1/items",
            "method": "POST",
            "query": {"limit": "100"},
            "headers": {"User-Agent": "geostudio"},
            "recordsPath": "data.items",
            "paginator": "page_number",
            "paginatorConfig": {"pageParam": "page"},
            "secretName": "my-api-key",
        },
    )
    assert params.path == "v1/items"
    assert params.method == "POST"
    assert params.recordsPath == "data.items"
    assert params.paginator == "page_number"
    assert params.secretName == "my-api-key"


def test_reader_connector_rest_rejects_unknown_paginator():
    with pytest.raises(ValidationError):
        parse_op_params(
            "reader.connector.rest",
            {
                "baseUrl": "https://api.example.com/",
                "paginator": "not-a-paginator",
            },
        )


def test_reader_connector_postgres_requires_secret_name_and_query():
    params = parse_op_params(
        "reader.connector.postgres",
        {"secretName": "warehouse-pg", "query": "SELECT * FROM towns"},
    )
    assert params.secretName == "warehouse-pg"
    assert params.query == "SELECT * FROM towns"
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"query": "SELECT 1"})
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.postgres", {"secretName": "x"})


def test_reader_connector_ops_appear_in_catalog():
    catalog = ops_catalog()
    assert catalog["reader.connector.rest"]["kind"] == "reader"
    assert "baseUrl" in catalog["reader.connector.rest"]["paramsSchema"]["properties"]
    assert catalog["reader.connector.postgres"]["kind"] == "reader"
    assert "query" in catalog["reader.connector.postgres"]["paramsSchema"]["properties"]


def test_transform_join_with_collection_id_is_now_optional():
    params = parse_op_params("transform.join", {"on": "code"})
    assert params.withCollectionId is None


def test_transform_intersection_with_collection_id_is_now_optional():
    params = parse_op_params("transform.intersection", {})
    assert params.withCollectionId is None


def test_transform_count_within_with_collection_id_is_now_optional():
    params = parse_op_params("transform.countWithin", {})
    assert params.withCollectionId is None


def test_transform_merge_accepts_no_params():
    params = parse_op_params("transform.merge", {})
    assert params.withCollectionId is None


def test_transform_merge_accepts_with_collection_id():
    params = parse_op_params("transform.merge", {"withCollectionId": "x"})
    assert params.withCollectionId == "x"


def test_transform_merge_is_kind_transform_and_registered():
    assert OP_KINDS["transform.merge"] == "transform"
    assert "transform.merge" in OP_PARAMS


def test_binary_ops_accept_secondary_input_in_catalog():
    catalog = ops_catalog()
    for op in (
        "transform.join",
        "transform.intersection",
        "transform.countWithin",
        "transform.merge",
    ):
        assert catalog[op]["acceptsSecondaryInput"] is True


def test_non_binary_ops_do_not_accept_secondary_input_in_catalog():
    catalog = ops_catalog()
    for op in ("reader.collection", "transform.filter", "writer.collection", "transform.buffer"):
        assert catalog[op]["acceptsSecondaryInput"] is False


def test_binary_ops_set_matches_catalog_flag():
    from app.pipelines.ops.schemas import BINARY_OPS

    assert BINARY_OPS == {
        "transform.join",
        "transform.intersection",
        "transform.countWithin",
        "transform.merge",
    }


def test_writer_collection_mode_defaults_to_append():
    params = parse_op_params("writer.collection", {"collectionId": "c1"})
    assert params.mode == "append"


def test_writer_collection_mode_accepts_replace():
    params = parse_op_params("writer.collection", {"collectionId": "c1", "mode": "replace"})
    assert params.mode == "replace"


def test_writer_collection_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        parse_op_params("writer.collection", {"collectionId": "c1", "mode": "overwrite"})


def test_writer_dataset_mode_defaults_to_append():
    params = parse_op_params("writer.dataset", {"collectionId": "c1", "title": "My dataset"})
    assert params.mode == "append"


def test_writer_dataset_mode_accepts_replace():
    params = parse_op_params(
        "writer.dataset",
        {"collectionId": "c1", "title": "My dataset", "mode": "replace"},
    )
    assert params.mode == "replace"


def test_writer_dataset_mode_rejects_unknown_value():
    with pytest.raises(ValidationError):
        parse_op_params(
            "writer.dataset",
            {"collectionId": "c1", "title": "My dataset", "mode": "overwrite"},
        )


def test_writer_collection_mode_description_reaches_json_schema():
    # Revue finale d'intégration SP-14o (Important 5) : la description doit
    # atteindre model_json_schema() — c'est ce que ops_catalog() (donc
    # l'inspecteur générique du canvas) expose réellement.
    schema = WriterCollectionParams.model_json_schema()
    assert schema["properties"]["mode"]["description"]


def test_writer_dataset_mode_description_reaches_json_schema():
    schema = WriterDatasetParams.model_json_schema()
    assert schema["properties"]["mode"]["description"]


def test_writer_collection_mode_description_reaches_ops_catalog():
    # ops_catalog() (consommé par GET /pipelines/ops puis l'inspecteur du
    # canvas) doit exposer la même description, pas seulement le modèle nu.
    catalog = ops_catalog()
    assert catalog["writer.collection"]["paramsSchema"]["properties"]["mode"]["description"]
    assert catalog["writer.dataset"]["paramsSchema"]["properties"]["mode"]["description"]


def test_reader_connector_rest_secret_name_has_secret_name_format():
    # GAP-43 : secretName n'a aujourd'hui aucun format déclaré, retombe dans
    # un <input type="text"> libre côté shell.
    schema = ops_catalog()["reader.connector.rest"]["paramsSchema"]
    assert schema["properties"]["secretName"]["format"] == "secret-name"


def test_reader_connector_postgres_secret_name_has_secret_name_format():
    schema = ops_catalog()["reader.connector.postgres"]["paramsSchema"]
    assert schema["properties"]["secretName"]["format"] == "secret-name"


def test_reader_connector_snowflake_is_kind_reader():
    assert OP_KINDS["reader.connector.snowflake"] == "reader"


def test_reader_connector_snowflake_requires_secret_name_and_query():
    params = parse_op_params(
        "reader.connector.snowflake",
        {"secretName": "warehouse-sf", "query": "SELECT * FROM towns"},
    )
    assert params.secretName == "warehouse-sf"
    assert params.query == "SELECT * FROM towns"
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.snowflake", {"query": "SELECT 1"})
    with pytest.raises(ValidationError):
        parse_op_params("reader.connector.snowflake", {"secretName": "x"})


def test_reader_connector_snowflake_appears_in_catalog_with_secret_name_format_hint():
    catalog = ops_catalog()
    assert catalog["reader.connector.snowflake"]["kind"] == "reader"
    props = catalog["reader.connector.snowflake"]["paramsSchema"]["properties"]
    assert "query" in props
    assert props["secretName"]["format"] == "secret-name"


def test_reader_connector_postgres_description_documents_redshift_compatibility():
    # GAP-16 §9 : seul le PREMIER PARAGRAPHE du docstring de classe devient le
    # paramsSchema.description exposé par GET /pipelines/ops (revue finale I2,
    # cf. test_op_tooltip_descriptions_hide_developer_jargon ci-dessous) — ce
    # test falsifie que la phrase Redshift, gardée dans ce premier paragraphe,
    # propage réellement jusqu'au catalogue, pas seulement jusqu'à un
    # commentaire de code invisible à l'auteur du pipeline.
    catalog = ops_catalog()
    description = catalog["reader.connector.postgres"]["paramsSchema"]["description"]
    assert "Redshift" in description


# Revue finale de branche GAP-16, Important I2 : le docstring Python complet
# de 5 ops (noms de classes, chemins de module, renvois "design §n"/"SPnn")
# atteignait tel quel le tooltip de palette (paramsSchema.description, lu par
# shell/src/builder/pipeline/PipelinePalette.tsx) — jargon développeur exposé
# tel quel à l'auteur de pipeline. Seul le premier paragraphe du docstring de
# classe doit atteindre le catalogue ; le reste continue de documenter les
# développeurs (implémentation, limites, renvois de design) sans être exposé.
_DEV_JARGON_MARKERS = ("app.pipelines", "design", "SP-1", "GAP-16", "§")


@pytest.mark.parametrize(
    "op",
    [
        "reader.connector.snowflake",
        "reader.connector.postgres",
        "reader.connector.rest",
        "transform.qgis",
        "transform.merge",
    ],
)
def test_op_tooltip_descriptions_hide_developer_jargon(op):
    catalog = ops_catalog()
    description = catalog[op]["paramsSchema"]["description"]
    assert description, f"{op} should still expose a user-facing description"
    for marker in _DEV_JARGON_MARKERS:
        assert marker not in description, (
            f"{op}: developer jargon marker {marker!r} leaked into the "
            f"user-facing tooltip description: {description!r}"
        )
    # Le docstring Python complet (non tronqué), lui, garde le détail
    # développeur — la classe reste une documentation développeur complète.
    model = OP_PARAMS[op]
    assert model.__doc__ is not None
    assert any(marker in model.__doc__ for marker in _DEV_JARGON_MARKERS), (
        f"{op}: expected the full class docstring to retain developer detail"
    )

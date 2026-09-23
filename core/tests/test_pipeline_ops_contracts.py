# SPDX-License-Identifier: Apache-2.0
import pytest

from app.pipelines.ops.contracts import OperationContract
from app.pipelines.ops.schemas import TransformFilterParams


def test_copyleft_engine_requires_sidecar_execution_model():
    with pytest.raises(ValueError, match="execution_model='sidecar'"):
        OperationContract(
            op="transform.fake-copyleft",
            kind="transform",
            params_schema=TransformFilterParams,
            engine="fake-gpl-engine",
            is_copyleft=True,
            execution_model="in_process",
        )


def test_copyleft_engine_with_sidecar_execution_model_is_accepted():
    contract = OperationContract(
        op="transform.fake-copyleft",
        kind="transform",
        params_schema=TransformFilterParams,
        engine="fake-gpl-engine",
        is_copyleft=True,
        execution_model="sidecar",
    )
    assert contract.execution_model == "sidecar"
    assert contract.is_copyleft is True


def test_non_copyleft_engine_defaults_to_in_process_and_no_copyleft():
    contract = OperationContract(
        op="transform.filter",
        kind="transform",
        params_schema=TransformFilterParams,
    )
    assert contract.execution_model == "in_process"
    assert contract.is_copyleft is False
    assert contract.engine is None
    assert contract.compile is None
    assert contract.output_srid is None


def test_operations_registry_has_exactly_the_fifty_one_known_ops():
    from app.pipelines.ops.contracts import OPERATIONS

    assert set(OPERATIONS) == {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "transform.buffer",
        "transform.reproject",
        "transform.intersection",
        "transform.countWithin",
        "transform.h3Aggregate",
        "transform.qgis",
        "writer.collection",
        "writer.export",
        "writer.dataset",
        "reader.connector.rest",
        "reader.connector.postgres",
        "reader.connector.snowflake",
        "reader.connector.bigquery",
        "reader.connector.mssql",
        "reader.connector.oracle",
        "reader.connector.blob",
        "transform.merge",
        "transform.swapCoordinates",
        "transform.translateGeometry",
        "transform.scaleGeometry",
        "transform.rotateGeometry",
        "transform.createGeometry",
        "transform.concatCoordinates",
        "transform.roundCoordinates",
        "transform.extractElevation",
        "transform.extractDimension",
        "transform.countVertices",
        "transform.extractCoordinates",
        "transform.extractSrid",
        "transform.setSrid",
        "transform.reprojectAttribute",
        "transform.formatCoordinates",
        "reader.file",
        "writer.file",
        "transform.bulkRemoveAttributes",
        "transform.bulkRenameAttributes",
        "transform.scanSchema",
        "transform.explodeList",
        "transform.explodeGeometry",
        "transform.centroid",
        "transform.convexHull",
        "transform.simplify",
        "transform.boundingGeometry",
        "transform.exposeAttributes",
        "transform.validateAttributes",
        "transform.sort",
        "transform.detectChanges",
        "transform.mergeChildren",
        "transform.mapSchema",
        "transform.snapToLayer",
        "transform.resolveOverlaps",
        "transform.triangulate",
        "transform.densify",
    }


def test_qgis_operation_contract_declares_copyleft_sidecar_metadata():
    from app.pipelines.ops.contracts import OPERATIONS

    contract = OPERATIONS["transform.qgis"]
    assert contract.engine == "qgis"
    assert contract.engine_license == "GPL-2.0-or-later (QGIS)"
    assert contract.is_copyleft is True
    assert contract.execution_model == "sidecar"
    assert contract.compile is None
    assert contract.output_srid is not None


def test_connector_and_writer_ops_are_not_classified_by_engine():
    from app.pipelines.ops.contracts import OPERATIONS

    for op in (
        "reader.collection",
        "reader.connector.rest",
        "reader.connector.postgres",
        "reader.connector.snowflake",
        "reader.connector.bigquery",
        "reader.connector.mssql",
        "reader.connector.oracle",
        "reader.connector.blob",
        "writer.collection",
        "writer.export",
        "writer.dataset",
    ):
        contract = OPERATIONS[op]
        assert contract.engine is None
        assert contract.is_copyleft is False
        assert contract.execution_model == "in_process"


def test_operation_contract_accepts_explicit_exchange_value():
    contract = OperationContract(
        op="transform.fake-native",
        kind="transform",
        params_schema=TransformFilterParams,
        exchange="arrow_stream",
    )
    assert contract.exchange == "arrow_stream"


def test_all_operations_default_exchange_to_none():
    from app.pipelines.ops.contracts import OPERATIONS

    for op, contract in OPERATIONS.items():
        assert contract.exchange is None, op


def test_ops_catalog_never_exposes_the_exchange_field():
    # Garde de régression (design §2 : "exchange n'entre jamais dans
    # ops_catalog()") — passe déjà avant ce champ puisque ops_catalog()
    # construit un dict à 3 clés fixes, mais documente et verrouille la
    # garantie plutôt que de la supposer.
    from app.pipelines.ops.contracts import ops_catalog

    catalog = ops_catalog()
    for op, entry in catalog.items():
        assert set(entry) == {"kind", "paramsSchema", "acceptsSecondaryInput"}, op


def test_operations_registry_has_fifty_one_entries_after_vague_2():
    from app.pipelines.ops.contracts import OPERATIONS

    assert len(OPERATIONS) == 59

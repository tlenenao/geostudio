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


def test_operations_registry_has_exactly_the_known_ops():
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
        "transform.minimumBoundingCircle",
    }


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


def test_operations_registry_has_59_entries():
    from app.pipelines.ops.contracts import OPERATIONS

    assert len(OPERATIONS) == 59


def test_binary_ops_are_covered_by_the_parallel_tables():
    # REV-198 : runtime._JOIN_PARAM_MODELS est dérivé de BINARY_OPS ;
    # config_validation._COLLECTION_PARAM_FIELD (qui contient aussi reader/writer) doit
    # désigner `withCollectionId` pour chaque op binaire.
    from app.pipelines.config_validation import _COLLECTION_PARAM_FIELD
    from app.pipelines.ops.contracts import BINARY_OPS, OP_PARAMS
    from app.pipelines.runtime import _JOIN_PARAM_MODELS

    assert set(_JOIN_PARAM_MODELS) == BINARY_OPS
    assert all(_JOIN_PARAM_MODELS[op] is OP_PARAMS[op] for op in BINARY_OPS)
    with_collection = {op for op, f in _COLLECTION_PARAM_FIELD.items() if f == "withCollectionId"}
    assert BINARY_OPS <= with_collection


def test_compile_and_execute_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutuellement exclusifs"):
        OperationContract(
            op="transform.fake-both",
            kind="transform",
            params_schema=TransformFilterParams,
            compile=lambda params, **kw: "SELECT 1",
            execute=lambda conn, **kw: None,
        )


def test_every_registered_transform_has_exactly_one_of_compile_or_execute():
    from app.pipelines.ops.contracts import OPERATIONS

    for op, contract in OPERATIONS.items():
        has_both_or_none = (contract.compile is not None) == (contract.execute is not None)
        if contract.kind == "transform":
            assert not has_both_or_none, op
        else:
            assert contract.compile is None and contract.execute is None, op


def test_python_executed_ops_declare_the_shapely_engine():
    from app.pipelines.ops.contracts import OPERATIONS

    executed = {op: c for op, c in OPERATIONS.items() if c.execute is not None}
    assert set(executed) == {
        "transform.triangulate",
        "transform.densify",
        "transform.minimumBoundingCircle",
    }
    for op, contract in executed.items():
        assert contract.engine == "shapely", op
        assert contract.engine_license == "BSD-3-Clause (Shapely)", op
        assert contract.is_copyleft is False, op

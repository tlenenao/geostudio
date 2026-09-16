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

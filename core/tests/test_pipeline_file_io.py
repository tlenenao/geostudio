# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_pipeline_file_io_enabled
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog


def test_is_pipeline_file_io_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    assert is_pipeline_file_io_enabled() is False


def test_is_pipeline_file_io_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    assert is_pipeline_file_io_enabled() is True
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert is_pipeline_file_io_enabled() is False


def test_reader_file_and_writer_file_hidden_from_catalog_by_default(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    catalog = ops_catalog()
    assert "reader.file" not in catalog
    assert "writer.file" not in catalog


def test_reader_file_and_writer_file_visible_in_catalog_when_enabled(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    catalog = ops_catalog()
    assert catalog["reader.file"]["kind"] == "reader"
    assert catalog["writer.file"]["kind"] == "writer"


def test_operations_registry_has_reader_and_writer_file_contracts():
    assert OPERATIONS["reader.file"].kind == "reader"
    assert OPERATIONS["writer.file"].kind == "writer"

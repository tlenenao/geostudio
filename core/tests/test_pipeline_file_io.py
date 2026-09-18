# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_pipeline_file_io_enabled


def test_is_pipeline_file_io_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_PIPELINE_FILE_IO_ENABLED", raising=False)
    assert is_pipeline_file_io_enabled() is False


def test_is_pipeline_file_io_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")
    assert is_pipeline_file_io_enabled() is True
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert is_pipeline_file_io_enabled() is False

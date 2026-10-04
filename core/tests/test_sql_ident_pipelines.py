# SPDX-License-Identifier: Apache-2.0
"""REV-109 : le quoting d'identifiant DuckDB vit dans app.sql_ident seul —
plus aucune copie privée `_qi` dans app.pipelines."""

import pathlib

import pytest

from app.sql_ident import quote_ident_duckdb

_PIPELINES = pathlib.Path(__file__).parent.parent / "app" / "pipelines"


@pytest.mark.parametrize(
    "path",
    ["compiler.py", "runtime.py", "connector_runtime.py", "ops/execute.py"],
)
def test_no_private_copy_of_the_duckdb_identifier_quoter(path):
    source = (_PIPELINES / path).read_text(encoding="utf-8")
    assert "def _qi(" not in source, f"{path} redéfinit encore _qi"
    assert "quote_ident_duckdb" in source, f"{path} n'utilise pas app.sql_ident"


def test_quote_ident_duckdb_doubles_inner_quotes():
    assert quote_ident_duckdb('a"b') == '"a""b"'

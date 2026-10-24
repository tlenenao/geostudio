# SPDX-License-Identifier: Apache-2.0
import duckdb
import pytest

from app.analytics.sql_sandbox import SqlSandboxError
from app.pipelines.expr_validation import validate_bounded_expr


@pytest.mark.parametrize(
    "expr",
    ["read_text('/etc/passwd')", "length(read_blob('/x'))", "glob('/*')", "READ_CSV('a')"],
)
def test_file_functions_refused(expr):
    with pytest.raises(SqlSandboxError):
        validate_bounded_expr(duckdb.connect(), expr)


def test_plain_expression_still_accepted():
    validate_bounded_expr(duckdb.connect(), "a + 1 > 2 AND lower(b) = 'x'")

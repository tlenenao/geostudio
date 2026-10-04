# SPDX-License-Identifier: Apache-2.0
"""REV-278b : la validation d'expression CEL du cœur est un vrai parseur,
plus un contrôle de parenthèses."""

import pytest

from app.configs.document_validation import _cel_syntax_error


@pytest.mark.parametrize(
    "expr",
    ["a == 1", "a ? b : c", "has(a.b)", "x in [1, 2]", "a == 'x' && (b > 1)", "size(items) > 0"],
)
def test_valid_cel_is_accepted(expr):
    assert _cel_syntax_error(expr) is None


@pytest.mark.parametrize(
    "expr", ["value >", "(a", "$$$", "1 +", "a ==== b", "a b", "foo(", "a ? b"]
)
def test_invalid_cel_is_rejected(expr):
    error = _cel_syntax_error(expr)
    assert error is not None and error != ""


def test_empty_expression_is_rejected():
    assert _cel_syntax_error("   ") == "empty expression"

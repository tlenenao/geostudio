# SPDX-License-Identifier: Apache-2.0
"""AUD-125 : le cliquet mypy refuse toute régression par fichier."""

from scripts.mypy_ratchet import count_errors, regressions

OUT = (
    "app/a.py:3: error: x  [arg-type]\n"
    "app/a.py:9:4: error: y  [misc]\n"
    "app/b.py:1: note: ignoré\n"
    "Found 2 errors in 1 file\n"
)


def test_count_errors_per_file():
    assert count_errors(OUT) == {"app/a.py": 2}


def test_regression_detected_only_above_baseline():
    assert regressions({"app/a.py": 2}, {"app/a.py": 2}) == []
    assert regressions({"app/a.py": 1}, {"app/a.py": 2}) == []
    assert regressions({"app/a.py": 3}, {"app/a.py": 2})
    assert regressions({"app/new.py": 1}, {})  # nouveau fichier fautif

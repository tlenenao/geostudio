# SPDX-License-Identifier: Apache-2.0
"""REV-193 : app.cdc.parquet_writer ne doit plus charger duckdb au niveau
module — seul un futur appelant qui construit réellement une relation
DuckDB doit payer ce coût (67 ms / 11 MiB mesurés), pas le cdc-worker qui
importe ce fichier sans jamais avoir besoin de duckdb."""

import os
import subprocess
import sys


def test_importing_parquet_writer_does_not_load_duckdb():
    # Determine cwd: if we're already in core/, use "."; otherwise use "core"
    # (pytest runs from core/ in CI, but might run from repo root locally)
    cwd_to_use = "." if os.path.basename(os.getcwd()) == "core" else "core"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import app.cdc.parquet_writer; import sys; "
            "assert 'duckdb' not in sys.modules, 'duckdb was eagerly imported'",
        ],
        capture_output=True,
        text=True,
        cwd=cwd_to_use,
    )
    assert result.returncode == 0, result.stderr

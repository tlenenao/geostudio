# SPDX-License-Identifier: Apache-2.0
"""Le découpage CORE_TEST_SHARD couvre exactement la collection (ci.yml)."""

import subprocess
import sys
from pathlib import Path

from tests.conftest import shard_of

CORE = Path(__file__).resolve().parents[1]


def _collect(shard: str | None) -> set[str]:
    import os

    env = {k: v for k, v in os.environ.items() if k != "CORE_TEST_SHARD"}
    if shard:
        env["CORE_TEST_SHARD"] = shard
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "--no-cov",
            "tests/test_mcp_tools_create.py",
            "tests/test_ci_sharding.py",
            "tests/test_deployability.py",
        ],
        cwd=CORE,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {ln for ln in out.splitlines() if "::" in ln}


def test_shards_partition_the_collection():
    full = _collect(None)
    parts = [_collect(f"{i}/3") for i in (1, 2, 3)]
    assert full and set().union(*parts) == full
    assert sum(len(p) for p in parts) == len(full)  # pas de doublon


def test_shard_of_is_per_file_and_stable():
    assert shard_of("tests/a.py::t1", 4) == shard_of("tests/a.py::t2[x]", 4)
    assert 0 <= shard_of("tests/a.py::t1", 4) < 4

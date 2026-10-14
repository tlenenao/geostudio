# SPDX-License-Identifier: Apache-2.0
"""ARC-32 : N réplicas `core` lancent `alembic upgrade head` en même temps (compose --scale,
Helm replicas > 1) — le verrou consultatif de env.py doit les sérialiser."""

import subprocess
import sys

import pytest

from tests.test_migrations_p09 import CORE_DIR, _scalar
from tests.test_migrations_p09 import throwaway_database_url as _throwaway

pytestmark = pytest.mark.postgis

throwaway_database_url = _throwaway


def test_concurrent_upgrades_all_succeed(throwaway_database_url):
    cmd = [sys.executable, "-m", "alembic", "upgrade", "head"]
    procs = [
        subprocess.Popen(cmd, cwd=CORE_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(3)
    ]
    outs = [(p.communicate()[0].decode(), p.returncode) for p in procs]
    assert all(rc == 0 for _, rc in outs), outs
    assert _scalar(throwaway_database_url, "SELECT count(*) FROM alembic_version") == 1

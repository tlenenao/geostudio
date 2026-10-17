# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.jobs.defer import defer_resilient


def test_retries_then_succeeds():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("pool fermé")

    defer_resilient(flaky, delay=0)
    assert len(calls) == 3


def test_gives_up_with_503():
    def down():
        raise RuntimeError("down")

    with pytest.raises(HTTPException) as e:
        defer_resilient(down, delay=0)
    assert e.value.status_code == 503

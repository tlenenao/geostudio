# SPDX-License-Identifier: Apache-2.0
"""REV-280g : une connexion du cœur est en UTC, quel que soit le fuseau client."""

import pytest
from sqlalchemy import text

from app.db import make_engine

pytestmark = pytest.mark.postgis


def test_postgres_session_timezone_is_utc(test_db_url, monkeypatch):
    monkeypatch.setenv("PGTZ", "Europe/Paris")  # fuseau client envoyé par libpq
    engine = make_engine(test_db_url)
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SHOW timezone")).scalar() == "UTC"
    finally:
        engine.dispose()

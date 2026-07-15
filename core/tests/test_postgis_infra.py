# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text


@pytest.mark.postgis
def test_postgis_available(pg_engine):
    with pg_engine.connect() as conn:
        version = conn.execute(text("SELECT PostGIS_Version()")).scalar()
    assert version is not None

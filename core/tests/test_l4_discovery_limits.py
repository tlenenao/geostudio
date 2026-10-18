# SPDX-License-Identifier: Apache-2.0
"""AUD-095 : STAC/DCAT/Records anonymes bornés (budget de débit + délai sur ST_Extent)."""

import re

import pytest
from sqlalchemy import text

import app.stac.extent as extent
from app.collections.introspection import ColumnInfo, TableInfo
from app.ratelimit.limiter import route_group


def test_discovery_catalogues_have_their_own_rate_limit_group():
    never = re.compile(r"^$")
    for method, path in [
        ("GET", "/v1/stac/collections"),
        ("POST", "/v1/stac/search"),
        ("GET", "/v1/dcat/datasets"),
        ("GET", "/v1/records/collections"),
    ]:
        assert route_group(path, method, never) == "discovery", path


@pytest.mark.postgis
def test_extent_timeout_falls_back_to_none_and_does_not_poison_the_transaction(
    pg_session_factory, monkeypatch
):
    info = TableInfo(
        table_name="stac_extent_slow_t",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="id", type="integer", required=True)],
    )
    with pg_session_factory() as s:
        s.execute(text("DROP TABLE IF EXISTS stac_extent_slow_t"))
        s.execute(
            text(
                "CREATE TABLE stac_extent_slow_t "
                "(id serial PRIMARY KEY, geom geometry(Point, 4326))"
            )
        )
        s.execute(
            text(
                "INSERT INTO stac_extent_slow_t (geom) "
                "SELECT ST_SetSRID(ST_MakePoint(i % 90, i % 45), 4326) "
                "FROM generate_series(1, 400000) i"
            )
        )
        s.commit()
        before = s.scalar(text("SELECT current_setting('statement_timeout')"))
        monkeypatch.setattr(extent, "EXTENT_STATEMENT_TIMEOUT_MS", 1)
        assert extent.rls_scoped_bbox_4326(s, info) is None
        assert s.scalar(text("SELECT 1")) == 1  # la transaction reste saine
        assert s.scalar(text("SELECT current_setting('statement_timeout')")) == before
        s.execute(text("DROP TABLE IF EXISTS stac_extent_slow_t"))
        s.commit()

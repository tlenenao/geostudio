# SPDX-License-Identifier: Apache-2.0
"""AUD-011 : supprimer une collection supprime sa table PostGIS (si créée par GeoStudio)."""

import pytest
from sqlalchemy import text

from app.collections.ddl import drop_managed_table, is_managed_table

pytestmark = pytest.mark.postgis


def test_drop_managed_table_drops_ingest_and_quarantine_but_never_a_registered_table(
    pg_engine, pg_session_factory
):
    assert is_managed_table("ingest_0123456789ab")
    assert not is_managed_table("ingest_communes") and not is_managed_table("communes")
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE ingest_0123456789ab (id serial PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE ingest_0123456789ab__rejected (id int)"))
        conn.execute(text("CREATE TABLE communes_aud011 (id int)"))
    with pg_session_factory() as session:
        assert drop_managed_table(session, "ingest_0123456789ab") is True
        assert drop_managed_table(session, "communes_aud011") is False
        session.commit()
    with pg_engine.begin() as conn:
        left = set(
            conn.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE tablename LIKE '%aud011%' OR tablename LIKE 'ingest_0123456789ab%'"
                )
            ).scalars()
        )
        conn.execute(text("DROP TABLE communes_aud011"))
    assert left == {"communes_aud011"}

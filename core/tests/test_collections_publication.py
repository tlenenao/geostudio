# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.publication import (
    add_table_to_publication,
    remove_table_from_publication,
)

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_pub"))
        conn.execute(text("CREATE TABLE t_pub (id serial PRIMARY KEY, v text)"))
    yield "t_pub"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP PUBLICATION IF EXISTS geostudio_cdc"))
        conn.execute(text("DROP TABLE IF EXISTS t_pub"))


def _is_member(pg_engine, table_name: str) -> bool:
    with pg_engine.begin() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT 1 FROM pg_publication_tables WHERE pubname = 'geostudio_cdc' "
                    "AND schemaname = 'public' AND tablename = :t"
                ),
                {"t": table_name},
            ).scalar()
        )


def test_add_table_creates_publication_and_adds_table(pg_table, pg_session_factory, pg_engine):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        session.commit()
    assert _is_member(pg_engine, pg_table)


def test_add_table_is_idempotent(pg_table, pg_session_factory, pg_engine):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        add_table_to_publication(session, pg_table)  # ne doit pas lever
        session.commit()
    assert _is_member(pg_engine, pg_table)


def test_remove_table_drops_membership_but_keeps_publication(
    pg_table, pg_session_factory, pg_engine
):
    with pg_session_factory() as session:
        add_table_to_publication(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        remove_table_from_publication(session, pg_table)
        session.commit()
    assert not _is_member(pg_engine, pg_table)
    with pg_engine.begin() as conn:
        assert conn.execute(
            text("SELECT 1 FROM pg_publication WHERE pubname = 'geostudio_cdc'")
        ).scalar()  # la publication elle-même survit


def test_remove_table_is_idempotent_when_never_added(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        remove_table_from_publication(session, pg_table)  # ne doit pas lever
        session.commit()

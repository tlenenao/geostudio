# SPDX-License-Identifier: Apache-2.0
"""REV-301 : les connexions hors engine SQLAlchemy (pool procrastinate async +
sync, consommateur CDC psycopg2) sont en UTC même sous PGTZ=Europe/Paris."""

import asyncio

import psycopg_pool
import pytest

from app import jobs
from app.cdc import consumer


@pytest.fixture()
def dsn(test_db_url, monkeypatch):
    monkeypatch.setenv("PGTZ", "Europe/Paris")
    return test_db_url.replace("postgresql+psycopg2://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


def _pool_args(dsn):
    return {**jobs.app.connector._pool_args, "conninfo": dsn}  # type: ignore[attr-defined]


async def _async_tz(dsn):
    async with psycopg_pool.AsyncConnectionPool(**_pool_args(dsn), open=False) as pool:
        async with pool.connection() as conn:
            return await (await conn.execute("SHOW timezone")).fetchone()


@pytest.mark.postgis
def test_procrastinate_async_pool_is_utc(dsn):
    assert asyncio.run(_async_tz(dsn)) == ("UTC",)


@pytest.mark.postgis
def test_procrastinate_sync_pool_is_utc(dsn):
    args = {**_pool_args(dsn), "configure": jobs._utc_sync}
    with psycopg_pool.ConnectionPool(**args, open=True) as pool, pool.connection() as conn:
        assert conn.execute("SHOW timezone").fetchone() == ("UTC",)


@pytest.mark.postgis
def test_cdc_replication_connection_is_utc(dsn):
    conn, cur = consumer._connect(dsn)
    try:
        cur.execute("SHOW timezone")
        assert cur.fetchone() == ("UTC",)
    finally:
        conn.close()

# SPDX-License-Identifier: Apache-2.0
"""Mesure empirique (pas un test permanent) du critère d'acceptation SP-11c :
une requête SQL analyste (POST /analytics/sql, run_analyst_sql) retourne bien
sous STATEMENT_TIMEOUT_S sur un scénario RÉALISTE (~1M lignes CDC réparties
sur un gros backfill + de nombreux petits flushes incrémentaux, avec
quelques updates/tombstones pour exercer la réduction état-courant
`max(_lsn)`), PAS un seul gros fichier artificiel favorable — même esprit et
même patron que scripts/measure_aggregate_performance.py (SP-11b).

Usage (contre un MinIO jetable) :
    docker run -d --name sp11c-minio -p 9000:9000 \
        -e MINIO_ROOT_USER=minioadmin -e MINIO_ROOT_PASSWORD=minioadmin \
        minio/minio server /data
    cd core && S3_ENDPOINT_URL=http://localhost:9000 S3_ACCESS_KEY=minioadmin \
        S3_SECRET_KEY=minioadmin S3_CDC_BUCKET=geostudio-cdc \
        uv run python -m scripts.measure_sql_sandbox

(Invoquer via `-m scripts.measure_sql_sandbox`, pas `python scripts/....py` —
le package `scripts` a besoin du cwd sur sys.path, cf. constat empirique de
la Task 1 de ce plan.)
"""
import os
import sys
import time
import uuid
from io import BytesIO

import boto3
import geopandas as gpd
import numpy as np
from shapely.geometry import Point

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analytics.duckdb_conn import open_connection  # noqa: E402
from app.analytics.sql_sandbox import STATEMENT_TIMEOUT_S, run_analyst_sql  # noqa: E402
from app.collections.introspection import ColumnInfo, TableInfo  # noqa: E402

TENANT_ID = "default"
COLLECTION_ID = "villes"
TOTAL_ROWS = 1_000_000
BACKFILL_ROWS = 900_000  # un gros fichier initial...
INCREMENTAL_BATCHES = 200  # ...puis 200 petits flushes réalistes
ROWS_PER_BATCH = (TOTAL_ROWS - BACKFILL_ROWS) // INCREMENTAL_BATCHES  # 500
UPDATE_BATCHES = 5  # parmi les 200, quelques updates sur des pks déjà backfillés...
DELETE_BATCHES = 5  # ...et quelques tombstones (exercent la réduction max(_lsn))
INSERT_BATCHES = INCREMENTAL_BATCHES - UPDATE_BATCHES - DELETE_BATCHES

REGIONS = ["Nord", "Sud", "Est", "Ouest"]

TABLE_INFO = TableInfo(
    table_name=COLLECTION_ID, pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="region", type="string", required=True),
             ColumnInfo(name="pop", type="integer", required=True)],
)


def _bucket() -> str:
    return os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")


def _base_uri() -> str:
    return f"s3://{_bucket()}/cdc"


def _client():
    return boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )


def _write_batch(client, *, ids: np.ndarray, op: str, lsn: int) -> None:
    n_rows = len(ids)
    rng = np.random.default_rng(lsn)
    rows = {
        "id": ids,
        "region": rng.choice(REGIONS, size=n_rows),
        "pop": rng.integers(1, 1000, size=n_rows),
        "_op": [op] * n_rows,
        "_lsn": [lsn] * n_rows,
        "_ts": [1.0] * n_rows,
        "geometry": [Point(0.0, 0.0)] * n_rows,
    }
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    buf = BytesIO()
    gdf.to_parquet(buf)
    key = (f"cdc/tenant_id={TENANT_ID}/collection_id={COLLECTION_ID}/"
           f"dt=2026-07-18/part-{uuid.uuid4().hex}.parquet")
    client.put_object(Bucket=_bucket(), Key=key, Body=buf.getvalue())


def _measure_sql() -> tuple[float, list, list]:
    conn = open_connection(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    start = time.monotonic()
    columns, rows, truncated = run_analyst_sql(
        conn, sql="SELECT region, count(*), avg(pop) FROM villes GROUP BY region",
        allowed={COLLECTION_ID: TABLE_INFO}, base_uri=_base_uri(), tenant_id=TENANT_ID,
    )
    elapsed = time.monotonic() - start
    conn.close()
    assert not truncated
    return elapsed, columns, rows


def main() -> int:
    client = _client()
    try:
        client.create_bucket(Bucket=_bucket())
    except Exception:
        pass

    print(f"Écriture du backfill ({BACKFILL_ROWS} lignes, 1 fichier)...")
    _write_batch(client, ids=np.arange(0, BACKFILL_ROWS), op="insert", lsn=1)

    print(f"Écriture de {INSERT_BATCHES} flushes incrémentaux d'insertion "
          f"({ROWS_PER_BATCH} lignes chacun)...")
    next_id = BACKFILL_ROWS
    lsn = 2
    for _ in range(INSERT_BATCHES):
        _write_batch(client, ids=np.arange(next_id, next_id + ROWS_PER_BATCH), op="insert", lsn=lsn)
        next_id += ROWS_PER_BATCH
        lsn += 1

    print(f"Écriture de {UPDATE_BATCHES} flushes de mise à jour "
          f"(pks déjà backfillés, {ROWS_PER_BATCH} lignes chacun, exerce max(_lsn))...")
    for i in range(UPDATE_BATCHES):
        ids = np.arange(i * ROWS_PER_BATCH, (i + 1) * ROWS_PER_BATCH)
        _write_batch(client, ids=ids, op="update", lsn=lsn)
        lsn += 1

    print(f"Écriture de {DELETE_BATCHES} flushes de suppression "
          f"(tombstones sur pks déjà backfillés, {ROWS_PER_BATCH} lignes chacun)...")
    delete_base = UPDATE_BATCHES * ROWS_PER_BATCH
    for i in range(DELETE_BATCHES):
        ids = np.arange(delete_base + i * ROWS_PER_BATCH, delete_base + (i + 1) * ROWS_PER_BATCH)
        _write_batch(client, ids=ids, op="delete", lsn=lsn)
        lsn += 1

    expected_live = BACKFILL_ROWS + INSERT_BATCHES * ROWS_PER_BATCH - DELETE_BATCHES * ROWS_PER_BATCH
    print(f"Lignes vivantes attendues après réduction état-courant (backfill + inserts - "
          f"tombstones, updates neutres en compte) : {expected_live}")

    elapsed, columns, rows = _measure_sql()
    total_count = sum(r[1] for r in rows)
    print(f"Colonnes : {columns}")
    print(f"Lignes retournées (par région) : {rows}")
    print(f"Somme des count(*) : {total_count} (attendu {expected_live})")
    print(f"Requête SQL analyste (SELECT region, count(*), avg(pop) FROM villes GROUP BY region) : "
          f"{elapsed:.3f}s (limite STATEMENT_TIMEOUT_S={STATEMENT_TIMEOUT_S}s) "
          f"({'PASS' if elapsed < STATEMENT_TIMEOUT_S else 'FAIL'})")

    ok = elapsed < STATEMENT_TIMEOUT_S and total_count == expected_live
    if total_count != expected_live:
        print(f"ATTENTION : somme des count(*) ({total_count}) != attendu ({expected_live}) "
              f"— la réduction max(_lsn) ne s'est pas comportée comme prévu")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

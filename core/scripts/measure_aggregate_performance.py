# SPDX-License-Identifier: Apache-2.0
"""Mesure empirique (pas un test permanent) du critère d'acceptation SP-11b
#2 : ~1M lignes agrégées en <2s via POST /collections/{id}/aggregate, mesuré
sur un scénario RÉALISTE (backfill + petits fichiers incrémentaux, PAS un
seul gros fichier artificiel) — avant ET après un cycle de compaction, pour
prouver que la performance ne dépend pas d'un scénario favorable non
représentatif d'un flux CDC prolongé (cf. spec §Tests).

Usage (contre la stack docker-compose réelle) :
    docker compose up -d minio
    cd core && S3_ENDPOINT_URL=http://127.0.0.1:9000 \
        S3_ACCESS_KEY=$MINIO_USER S3_SECRET_KEY=$MINIO_PASSWORD \
        uv run python -m scripts.measure_aggregate_performance
"""

import os
import sys
import time
import uuid
from io import BytesIO

import boto3
import duckdb
import geopandas as gpd
import numpy as np
from shapely.geometry import Point

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analytics.aggregate import AggregateRequestBody, run_collection_aggregate  # noqa: E402
from app.cdc.compaction import run_compaction_cycle  # noqa: E402
from app.collections.introspection import ColumnInfo, TableInfo  # noqa: E402

BUCKET = "geostudio-cdc-perf"
TENANT_ID = "perf"
COLLECTION_ID = "perf_villes"
TOTAL_ROWS = 1_000_000
BACKFILL_ROWS = 900_000  # un gros fichier initial...
INCREMENTAL_BATCHES = 200  # ...puis 200 petits flushes réalistes (500 lignes chacun)
INCREMENTAL_ROWS_PER_BATCH = (TOTAL_ROWS - BACKFILL_ROWS) // INCREMENTAL_BATCHES

TABLE_INFO = TableInfo(
    table_name=COLLECTION_ID,
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)

REGIONS = ["Nord", "Sud", "Est", "Ouest"]


def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )


def _write_batch(client, *, n_rows: int, id_start: int, lsn: int) -> None:
    rng = np.random.default_rng(lsn)
    rows = {
        "id": np.arange(id_start, id_start + n_rows),
        "region": rng.choice(REGIONS, size=n_rows),
        "pop": rng.integers(1, 1000, size=n_rows),
        "_op": ["insert"] * n_rows,
        "_lsn": [lsn] * n_rows,
        "_ts": [1.0] * n_rows,
        "geometry": [Point(0.0, 0.0)] * n_rows,
    }
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    buf = BytesIO()
    gdf.to_parquet(buf)
    key = (
        f"cdc/tenant_id={TENANT_ID}/collection_id={COLLECTION_ID}/dt=2026-07-18/"
        f"part-{uuid.uuid4().hex}.parquet"
    )
    client.put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())


def _measure_aggregate() -> float:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    endpoint = os.environ["S3_ENDPOINT_URL"].split("://", 1)[-1]
    conn.execute(f"SET s3_endpoint = '{endpoint}'")
    conn.execute("SET s3_use_ssl = false")
    conn.execute("SET s3_url_style = 'path'")
    conn.execute(f"SET s3_access_key_id = '{os.environ['S3_ACCESS_KEY']}'")
    conn.execute(f"SET s3_secret_access_key = '{os.environ['S3_SECRET_KEY']}'")

    start = time.monotonic()
    _category_key, rows = run_collection_aggregate(
        conn,
        base_uri=f"s3://{BUCKET}/cdc",
        tenant_id=TENANT_ID,
        collection_id=COLLECTION_ID,
        table_info=TABLE_INFO,
        request=AggregateRequestBody(groupBy="region", agg="sum", field="pop"),
    )
    elapsed = time.monotonic() - start
    conn.close()
    assert len(rows) == len(REGIONS)
    return elapsed


def main() -> int:
    client = _client()
    try:
        client.create_bucket(Bucket=BUCKET)
    except Exception:
        pass

    print(f"Écriture du backfill ({BACKFILL_ROWS} lignes, 1 fichier)...")
    _write_batch(client, n_rows=BACKFILL_ROWS, id_start=0, lsn=1)

    print(
        f"Écriture de {INCREMENTAL_BATCHES} flushes incrémentaux "
        f"({INCREMENTAL_ROWS_PER_BATCH} lignes chacun)..."
    )
    for i in range(INCREMENTAL_BATCHES):
        _write_batch(
            client,
            n_rows=INCREMENTAL_ROWS_PER_BATCH,
            id_start=BACKFILL_ROWS + i * INCREMENTAL_ROWS_PER_BATCH,
            lsn=i + 2,
        )

    elapsed_before = _measure_aggregate()
    print(
        f"Agrégation AVANT compaction : {elapsed_before:.3f}s "
        f"({'PASS' if elapsed_before < 2.0 else 'FAIL'}, critère <2s)"
    )

    print("Cycle de compaction...")
    report = run_compaction_cycle(client, bucket=BUCKET)
    print(
        f"  {report.partitions_scanned} partitions scannées, "
        f"{report.partitions_compacted} compactées, {report.files_removed} fichiers retirés"
    )

    elapsed_after = _measure_aggregate()
    print(
        f"Agrégation APRÈS compaction : {elapsed_after:.3f}s "
        f"({'PASS' if elapsed_after < 2.0 else 'FAIL'}, critère <2s)"
    )

    return 0 if (elapsed_before < 2.0 and elapsed_after < 2.0) else 1


if __name__ == "__main__":
    sys.exit(main())

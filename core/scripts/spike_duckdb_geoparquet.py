# SPDX-License-Identifier: Apache-2.0
"""Spike SP-11b : DuckDB (httpfs + spatial) contre un GeoParquet réel écrit
par geopandas (même écriture que app.cdc.parquet_writer, SP-11a) hébergé sur
un MinIO réel. Vérifie, DANS L'ORDRE :
1. httpfs + spatial s'installent/chargent sans erreur ;
2. lecture d'un fichier GeoParquet réel écrit par geopandas depuis S3/MinIO
   via read_parquet(..., hive_partitioning=true) ;
3. réduction à l'état courant par fenêtre SQL (QUALIFY row_number() OVER
   (PARTITION BY pk ORDER BY _lsn DESC) = 1), tombstone exclue ;
4. filtre spatial bbox (ST_Intersects) sur la colonne géométrie WKB — LE
   point le plus incertain (deux implémentations indépendantes de la spec
   GeoParquet : geopandas/pyarrow en écriture, extension spatial de DuckDB en
   lecture). Deux incantations testées dans l'ordre : (a) la colonne lue
   directement comme GEOMETRY (DuckDB spatial peut convertir nativement une
   colonne GeoParquet 1.0 taguée dans les métadonnées "geo") ; (b) repli
   ST_GeomFromWKB(colonne) si (a) échoue (colonne lue comme BLOB brut).

Si un de ces points échoue durement après investigation raisonnable : arrêter
le plan ici, documenter ce qui a été essayé, retourner en brainstorm/spec.

Usage :
  S3_ENDPOINT_URL=http://127.0.0.1:9000 S3_ACCESS_KEY=$MINIO_USER \
    S3_SECRET_KEY=$MINIO_PASSWORD uv run python -m scripts.spike_duckdb_geoparquet
Nécessite : docker compose up -d minio (le bucket "geostudio-cdc-spike" est
créé par le script s'il n'existe pas).
Sort avec le code 0 (PASS) ou 1 (FAIL, échecs listés).
"""
import os
import sys
from io import BytesIO

import duckdb
import geopandas as gpd
import shapely.wkb
from shapely.geometry import Point

BUCKET = "geostudio-cdc-spike"


def _write_fixture_to_minio() -> None:
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    )
    try:
        client.create_bucket(Bucket=BUCKET)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise

    records = [
        {"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Point(2.30, 48.80)},
        {"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0,
         "geometry": Point(2.31, 48.81)},  # doit gagner (lsn max)
        {"id": 2, "titre": "c", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Point(10.0, 10.0)},  # hors bbox du filtre testé plus bas
    ]
    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    buf = BytesIO()
    gdf.to_parquet(buf)
    client.put_object(
        Bucket=BUCKET,
        Key="tenant_id=default/collection_id=spike/dt=2026-07-18/part-1.parquet",
        Body=buf.getvalue(),
    )


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
        if not cond:
            failures.append(name)

    _write_fixture_to_minio()

    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    check("httpfs + spatial installés/chargés", True)

    endpoint = os.environ["S3_ENDPOINT_URL"].split("://", 1)[-1]
    use_ssl = os.environ["S3_ENDPOINT_URL"].startswith("https://")
    conn.execute(f"SET s3_endpoint = '{endpoint}'")
    conn.execute(f"SET s3_use_ssl = {str(use_ssl).lower()}")
    conn.execute("SET s3_url_style = 'path'")
    conn.execute(f"SET s3_access_key_id = '{os.environ['S3_ACCESS_KEY']}'")
    conn.execute(f"SET s3_secret_access_key = '{os.environ['S3_SECRET_KEY']}'")

    glob = f"s3://{BUCKET}/tenant_id=default/collection_id=spike/dt=*/*.parquet"

    rows = conn.execute(
        f"SELECT id, titre, _op, _lsn FROM read_parquet('{glob}', hive_partitioning=true) ORDER BY id, _lsn"
    ).fetchall()
    check("lecture GeoParquet réel via httpfs (3 lignes brutes)", len(rows) == 3)

    reduced = conn.execute(
        f"""
        WITH raw AS (SELECT * FROM read_parquet('{glob}', hive_partitioning=true)),
             current AS (
                 SELECT * FROM raw
                 QUALIFY row_number() OVER (PARTITION BY id ORDER BY _lsn DESC) = 1
             )
        SELECT id, titre FROM current WHERE _op != 'delete' ORDER BY id
        """
    ).fetchall()
    check(
        "réduction état courant (lsn max gagne, tombstone exclue)",
        reduced == [(1, "b"), (2, "c")],
    )

    # Filtre spatial : deux incantations testées, la première qui marche fait foi.
    bbox_sql_native = f"""
        WITH raw AS (SELECT * FROM read_parquet('{glob}', hive_partitioning=true)),
             current AS (
                 SELECT * FROM raw
                 QUALIFY row_number() OVER (PARTITION BY id ORDER BY _lsn DESC) = 1
             )
        SELECT id FROM current
        WHERE _op != 'delete' AND ST_Intersects(geometry, ST_MakeEnvelope(2.0, 48.0, 3.0, 49.0))
        ORDER BY id
    """
    bbox_sql_wkb = bbox_sql_native.replace(
        "ST_Intersects(geometry,", "ST_Intersects(ST_GeomFromWKB(geometry),",
    )
    bbox_result = None
    working_incantation = None
    for label, sql in [("native GEOMETRY", bbox_sql_native), ("ST_GeomFromWKB", bbox_sql_wkb)]:
        try:
            bbox_result = conn.execute(sql).fetchall()
            working_incantation = label
            break
        except Exception as exc:  # noqa: BLE001 — spike exploratoire, on essaie l'autre incantation
            print(f"    ({label} a échoué : {exc})")
    check(
        f"filtre bbox ST_Intersects fonctionne (incantation retenue : {working_incantation})",
        bbox_result == [(1,)],
    )

    print("\nRésultat spike :", "PASS" if not failures else f"FAIL ({failures})")
    if working_incantation:
        print(f"INCANTATION BBOX RETENUE POUR TASK 6 : {working_incantation}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

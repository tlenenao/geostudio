# SPDX-License-Identifier: Apache-2.0
"""Spike go/no-go SP-11c — isolation DuckDB pour le SQL analyste sandboxé.

FINDINGS (confirmés empiriquement le 2026-07-18 contre un MinIO jetable réel,
DuckDB 1.5.4 — GO 10/10, cf. core/.superpowers/sdd/task-1-report.md) :
- AST json_serialize_sql : type de nœud SELECT = "SELECT_NODE" (confirmé, pas de
  requête d'UNION/EXCEPT/INTERSECT testée ici — "SET_OPERATION_NODE" resté une
  hypothèse non vérifiée par ce spike, à re-confirmer en Task 7 si nécessaire) ;
  réf. table de base = type "BASE_TABLE", clé "table_name" (confirmé — cf.
  from_table.left/right dans l'AST SAMPLE ci-dessous : {"type": "BASE_TABLE",
  ..., "table_name": "villes", ...}).
- Verrouillage : SET enable_external_access=false; SET lock_configuration=true
  bloque read_parquet/read_csv/ATTACH/COPY TO/INSTALL LOAD/lecture locale
  (read_text) ET un re-SET enable_external_access=true tenté après coup : OUI
  (7/7 cas d'abus lèvent une exception).
- ST_* + SELECT sur table temp matérialisée fonctionnent après verrouillage : OUI
  (count=5, ST_Intersects sur la géométrie de la table temp déjà matérialisée).
- Timeout via threading.Timer(conn.interrupt) interruptible : OUI, exception =
  duckdb.InterruptException (sous-classe de duckdb.Error/DatabaseError — PAS de
  duckdb.Exception, cf. correction ci-dessous).
- SET memory_limit / SET threads acceptés : OUI (aucune exception aux deux SET,
  exécutés avant verrouillage).
- CORRECTION EMPIRIQUE au script tel que fourni par le brief : `duckdb.Exception`
  n'existe pas en DuckDB 1.5.4 (AttributeError à l'exécution — cassait le
  except des cas d'abus ET du timeout). La base commune réelle de toutes les
  exceptions DuckDB (PermissionException, HTTPException, InterruptException,
  BinderException, IOException, CatalogException, ...) est `duckdb.Error`
  (héritage confirmé via __mro__). Script corrigé pour catcher `duckdb.Error`
  aux deux endroits — pertinent pour Task 8 qui réutilisera ce patron.

Lancer : cd core && uv run python -m scripts.spike_duckdb_sql_sandbox
(PAS `python scripts/spike_duckdb_sql_sandbox.py` — le script importe
`app.analytics.duckdb_conn`, qui a besoin du cwd `core/` sur sys.path ;
seul `-m` depuis `core/` le garantit, cf. convention déjà en place pour
`scripts.seed_demo`/`scripts.measure_aggregate_performance`.)
"""
import json
import os
import threading
import time
import uuid

import duckdb
import geopandas as gpd
from shapely.geometry import Point

from app.analytics.duckdb_conn import open_connection

BUCKET = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
BASE = f"s3://{BUCKET}/cdc"
GLOB = f"{BASE}/tenant_id=t1/collection_id=villes/dt=2026-07-18/*.parquet"

results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def _open():
    return open_connection(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def write_fixture():
    # Écrit un GeoParquet CDC réel via geopandas → MinIO (httpfs write).
    conn = _open()
    gdf = gpd.GeoDataFrame(
        [{"id": i, "region": "Nord" if i % 2 else "Sud", "pop": i,
          "_op": "insert", "_lsn": i, "_ts": 1.0, "geometry": Point(i, i)} for i in range(1, 6)],
        geometry="geometry", crs="EPSG:4326",
    )
    local = f"/tmp/spike-{uuid.uuid4().hex}.parquet"
    gdf.to_parquet(local)
    conn.execute(f"COPY (SELECT * FROM read_parquet('{local}')) TO '{GLOB.replace('*', 'part-1')}' (FORMAT parquet)")
    conn.close()


def probe_ast():
    conn = _open()
    doc = json.loads(conn.execute(
        "SELECT json_serialize_sql('SELECT region, count(*) FROM villes t JOIN autre a ON a.id=t.id GROUP BY region')"
    ).fetchone()[0])
    print("AST SAMPLE:", json.dumps(doc)[:2000])
    # Repérer visuellement les type de nœud SELECT et les nœuds de table de base (table_name).
    check("json_serialize_sql renvoie un AST exploitable", "statements" in doc, str(list(doc.keys())))
    conn.close()


def probe_materialize_then_lock():
    conn = _open()
    conn.execute("SET memory_limit='512MB'")
    conn.execute("SET threads=2")
    # 1) Matérialiser depuis le GeoParquet (accès externe encore autorisé).
    conn.execute(f"CREATE TEMP TABLE villes AS SELECT * FROM read_parquet('{GLOB}', hive_partitioning=true)")
    # 2) Verrouiller.
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")
    # 3) SELECT + ST_* sur la table temp doivent marcher.
    n = conn.execute("SELECT count(*) FROM villes WHERE ST_Intersects(geometry, ST_MakeEnvelope(0,0,10,10))").fetchone()[0]
    check("SELECT + ST_* sur table temp après verrouillage", n == 5, f"count={n}")

    # 4) Chaque cas d'abus doit LEVER une exception.
    for label, sql in [
        ("read_parquet chemin arbitraire (cross-tenant)", f"SELECT * FROM read_parquet('{BASE}/tenant_id=t2/collection_id=x/dt=*/*.parquet')"),
        ("read_csv arbitraire", "SELECT * FROM read_csv('/etc/hostname')"),
        ("lecture fichier local", "SELECT * FROM read_text('/etc/hostname')"),
        ("ATTACH base externe", "ATTACH 'x.db' AS x"),
        ("COPY TO (écriture)", "COPY (SELECT 1) TO '/tmp/out.parquet'"),
        ("INSTALL/LOAD extension", "INSTALL json; LOAD json"),
        ("re-SET pour ré-autoriser", "SET enable_external_access = true"),
    ]:
        try:
            conn.execute(sql)
            check(f"BLOQUE : {label}", False, "n'a PAS levé — TROU DE SÉCURITÉ")
        except duckdb.Error:
            check(f"BLOQUE : {label}", True)
    conn.close()


def probe_timeout():
    conn = _open()
    timer = threading.Timer(0.5, conn.interrupt)
    timer.start()
    t0 = time.time()
    try:
        conn.execute("SELECT count(*) FROM range(100000000000) t1, range(100000) t2").fetchall()
        check("interrupt() interrompt une requête longue", False, "n'a pas été interrompue")
    except duckdb.Error as exc:
        check("interrupt() interrompt une requête longue", (time.time() - t0) < 5, f"{type(exc).__name__}")
    finally:
        timer.cancel()
        conn.close()


if __name__ == "__main__":
    write_fixture()
    probe_ast()
    probe_materialize_then_lock()
    probe_timeout()
    failed = [r for r in results if not r[1]]
    print(f"\n{'GO' if not failed else 'NO-GO'} — {len(results) - len(failed)}/{len(results)} checks PASS")
    raise SystemExit(1 if failed else 0)

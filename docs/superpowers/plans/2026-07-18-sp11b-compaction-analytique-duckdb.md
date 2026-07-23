# SP-11b — Compaction GeoParquet + module analytique DuckDB — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un widget Graphique ou Indicateur agrège les données d'une collection via une nouvelle API du cœur (`POST /collections/{id}/aggregate`, DuckDB in-process interrogeant le GeoParquet CDC produit par SP-11a) au lieu de fetcher les features brutes et d'agréger côté client — ~1 M lignes agrégées en < 2 s — pendant qu'un job de compaction périodique réduit le nombre de fichiers Parquet par partition pour qu'une collection à forte écriture reste performante, sans jamais changer la sémantique de change-log ni risquer de perte de données.

**Architecture:** Deux morceaux indépendants qui partagent seulement le layout S3 posé par SP-11a (`cdc/tenant_id=<t>/collection_id=<c>/dt=<d>/part-<uuid>.parquet`). (1) Un job procrastinate périodique (nouvelle queue `cdc`, tourne dans le process `worker` déjà existant — pas `cdc-worker`, qui est entièrement occupé par la boucle bloquante de réplication) fusionne les petits fichiers Parquet d'une même partition en un seul, toujours écriture-avant-suppression, jamais de déduplication à l'écriture. (2) Un nouveau module `app/analytics/` ouvre une connexion DuckDB éphémère par requête (extensions `httpfs`+`spatial`), lit le GeoParquet via `read_parquet(glob, hive_partitioning=true)`, réduit à l'état courant par fenêtre SQL (`QUALIFY row_number() ... = 1`), applique filtres/bbox/group-by côté DuckDB puis pivote le (petit) résultat groupé en Python — exactement la forme que produit `aggregateRecords` aujourd'hui côté client — exposé par un nouvel endpoint REST, consommé par `itemClient.queryDataSource` à la place de l'agrégation client actuelle.

**Tech Stack:** Python (core existant), nouvelle dépendance `duckdb` (extensions `httpfs`+`spatial` chargées à l'exécution), `geopandas`/`pyarrow` (déjà présents depuis SP-11a, réutilisés par la compaction), `procrastinate` (déjà présent, nouvelle queue `cdc`).

## Global Constraints

- Layout S3 CDC hérité de SP-11a, inchangé : `s3://<bucket>/cdc/tenant_id=<tenant>/collection_id=<collection>/dt=<YYYY-MM-DD>/part-<uuid>.parquet`. Colonnes fixes `_op`/`_lsn`/`_ts`, tombstones PK-seule sur delete.
- **La compaction ne change JAMAIS la sémantique du change-log** : toujours append-only en sortie (fusion pure, aucune déduplication ni suppression de tombstone à l'écriture). La réduction à l'état courant reste entièrement à la charge du lecteur (module analytique).
- **Sûreté à l'interruption** : le fichier fusionné est **toujours écrit avant** la suppression des fichiers d'entrée, jamais l'inverse. Un crash entre les deux laisse des doublons inoffensifs (le lecteur réduit par `(pk, max(_lsn))`), jamais de perte.
- Seuil de taille de fusion : **32 Mo** (`DEFAULT_SIZE_THRESHOLD_BYTES = 32 * 1024 * 1024`), paramétrable — un fichier déjà volumineux n'est jamais re-fusionné.
- Cron de compaction : **`*/10 * * * *`** (toutes les 10 min, dans la fourchette 10–15 min de la spec), nouvelle queue procrastinate `cdc`. Le job tourne dans le process `worker` (`docker-compose.yml`), jamais dans `cdc-worker` (occupé par la boucle de réplication bloquante).
- `app/jobs.py` (`import_paths`) et `docker-compose.yml` (`worker` : `-q ingestion,search,cdc`) doivent tous les deux référencer la nouvelle queue — même classe de bug que la régression critique de SP-7 (`import_paths` manquant) : à vérifier explicitement par un test de régression, pas seulement supposé.
- Connexion DuckDB : **in-process, éphémère par requête** (ouverte/fermée à chaque appel de `POST /collections/{id}/aggregate`), extensions `httpfs`+`spatial` chargées à chaque connexion (installées une fois sur le disque de l'image). Pas de pool. Credentials S3/MinIO réutilisés depuis les mêmes variables d'environnement que `app.cdc`/`app.ingestion` (`S3_ENDPOINT_URL`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`), bucket `S3_CDC_BUCKET` (défaut `geostudio-cdc`, même défaut que `app/cdc/main.py`).
- Requête DuckDB : glob **toujours scopé** à `tenant_id=<tenant courant>/collection_id=<id demandé>` — jamais un pattern plus large (l'isolation tenant est portée par le chemin S3, pas par une RLS Postgres qui n'existe pas côté fichiers).
- Réduction à l'état courant : `QUALIFY row_number() OVER (PARTITION BY <pk> ORDER BY _lsn DESC) = 1`, puis exclusion `_op != 'delete'` — dans cet ordre, avant tout filtre/group-by.
- Noms de colonnes (groupBy/split/field de mesure/clés de filtre) **validés contre le schéma introspecté** (`TableInfo.columns`/`pk_column`/`geometry_column`) avant toute interpolation SQL — même frontière de confiance que `_where` dans `app/features/repository.py` pour `GET /items`. Le pattern glob lui-même (construit uniquement à partir de `bucket`/`col.tenant_id`/`col.id`, jamais d'entrée utilisateur brute) est interpolé directement en littéral SQL plutôt que lié en paramètre — DuckDB ne garantit pas le bind de paramètres sur les arguments de fonctions table (`read_parquet(?)`), et ces trois valeurs sont des identifiants internes déjà validés à l'enregistrement de la collection.
- Endpoint : **`POST /collections/{collection_id}/aggregate`** (POST parce que le corps est structuré, pas une liste de query params) — même porte d'autorisation que `GET /collections/{id}/items` (`get_readable_collection`, 404 avant 403). Réponse : `{"categoryKey": str, "rows": [...]}`
  — `rows` est la forme large (une ligne par catégorie, une colonne par série) que produit `aggregateRecords` aujourd'hui côté client ; `categoryKey` indique quelle clé de chaque ligne porte la catégorie (le shell enveloppe `{id: row[categoryKey], properties: row}`).
- **Le mode démo lecture seule (SP-9, `CORE_READ_ONLY_MODE`) doit laisser passer cet endpoint** malgré son verbe `POST` : c'est une lecture. Le middleware `read_only_guard` (`app/main.py`) doit exempter explicitement `^/collections/[^/]+/aggregate$`, avec un test de régression dans `test_read_only_mode.py` — sans quoi une démo publique casse silencieusement tout widget Graphique/Indicateur.
- `aggregateRecords`/`reduceValues`/`measureLabel` (agrégation client, `shell/src/api/itemClient.ts:84-165`) sont supprimés une fois la migration faite — code mort, pas de garde de compatibilité à conserver.
- Hors périmètre (rappel spec) : endpoint SQL sandbox analyste, dashboard/alerte Grafana dédiés, outil MCP d'agrégation, DuckDB-WASM navigateur, analytique temporelle/historique, politique de rétention du change-log.

### Décisions de conception prises par ce plan (au-delà du texte de la spec)

La spec (`docs/superpowers/specs/2026-07-17-sp11b-compaction-analytique-duckdb-design.md`) fixe l'architecture ; ce plan tranche les points d'implémentation qu'elle laisse ouverts :

1. **La compaction tient dans `app/cdc/` (pas un nouveau package)** : elle ne touche qu'au layout S3 déjà possédé par ce module, et réutilise ses primitives S3 (`app/cdc/storage.py`, étendu avec `list_objects`/`delete_objects`/`upload_bytes` — `make_s3_client`/`ensure_cdc_bucket`/`upload_parquet_file` existent déjà depuis SP-11a). Le module analytique, lui, est un domaine neuf (`app/analytics/`) : il ne dépend d'aucune primitive CDC, seulement du layout S3 (une constante de chemin) et de l'introspection Postgres existante (`app.collections.introspection`).
2. **La compaction est 100% en mémoire (`BytesIO`), jamais de fichier temporaire local** — contrairement au flush du `cdc-worker` (SP-11a, `app/cdc/main.py`) qui écrit un fichier local avant de l'uploader. `geopandas.to_parquet`/`read_parquet` acceptent un buffer aussi bien qu'un chemin ; la compaction n'a pas besoin d'un chemin de fichier réel, ce qui évite toute gestion de nettoyage de fichiers temporaires (la classe de bug corrigée en revue finale de SP-11a Task 9).
3. **Le job de compaction ne touche jamais à Postgres** : le layout S3 encode déjà `tenant_id`/`collection_id` dans le chemin de chaque objet — la compaction n'a besoin de rien d'autre qu'un client S3 pour découvrir ses partitions. Il tourne dans le process `worker` existant (nouvelle queue `cdc`), jamais dans `cdc-worker` (occupé en continu par `consumer.stream_changes`, qui est une boucle bloquante — un job procrastinate n'y trouverait jamais de créneau pour s'exécuter).
4. **Tests de compaction sans MinIO réel** : toutes les opérations S3 utilisées par la compaction (`list_objects_v2`/`get_object`/`put_object`/`delete_objects`) sont testées avec un client factice (`_FakeS3Client`, même patron que `test_cdc_storage.py`/`test_ingestion_storage.py` depuis SP-6a/SP-11a) — aucun besoin d'un MinIO de test réel pour prouver l'algorithme de fusion.
5. **Tests du module analytique sans MinIO réel non plus, sauf le spike d'ouverture** : `read_parquet`/`glob`/`QUALIFY`/les fonctions `ST_*` de l'extension `spatial` fonctionnent sur des chemins de fichiers locaux exactement comme sur `s3://` (DuckDB dispatche sur le schéma du chemin) — les tests de `app/analytics/aggregate.py` pointent une connexion DuckDB en mémoire vers un répertoire `tmp_path` local rempli de fixtures GeoParquet écrites via `geopandas` (même pattern que `test_cdc_parquet_writer.py` de SP-11a), sans jamais configurer `httpfs`/S3. Seul le spike d'ouverture (Task 1, un script jetable, pas un test pytest permanent) prouve la connectivité réelle `httpfs` + MinIO + credentials — c'est la seule inconnue technique de ce plan (compatibilité DuckDB spatial ↔ GeoParquet écrit par geopandas, signalée comme risque par la spec).
6. **Glob interpolé en littéral SQL, jamais en paramètre lié** : `read_parquet(?, ...)`/`glob(?)` ne sont pas garantis par DuckDB pour les arguments de fonctions table (contrairement à un `WHERE` normal) — évite une inconnue d'API supplémentaire. Le glob est construit uniquement à partir de `bucket` (config serveur) et `col.tenant_id`/`col.id` (identifiants internes déjà validés à l'enregistrement), donc sûr à interpoler directement (échappé par précaution).
7. **Filtres/group-by/mesures : rejet 400 si nom de colonne inconnu**, en réutilisant l'introspection Postgres existante de la collection (`TableInfo.columns`) — même frontière de confiance que `_where` (`app/features/repository.py`) pour `GET /items`, bien que les données interrogées viennent de DuckDB/Parquet et non de Postgres (le schéma, lui, reste la source de vérité côté Postgres).
8. **Coercion numérique par `TRY_CAST(... AS DOUBLE)` + `COALESCE(..., 0)`**, plutôt que de répliquer exactement `Number(x) || 0` (TS) : une valeur non numérique devient `NULL` puis est ignorée par `SUM`/`AVG`/`MIN`/`MAX` (résultat identique à la substitution par 0 dans l'immense majorité des cas réels — un champ numérique mal typé est une donnée déjà anormale) plutôt que codée en dur comme zéro contribuant au compte. Différence assumée, non testée explicitement (hors périmètre des critères d'acceptation).

---

### Task 1: Spike go/no-go — DuckDB `httpfs`+`spatial` contre un GeoParquet réel produit par SP-11a (tâche d'ouverture, bloquante)

**Files:**
- Modify: `core/pyproject.toml` (ajoute `duckdb>=1.0`)
- Modify: `core/Dockerfile` (ajoute `"duckdb>=1.0"` à la liste `uv pip install --system`)
- Create: `core/scripts/spike_duckdb_geoparquet.py`
- Test: aucun test pytest — script empirique jetable contre un MinIO réel (docker-compose), même patron que `core/scripts/spike_cdc_replication.py` (SP-11a Task 1) et `spike_pgbouncer_rls.py` (SP-3b).

**Interfaces:**
- Produces: confirmation empirique de la syntaxe DuckDB exacte pour lire un GeoParquet écrit par `geopandas.to_parquet` (colonne géométrie WKB) via `httpfs`+`spatial`, filtrer par bbox (`ST_Intersects`) et réduire par fenêtre (`QUALIFY row_number() ... = 1`). Si la syntaxe présumée ci-dessous échoue, la corriger ICI puis répercuter sur Task 6 (`app/analytics/aggregate.py`) avant de l'exécuter.

- [ ] **Step 1: Ajouter `duckdb` comme dépendance**

Dans `core/pyproject.toml`, ajouter dans `dependencies` après `"pgvector>=0.3",` :

```toml
    "duckdb>=1.0",  # SP-11b : module analytique — lit le GeoParquet CDC (SP-11a)
                    # via httpfs (S3/MinIO) + spatial (ST_Intersects sur la colonne
                    # géométrie WKB), connexion in-process éphémère par requête.
```

Dans `core/Dockerfile`, ajouter `"duckdb>=1.0"` à la liste `uv pip install --system --no-cache`.

```bash
cd core && uv sync
```

- [ ] **Step 2: Écrire le script spike**

Créer `core/scripts/spike_duckdb_geoparquet.py` :

```python
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
```

- [ ] **Step 3: Exécuter le spike contre un MinIO réel**

```bash
docker compose up -d minio
cd core && S3_ENDPOINT_URL=http://127.0.0.1:9000 \
  S3_ACCESS_KEY=${MINIO_USER} S3_SECRET_KEY=${MINIO_PASSWORD} \
  uv run python -m scripts.spike_duckdb_geoparquet
```

Expected: `Résultat spike : PASS`, avec une ligne `INCANTATION BBOX RETENUE POUR TASK 6 : ...`.

**GATE — si le spike ne passe pas PASS après investigation raisonnable (documenter ce qui a été essayé) : arrêter le plan ici.** Ne pas continuer vers Task 2 sans un PASS réel — c'est le go/no-go que la spec impose explicitement (§Risques : compatibilité DuckDB spatial ↔ GeoParquet non vérifiée). Si l'incantation bbox retenue est `ST_GeomFromWKB`, répercuter ce choix sur `_build_where` dans Task 6 (le code présumé de Task 6 utilise déjà cette forme par défaut — si c'est plutôt la forme "native GEOMETRY" qui gagne, retirer l'appel `ST_GeomFromWKB(...)` dans Task 6).

- [ ] **Step 4: Commit**

```bash
git add core/pyproject.toml core/Dockerfile core/uv.lock core/scripts/spike_duckdb_geoparquet.py
git commit -m "feat(core): SP-11b — spike go/no-go DuckDB httpfs+spatial contre GeoParquet réel"
```

---

### Task 2: Primitives S3 pour la compaction (`app/cdc/storage.py`)

**Files:**
- Modify: `core/app/cdc/storage.py`
- Modify: `core/tests/test_cdc_storage.py`

**Interfaces:**
- Consumes: `_FakeS3Client` déjà présent dans `test_cdc_storage.py` (étendu).
- Produces: `list_objects(client, *, bucket, prefix) -> list[dict]` (chaque élément `{"key": str, "size": int}`, pagine via `ContinuationToken`) ; `delete_objects(client, *, bucket, keys: list[str]) -> None` ; `upload_bytes(client, *, bucket, key, data: bytes) -> None`. Consommé par Task 3 (`app/cdc/compaction.py`). `download_object` est déjà fourni par `app.ingestion.storage` (réutilisé tel quel, pas réimplémenté).

- [ ] **Step 1: Étendre le test (échoue — les fonctions n'existent pas)**

Ajouter à `core/tests/test_cdc_storage.py` (après les tests existants, `_FakeS3Client` étendu en place) :

```python
class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.uploaded: list[tuple[str, str, str]] = []  # (local_path, bucket, key)
        self.objects: dict[str, bytes] = {}  # key -> body, pour list/delete/upload_bytes
        self.deleted: list[str] = []

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        self.uploaded.append((Filename, Bucket, Key))

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        matching = sorted(k for k in self.objects if k.startswith(Prefix))
        # Pagine par lots de 2 pour exercer la boucle ContinuationToken.
        page_size = 2
        start = int(ContinuationToken) if ContinuationToken else 0
        page = matching[start:start + page_size]
        truncated = start + page_size < len(matching)
        return {
            "Contents": [{"Key": k, "Size": len(self.objects[k])} for k in page],
            "IsTruncated": truncated,
            "NextContinuationToken": str(start + page_size) if truncated else None,
        }

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        keys = [o["Key"] for o in Delete["Objects"]]
        for k in keys:
            self.objects.pop(k, None)
            self.deleted.append(k)

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        from io import BytesIO
        return {"Body": BytesIO(self.objects[Key])}


def test_list_objects_returns_key_and_size():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"12345", "cdc/b.parquet": b"1234567890"}
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert sorted(result, key=lambda o: o["key"]) == [
        {"key": "cdc/a.parquet", "size": 5}, {"key": "cdc/b.parquet", "size": 10},
    ]


def test_list_objects_paginates_across_multiple_pages():
    client = _FakeS3Client()
    client.objects = {f"cdc/{i}.parquet": b"x" for i in range(5)}  # 5 objets, pages de 2
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert len(result) == 5  # sans la boucle de pagination, seuls les 2 premiers reviendraient


def test_list_objects_filters_by_prefix():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"x", "other/b.parquet": b"x"}
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert [o["key"] for o in result] == ["cdc/a.parquet"]


def test_delete_objects_removes_all_given_keys():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"x", "cdc/b.parquet": b"y"}
    delete_objects(client, bucket="b", keys=["cdc/a.parquet"])
    assert "cdc/a.parquet" not in client.objects
    assert "cdc/b.parquet" in client.objects
    assert client.deleted == ["cdc/a.parquet"]


def test_upload_bytes_writes_via_put_object():
    client = _FakeS3Client()
    upload_bytes(client, bucket="b", key="cdc/merged.parquet", data=b"payload")
    assert client.objects["cdc/merged.parquet"] == b"payload"
```

Et ajouter à l'import en tête de fichier :

```python
from app.cdc.storage import (
    delete_objects, ensure_cdc_bucket, list_objects, upload_bytes, upload_parquet_file,
)
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_storage.py -v
```

Expected: FAIL — `ImportError: cannot import name 'list_objects' from 'app.cdc.storage'`.

- [ ] **Step 3: Ajouter les 3 fonctions à `core/app/cdc/storage.py`**

```python
def list_objects(client, *, bucket: str, prefix: str) -> list[dict]:
    """Liste paginée (list_objects_v2 ne renvoie qu'1000 clés par appel) —
    une collection à forte écriture accumule aisément plus de fichiers que
    ça avant un cycle de compaction ; une boucle non paginée tronquerait
    silencieusement la découverte des partitions (cf. test dédié)."""
    objects: list[dict] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            objects.append({"key": obj["Key"], "size": obj["Size"]})
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return objects


def delete_objects(client, *, bucket: str, keys: list[str]) -> None:
    client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys]})


def upload_bytes(client, *, bucket: str, key: str, data: bytes) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data)
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_storage.py -v
```

Expected: 9 passed (5 existants + 4 nouveaux — `test_list_objects_returns_key_and_size` compte pour 1, plus les 3 autres list/delete/upload).

- [ ] **Step 5: Commit**

```bash
git add core/app/cdc/storage.py core/tests/test_cdc_storage.py
git commit -m "feat(core): SP-11b — primitives S3 list/delete/upload pour la compaction"
```

---

### Task 3: Algorithme de compaction (`app/cdc/compaction.py`)

**Files:**
- Create: `core/app/cdc/compaction.py`
- Create: `core/tests/test_cdc_compaction.py`

**Interfaces:**
- Consumes: `app.cdc.storage.list_objects`/`delete_objects`/`upload_bytes` (Task 2), `app.ingestion.storage.download_object` (déjà existant, ré-exporté par `app.cdc.storage`).
- Produces: `DEFAULT_SIZE_THRESHOLD_BYTES` ; `CompactionReport` (dataclass : `partitions_scanned: int`, `partitions_compacted: int`, `files_removed: int`) ; `group_by_partition(objects) -> dict[str, list[dict]]` ; `select_files_to_merge(files, *, size_threshold_bytes) -> list[dict]` ; `merge_geoparquet(byte_blobs: list[bytes]) -> bytes` ; `compact_partition(client, *, bucket, partition_prefix, files, size_threshold_bytes) -> int` (nombre de fichiers fusionnés, 0 si rien à faire) ; `run_compaction_cycle(client, *, bucket, size_threshold_bytes=DEFAULT_SIZE_THRESHOLD_BYTES) -> CompactionReport`. Consommé par Task 4 (`app/cdc/jobs.py`).

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/tests/test_cdc_compaction.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from io import BytesIO

import geopandas as gpd
from shapely.geometry import Point

from app.cdc.compaction import (
    CompactionReport, compact_partition, group_by_partition, merge_geoparquet,
    run_compaction_cycle, select_files_to_merge,
)


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.delete_should_fail = False

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        matching = sorted(k for k in self.objects if k.startswith(Prefix))
        return {"Contents": [{"Key": k, "Size": len(self.objects[k])} for k in matching],
                "IsTruncated": False}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": BytesIO(self.objects[Key])}

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[Key] = Body

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        if self.delete_should_fail:
            raise RuntimeError("simulated crash between upload and delete")
        for o in Delete["Objects"]:
            self.objects.pop(o["Key"], None)
            self.deleted.append(o["Key"])


def _geoparquet_bytes(rows: list[dict]) -> bytes:
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    buf = BytesIO()
    gdf.to_parquet(buf)
    return buf.getvalue()


def _read_all_current(client, keys: list[str]) -> list[tuple]:
    """Aide de test : réduction (pk, max(_lsn)) minimale, juste assez pour
    comparer un résultat de lecture avant/après compaction — la vraie
    réduction complète vit dans le module analytique (Task 6)."""
    frames = [gpd.read_parquet(BytesIO(client.objects[k])) for k in keys if k in client.objects]
    import pandas as pd
    all_rows = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if all_rows.empty:
        return []
    current = all_rows.sort_values("_lsn").groupby("id").tail(1)
    current = current[current["_op"] != "delete"]
    return sorted(zip(current["id"], current["titre"]))


PARTITION = "cdc/tenant_id=t1/collection_id=c1/dt=2026-07-18/"


def test_group_by_partition_groups_files_under_the_same_prefix():
    objects = [
        {"key": f"{PARTITION}part-a.parquet", "size": 10},
        {"key": f"{PARTITION}part-b.parquet", "size": 10},
        {"key": "cdc/tenant_id=t1/collection_id=c2/dt=2026-07-18/part-c.parquet", "size": 10},
    ]
    groups = group_by_partition(objects)
    assert set(groups.keys()) == {PARTITION, "cdc/tenant_id=t1/collection_id=c2/dt=2026-07-18/"}
    assert len(groups[PARTITION]) == 2


def test_select_files_to_merge_excludes_large_files():
    files = [{"key": "a", "size": 10}, {"key": "b", "size": 10}, {"key": "big", "size": 100}]
    selected = select_files_to_merge(files, size_threshold_bytes=50)
    assert {f["key"] for f in selected} == {"a", "b"}


def test_select_files_to_merge_returns_empty_when_at_most_one_eligible():
    files = [{"key": "a", "size": 10}, {"key": "big", "size": 100}]
    assert select_files_to_merge(files, size_threshold_bytes=50) == []


def test_merge_geoparquet_concatenates_and_preserves_crs():
    blob1 = _geoparquet_bytes([{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
                                "geometry": Point(0, 0)}])
    blob2 = _geoparquet_bytes([{"id": 2, "titre": "b", "_op": "insert", "_lsn": 2, "_ts": 2.0,
                                "geometry": Point(1, 1)}])
    merged = merge_geoparquet([blob1, blob2])
    gdf = gpd.read_parquet(BytesIO(merged))
    assert len(gdf) == 2
    assert gdf.crs.to_epsg() == 4326
    assert sorted(gdf["id"]) == [1, 2]


def test_compact_partition_merges_eligible_files_and_removes_originals():
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}])
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}])
    files = [{"key": k, "size": len(v)} for k, v in client.objects.items()]

    merged_count = compact_partition(
        client, bucket="b", partition_prefix=PARTITION, files=files, size_threshold_bytes=50,
    )

    assert merged_count == 2
    remaining = list(client.objects.keys())
    assert len(remaining) == 1  # les 2 originaux ont disparu, remplacés par 1 fichier fusionné
    assert remaining[0].startswith(PARTITION) and remaining[0] not in {f["key"] for f in files}
    assert _read_all_current(client, remaining) == [(1, "b")]  # lsn max gagne, résultat inchangé


def test_compact_partition_skips_when_nothing_eligible():
    client = _FakeS3Client()
    big = b"x" * 100
    client.objects[f"{PARTITION}part-big.parquet"] = big
    files = [{"key": f"{PARTITION}part-big.parquet", "size": 100}]
    merged_count = compact_partition(
        client, bucket="b", partition_prefix=PARTITION, files=files, size_threshold_bytes=50,
    )
    assert merged_count == 0
    assert list(client.objects.keys()) == [f"{PARTITION}part-big.parquet"]  # non touché


def test_compact_partition_writes_merged_file_before_deleting_originals_on_crash():
    """Sûreté à l'interruption : si delete_objects crashe APRÈS l'upload
    (simulé ici), le fichier fusionné doit déjà exister aux côtés des
    originaux — jamais de perte, juste des doublons inoffensifs (réduits
    par (pk, max(_lsn)) à la lecture, Task 6)."""
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}])
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 2, "titre": "b", "_op": "insert", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}])
    files = [{"key": k, "size": len(v)} for k, v in client.objects.items()]
    client.delete_should_fail = True

    try:
        compact_partition(client, bucket="b", partition_prefix=PARTITION, files=files,
                          size_threshold_bytes=50)
    except RuntimeError:
        pass

    keys = list(client.objects.keys())
    assert len(keys) == 3  # 2 originaux + 1 fusionné : rien supprimé, rien perdu
    assert _read_all_current(client, keys) == [(1, "a"), (2, "b")]  # résultat inchangé malgré le doublon


def test_run_compaction_cycle_reports_across_partitions():
    client = _FakeS3Client()
    client.objects[f"{PARTITION}part-a.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)}])
    client.objects[f"{PARTITION}part-b.parquet"] = _geoparquet_bytes(
        [{"id": 1, "titre": "b", "_op": "update", "_lsn": 2, "_ts": 2.0, "geometry": Point(1, 1)}])
    other_prefix = "cdc/tenant_id=t2/collection_id=c9/dt=2026-07-18/"
    client.objects[f"{other_prefix}part-only.parquet"] = b"x" * 100  # seul, jamais éligible

    report = run_compaction_cycle(client, bucket="b", size_threshold_bytes=50)

    assert report == CompactionReport(partitions_scanned=2, partitions_compacted=1, files_removed=2)
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_cdc_compaction.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.cdc.compaction'`.

- [ ] **Step 3: Écrire `core/app/cdc/compaction.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Compaction périodique du change-log GeoParquet CDC (SP-11b) : fusionne
les petits fichiers d'une même partition tenant_id=/collection_id=/dt= en
un seul, SANS jamais changer la sémantique de change-log — toujours
append-only en sortie, aucune déduplication ni suppression de tombstone à
l'écriture (cf. spec §Architecture, "approche A"). La réduction à l'état
courant reste entièrement à la charge du lecteur (app.analytics).

Sûreté à l'interruption : le fichier fusionné est TOUJOURS écrit avant la
suppression des fichiers d'entrée (compact_partition), jamais l'inverse.
Un crash entre les deux laisse des doublons inoffensifs (le lecteur réduit
par (pk, max(_lsn))), jamais de perte ni de suppression partielle
dangereuse — aucun verrou ni coordination avec le worker CDC nécessaire."""
import re
import uuid
from dataclasses import dataclass
from io import BytesIO

import geopandas as gpd
import pandas as pd

from app.cdc import storage
from app.ingestion.storage import download_object

CDC_PREFIX = "cdc/"
DEFAULT_SIZE_THRESHOLD_BYTES = 32 * 1024 * 1024

_PARTITION_RE = re.compile(r"^cdc/tenant_id=[^/]+/collection_id=[^/]+/dt=[^/]+/")


@dataclass
class CompactionReport:
    partitions_scanned: int
    partitions_compacted: int
    files_removed: int


def group_by_partition(objects: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for obj in objects:
        m = _PARTITION_RE.match(obj["key"])
        if m is None:
            continue
        groups.setdefault(m.group(0), []).append(obj)
    return groups


def select_files_to_merge(files: list[dict], *, size_threshold_bytes: int) -> list[dict]:
    eligible = [f for f in files if f["size"] < size_threshold_bytes]
    return eligible if len(eligible) > 1 else []


def merge_geoparquet(byte_blobs: list[bytes]) -> bytes:
    frames = [gpd.read_parquet(BytesIO(b)) for b in byte_blobs]
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    buf = BytesIO()
    merged.to_parquet(buf)
    return buf.getvalue()


def compact_partition(
    client, *, bucket: str, partition_prefix: str, files: list[dict], size_threshold_bytes: int,
) -> int:
    to_merge = select_files_to_merge(files, size_threshold_bytes=size_threshold_bytes)
    if not to_merge:
        return 0
    blobs = [download_object(client, bucket=bucket, key=f["key"]) for f in to_merge]
    merged_bytes = merge_geoparquet(blobs)
    new_key = f"{partition_prefix}part-{uuid.uuid4().hex}.parquet"
    # Écriture AVANT suppression, jamais l'inverse (cf. docstring module).
    storage.upload_bytes(client, bucket=bucket, key=new_key, data=merged_bytes)
    storage.delete_objects(client, bucket=bucket, keys=[f["key"] for f in to_merge])
    return len(to_merge)


def run_compaction_cycle(
    client, *, bucket: str, size_threshold_bytes: int = DEFAULT_SIZE_THRESHOLD_BYTES,
) -> CompactionReport:
    objects = storage.list_objects(client, bucket=bucket, prefix=CDC_PREFIX)
    groups = group_by_partition(objects)
    partitions_compacted = 0
    files_removed = 0
    for partition_prefix, files in groups.items():
        merged_count = compact_partition(
            client, bucket=bucket, partition_prefix=partition_prefix, files=files,
            size_threshold_bytes=size_threshold_bytes,
        )
        if merged_count:
            partitions_compacted += 1
            files_removed += merged_count
    return CompactionReport(
        partitions_scanned=len(groups), partitions_compacted=partitions_compacted,
        files_removed=files_removed,
    )
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_cdc_compaction.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/cdc/compaction.py core/tests/test_cdc_compaction.py
git commit -m "feat(core): SP-11b — algorithme de compaction GeoParquet (app.cdc.compaction)"
```

---

### Task 4: Job procrastinate périodique (`app/cdc/jobs.py`) + wiring worker

**Files:**
- Create: `core/app/cdc/jobs.py`
- Modify: `core/app/jobs.py` (ajoute `"app.cdc.jobs"` à `import_paths`)
- Modify: `docker-compose.yml` (queue `cdc` sur le service `worker`, `S3_CDC_BUCKET` sur `core` et `worker`)
- Modify: `core/tests/test_jobs.py`

**Interfaces:**
- Consumes: `app.jobs.app` (App procrastinate partagée), `app.cdc.compaction.run_compaction_cycle`, `app.cdc.storage.make_s3_client`/`ensure_cdc_bucket`.
- Produces: `run_compaction_cycle_task(timestamp: int) -> None`, enregistrée sur la queue `cdc`, périodique (`cron="*/10 * * * *"`).

- [ ] **Step 1: Écrire `core/app/cdc/jobs.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Job périodique de compaction (SP-11b) — tourne dans le process `worker`
partagé (docker-compose.yml), PAS dans cdc-worker : ce dernier est occupé en
continu par consumer.stream_changes (boucle bloquante), il n'a jamais de
créneau pour exécuter un job procrastinate. La compaction n'a besoin
d'aucun accès Postgres (le layout S3 encode déjà tenant_id/collection_id
dans chaque clé), seulement d'un client S3 — même client que app.cdc.main,
credentials identiques."""
import logging
import os

from app.cdc import compaction, storage
from app.jobs import app

logger = logging.getLogger(__name__)


@app.periodic(cron="*/10 * * * *")
@app.task(queue="cdc")
def run_compaction_cycle_task(timestamp: int) -> None:
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(client, bucket)
    report = compaction.run_compaction_cycle(client, bucket=bucket)
    logger.info(
        "compaction cycle: %s partitions scanned, %s compacted, %s files removed",
        report.partitions_scanned, report.partitions_compacted, report.files_removed,
    )
```

- [ ] **Step 2: Étendre `core/tests/test_jobs.py` (échoue — nouvelle tâche pas encore enregistrée)**

Modifier `test_import_paths_registers_all_domain_tasks` :

```python
    task_names = set(result.stdout.strip().splitlines())
    assert "app.ingestion.tasks.run_ingestion_task" in task_names
    assert "app.items.jobs.embed_item_task" in task_names
    assert "app.collections.jobs.embed_collection_task" in task_names
    assert "app.cdc.jobs.run_compaction_cycle_task" in task_names
```

- [ ] **Step 3: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_jobs.py -v
```

Expected: FAIL sur la nouvelle assertion — `app.cdc.jobs.run_compaction_cycle_task` absente (import_paths de `app/jobs.py` ne référence pas encore `app.cdc.jobs`).

- [ ] **Step 4: Ajouter `app.cdc.jobs` à `import_paths` (`core/app/jobs.py`)**

```python
    import_paths=["app.ingestion.tasks", "app.items.jobs", "app.collections.jobs", "app.cdc.jobs"],
```

- [ ] **Step 5: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_jobs.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Wirer la queue `cdc` et `S3_CDC_BUCKET` dans `docker-compose.yml`**

Modifier le `command:` du service `worker` :

```yaml
    command: >
      sh -c "python -m procrastinate --app app.jobs.app schema --apply &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc"
```

Ajouter `S3_CDC_BUCKET: geostudio-cdc` à l'`environment:` du service `worker` (après `S3_UPLOADS_BUCKET`) et à celui du service `core` (après `S3_UPLOADS_BUCKET` également — `core` en aura besoin en Task 7 pour construire le glob DuckDB).

- [ ] **Step 7: Vérification empirique — le worker réel démarre et enregistre la tâche périodique**

```bash
docker compose up -d --build worker
docker compose logs worker --tail 50
```

Expected: pas de crash-loop ; les logs procrastinate mentionnent le déferreur périodique démarré (`Starting periodic deferrer` ou équivalent selon la version). Pas d'assertion automatisée ici — vérification manuelle, comme SP-11a Task 10.

- [ ] **Step 8: Commit**

```bash
git add core/app/cdc/jobs.py core/app/jobs.py core/tests/test_jobs.py docker-compose.yml
git commit -m "feat(core): SP-11b — job périodique de compaction (queue cdc, toutes les 10 min)"
```

---

### Task 5: Connexion DuckDB (`app/analytics/duckdb_conn.py`)

**Files:**
- Create: `core/app/analytics/__init__.py` (vide)
- Create: `core/app/analytics/duckdb_conn.py`
- Create: `core/tests/test_analytics_duckdb_conn.py`

**Interfaces:**
- Produces: `open_connection(*, endpoint_url: str, access_key: str, secret_key: str) -> duckdb.DuckDBPyConnection`. Consommé par Task 6 (tests, en pointant vers des fichiers locaux — `httpfs`/S3 non nécessaire pour ces tests) et Task 7 (dépendance FastAPI, chemin réel).

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/app/analytics/__init__.py` (vide) et `core/tests/test_analytics_duckdb_conn.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Teste la SÉQUENCE de configuration (extensions + S3), pas la connectivité
réseau réelle (ça, c'est le spike Task 1 + le script empirique Task 10) —
via un connecteur DuckDB réel en mémoire, en interceptant .execute() pour
capturer les statements exécutés sans réseau."""
from app.analytics.duckdb_conn import open_connection


class _RecordingConnection:
    def __init__(self, real):
        self._real = real
        self.statements: list[str] = []

    def execute(self, sql, *args, **kwargs):
        self.statements.append(sql)
        return self._real.execute(sql, *args, **kwargs)


def test_open_connection_installs_and_loads_httpfs_and_spatial(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    assert "INSTALL httpfs" in joined and "LOAD httpfs" in joined
    assert "INSTALL spatial" in joined and "LOAD spatial" in joined


def test_open_connection_configures_s3_settings_from_endpoint(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="http://minio:9000", access_key="ak", secret_key="sk")

    joined = "\n".join(recording.statements)
    assert "s3_endpoint = 'minio:9000'" in joined
    assert "s3_use_ssl = false" in joined
    assert "s3_url_style = 'path'" in joined
    assert "s3_access_key_id = 'ak'" in joined
    assert "s3_secret_access_key = 'sk'" in joined


def test_open_connection_detects_https_endpoint(monkeypatch):
    import duckdb

    real_conn = duckdb.connect(":memory:")
    recording = _RecordingConnection(real_conn)
    monkeypatch.setattr(duckdb, "connect", lambda *_a, **_kw: recording)

    open_connection(endpoint_url="https://minio.example.com", access_key="ak", secret_key="sk")

    assert "s3_use_ssl = true" in "\n".join(recording.statements)
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.analytics.duckdb_conn'`.

- [ ] **Step 3: Écrire `core/app/analytics/duckdb_conn.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Connexion DuckDB in-process, ÉPHÉMÈRE PAR REQUÊTE (SP-11b) — pas de pool
ni de connexion partagée entre requêtes concurrentes (simplicité d'abord,
le coût de chargement des extensions — dizaines de ms — est négligeable
face au budget de 2s ; cf. spec §Architecture, à revisiter seulement si le
profilage montre un goulot réel). Extensions httpfs (lecture S3/MinIO) et
spatial (ST_Intersects sur la colonne géométrie WKB du GeoParquet CDC)
installées une fois sur le disque de l'image, chargées à chaque connexion.

Les valeurs SET ci-dessous viennent de variables d'environnement serveur
(pas d'entrée utilisateur) : interpolées directement, comme le reste du
cœur fait déjà confiance à ses propres variables d'environnement (ex.
CORE_BASE_URL dans app/main.py)."""
import duckdb


def open_connection(*, endpoint_url: str, access_key: str, secret_key: str) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    host = endpoint_url.split("://", 1)[-1]
    use_ssl = endpoint_url.startswith("https://")
    conn.execute(f"SET s3_endpoint = '{host}'")
    conn.execute(f"SET s3_use_ssl = {str(use_ssl).lower()}")
    conn.execute("SET s3_url_style = 'path'")
    conn.execute(f"SET s3_access_key_id = '{access_key}'")
    conn.execute(f"SET s3_secret_access_key = '{secret_key}'")
    return conn
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_analytics_duckdb_conn.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/__init__.py core/app/analytics/duckdb_conn.py core/tests/test_analytics_duckdb_conn.py
git commit -m "feat(core): SP-11b — connexion DuckDB éphémère (httpfs+spatial) — app.analytics.duckdb_conn"
```

---

### Task 6: Module analytique — requête, filtres, group-by/mesures (`app/analytics/aggregate.py`)

**Files:**
- Create: `core/app/analytics/aggregate.py`
- Create: `core/tests/test_analytics_aggregate.py`

**Interfaces:**
- Consumes: `app.collections.introspection.TableInfo`/`ColumnInfo` (validation des noms de colonnes).
- Produces: `AggregateMeasure` (pydantic : `field: str | None`, `agg: str = "count"`, `label: str | None`) ; `AggregateRequestBody` (pydantic : `groupBy: str | None`, `split: str | None`, `agg: str = "count"`, `field: str | None`, `measures: list[AggregateMeasure] | None`, `filters: dict[str, str] = {}`, `bbox: tuple[float, float, float, float] | None`) ; `UnknownAggregateField` (exception : `field: str`, `message: str`) ; `run_collection_aggregate(conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info: TableInfo, request: AggregateRequestBody) -> tuple[str, list[dict]]`. Consommé par Task 7 (endpoint REST).

- [ ] **Step 1: Écrire le test (échoue — le module n'existe pas)**

Créer `core/tests/test_analytics_aggregate.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Tests SANS MinIO réel : DuckDB lit des chemins LOCAUX (tmp_path) exactement
comme il lirait s3:// (même read_parquet/glob, DuckDB dispatche sur le schéma
du chemin) — seule la connectivité réseau réelle est hors du périmètre de ces
tests (prouvée par le spike Task 1 + le script empirique Task 10)."""
import duckdb
import geopandas as gpd
import pytest
from shapely.geometry import Point

from app.analytics.aggregate import (
    AggregateMeasure, AggregateRequestBody, UnknownAggregateField, run_collection_aggregate,
)
from app.collections.introspection import ColumnInfo, TableInfo

TABLE_INFO = TableInfo(
    table_name="villes", pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="annee", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")  # bbox, pas de httpfs (chemins locaux)
    return c


def _write_partition(base_dir, *, tenant_id="t1", collection_id="villes", rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _row(id_, region, annee, pop, *, op="insert", lsn=1, x=0.0, y=0.0):
    return {"id": id_, "region": region, "annee": annee, "pop": pop, "_op": op, "_lsn": lsn,
            "_ts": 1.0, "geometry": Point(x, y)}


def test_group_by_with_split_produces_wide_rows_matching_client_contract(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2026", 12, lsn=1),
        _row(3, "Sud", "2025", 5, lsn=1), _row(4, "Sud", "2026", 7, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", split="annee", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "region"
    by_region = {r["region"]: r for r in rows}
    assert by_region["Nord"] == {"region": "Nord", "2025": 10, "2026": 12}
    assert by_region["Sud"] == {"region": "Sud", "2025": 5, "2026": 7}


def test_group_by_without_split_uses_single_measure_labeled_value(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1),
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "region"
    assert sorted(rows, key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10}, {"region": "Sud", "value": 5},
    ]


def test_multiple_measures_use_their_own_labels(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Nord", "2025", 20, lsn=1)])
    request = AggregateRequestBody(
        groupBy="region",
        measures=[AggregateMeasure(agg="sum", field="pop", label="total"),
                  AggregateMeasure(agg="count", label="nb")],
    )

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "total": 30, "nb": 2}]


def test_no_group_by_produces_a_single_total_row(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(agg="sum", field="pop")

    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert category_key == "group"
    assert rows == [{"group": "Total", "value": 15}]


def test_reduces_to_current_state_last_lsn_wins_and_tombstone_excluded(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1),
        _row(1, "Nord", "2025", 999, lsn=5),  # update : doit gagner
        _row(2, "Sud", "2025", 5, lsn=1),
        _row(2, "Sud", "2025", 0, lsn=2, op="delete"),  # tombstone : doit disparaître
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop")

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 999}]  # Sud entièrement supprimé


def test_attribute_filter_narrows_rows(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1), _row(2, "Sud", "2025", 5, lsn=1)])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", filters={"region": "Nord"})

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_bbox_filter_narrows_rows_spatially(tmp_path, conn):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", "2025", 10, lsn=1, x=2.3, y=48.8),  # dans le bbox
        _row(2, "Sud", "2025", 5, lsn=1, x=100.0, y=50.0),  # hors bbox
    ])
    request = AggregateRequestBody(groupBy="region", agg="sum", field="pop", bbox=(2.0, 48.0, 3.0, 49.0))

    _category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=request,
    )

    assert rows == [{"region": "Nord", "value": 10}]


def test_empty_collection_returns_empty_rows_without_error(tmp_path, conn):
    # Aucune partition écrite du tout — même chemin que "collection jamais flushée".
    category_key, rows = run_collection_aggregate(
        conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
        table_info=TABLE_INFO, request=AggregateRequestBody(groupBy="region"),
    )
    assert category_key == "region"
    assert rows == []


def test_unknown_group_by_field_raises_with_field_name(tmp_path, conn):
    _write_partition(tmp_path, rows=[_row(1, "Nord", "2025", 10, lsn=1)])
    request = AggregateRequestBody(groupBy="inconnu")
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            conn, base_uri=str(tmp_path), tenant_id="t1", collection_id="villes",
            table_info=TABLE_INFO, request=request,
        )
    assert exc_info.value.field == "groupBy"


def test_bbox_without_geometry_column_raises():
    info_no_geom = TableInfo(table_name="t", pk_column="id", geometry_column=None,
                             geometry_type=None, srid=None, columns=[])
    request = AggregateRequestBody(bbox=(0, 0, 1, 1))
    with pytest.raises(UnknownAggregateField) as exc_info:
        run_collection_aggregate(
            duckdb.connect(":memory:"), base_uri="/nonexistent", tenant_id="t1",
            collection_id="c", table_info=info_no_geom, request=request,
        )
    assert exc_info.value.field == "bbox"
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.analytics.aggregate'`.

- [ ] **Step 3: Écrire `core/app/analytics/aggregate.py`**

Note : la clause bbox ci-dessous utilise `ST_GeomFromWKB(...)`, l'incantation par défaut présumée par ce plan — **si le spike Task 1 a retenu l'incantation "native GEOMETRY" à la place, retirer l'appel `ST_GeomFromWKB(...)` et lire directement la colonne géométrie.**

```python
# SPDX-License-Identifier: Apache-2.0
"""Module analytique DuckDB (SP-11b, A18/A19) : agrège les données d'une
collection depuis son GeoParquet CDC (SP-11a), au lieu de fetcher les
features brutes et d'agréger côté client (aggregateRecords, supprimé côté
shell par ce plan). Réduction à l'état courant PUIS filtres PUIS group-by/
mesures, dans cet ordre — jamais l'inverse (un filtre appliqué avant
réduction pourrait retenir une ligne déjà remplacée par une version plus
récente)."""
from pydantic import BaseModel


class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None


class AggregateRequestBody(BaseModel):
    groupBy: str | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None


class UnknownAggregateField(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _valid_column_names(table_info) -> set[str]:
    names = {c.name for c in table_info.columns} | {table_info.pk_column}
    if table_info.geometry_column:
        names.add(table_info.geometry_column)
    return names


def _validate_fields(request: AggregateRequestBody, table_info) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    check(request.groupBy, "groupBy")
    check(request.split, "split")
    check(request.field, "field")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
    for name in request.filters:
        check(name, f"filters.{name}")
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")


def _agg_expr(agg: str, field: str | None) -> str:
    if agg == "count":
        return "COUNT(*)"
    if field is None:
        raise UnknownAggregateField("field", f"agg '{agg}' requires a field")
    col = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    if agg == "sum":
        return f"COALESCE(SUM({col}), 0)"
    if agg == "avg":
        return f"COALESCE(AVG({col}), 0)"
    if agg == "min":
        return f"COALESCE(MIN({col}), 0)"
    if agg == "max":
        return f"COALESCE(MAX({col}), 0)"
    raise UnknownAggregateField("agg", f"unknown agg '{agg}'")


def _measure_label(m: AggregateMeasure) -> str:
    return m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)


def _measures_for(request: AggregateRequestBody) -> list[AggregateMeasure]:
    if request.measures:
        return request.measures
    return [AggregateMeasure(field=request.field, agg=request.agg, label="value")]


def _build_where(request: AggregateRequestBody, table_info) -> tuple[str, list]:
    clauses = []
    params: list = []
    for name, value in request.filters.items():
        clauses.append(f"{_qi(name)} = ?")
        params.append(value)
    if request.bbox is not None:
        minx, miny, maxx, maxy = request.bbox
        clauses.append(
            f"ST_Intersects(ST_GeomFromWKB({_qi(table_info.geometry_column)}), "
            f"ST_MakeEnvelope(?, ?, ?, ?))"
        )
        params.extend([minx, miny, maxx, maxy])
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _pivot_split(sql_rows: list[dict], *, category_key: str) -> list[dict]:
    categories: list[str] = []
    by_cat: dict[str, dict] = {}
    splits: list[str] = []
    seen_splits: set[str] = set()
    for r in sql_rows:
        cat = str(r["__cat"])
        if cat not in by_cat:
            by_cat[cat] = {category_key: cat}
            categories.append(cat)
        sv = str(r["__split"])
        if sv not in seen_splits:
            seen_splits.add(sv)
            splits.append(sv)
        by_cat[cat][sv] = r["__val"]
    for cat in categories:
        row = by_cat[cat]
        for sv in splits:
            row.setdefault(sv, 0)
    return [by_cat[c] for c in categories]


def _pivot_measures(sql_rows: list[dict], *, category_key: str, measures: list[AggregateMeasure]) -> list[dict]:
    out = []
    for r in sql_rows:
        row = {category_key: str(r["__cat"])}
        for i, m in enumerate(measures):
            row[_measure_label(m)] = r[f"m{i}"]
        out.append(row)
    return out


def _dedup_cte(table_info, base_uri: str, tenant_id: str, collection_id: str) -> str:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    pk = _qi(table_info.pk_column)
    return (
        f"WITH raw AS (SELECT * FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true)), "
        f"current AS (SELECT * FROM raw QUALIFY row_number() OVER "
        f"(PARTITION BY {pk} ORDER BY _lsn DESC) = 1), "
        f"live AS (SELECT * FROM current WHERE _op != 'delete')"
    )


def _has_any_file(conn, base_uri: str, tenant_id: str, collection_id: str) -> bool:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _fetch_rows(conn, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in result]


def run_collection_aggregate(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info, request: AggregateRequestBody,
) -> tuple[str, list[dict]]:
    category_key = request.groupBy or "group"
    _validate_fields(request, table_info)

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)
    cat_expr = _qi(request.groupBy) if request.groupBy else "'Total'"

    if request.split:
        agg_sql = _agg_expr(request.agg, request.field)
        sql = (
            f"{dedup_cte} SELECT {cat_expr} AS __cat, {_qi(request.split)} AS __split, "
            f"{agg_sql} AS __val FROM live {where_sql} GROUP BY __cat, __split"
        )
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_split(sql_rows, category_key=category_key)

    measures = _measures_for(request)
    measure_cols = ", ".join(f"{_agg_expr(m.agg, m.field)} AS m{i}" for i, m in enumerate(measures))
    sql = f"{dedup_cte} SELECT {cat_expr} AS __cat, {measure_cols} FROM live {where_sql} GROUP BY __cat"
    sql_rows = _fetch_rows(conn, sql, where_params)
    return category_key, _pivot_measures(sql_rows, category_key=category_key, measures=measures)
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_analytics_aggregate.py -v
```

Expected: 10 passed. Si `test_bbox_filter_narrows_rows_spatially` échoue avec une erreur DuckDB sur `ST_GeomFromWKB`, appliquer la correction d'incantation notée par le spike Task 1 (retirer l'appel si la colonne est déjà lue comme `GEOMETRY` natif).

- [ ] **Step 5: Commit**

```bash
git add core/app/analytics/aggregate.py core/tests/test_analytics_aggregate.py
git commit -m "feat(core): SP-11b — module analytique DuckDB (app.analytics.aggregate)"
```

---

### Task 7: Endpoint `POST /collections/{collection_id}/aggregate` + exemption mode démo

**Files:**
- Modify: `core/app/features/routes.py`
- Modify: `core/app/main.py` (exemption `read_only_guard`)
- Modify: `core/tests/test_read_only_mode.py` (régression : l'endpoint reste accessible en mode démo)
- Create: `core/tests/test_features_aggregate_routes.py`

**Interfaces:**
- Consumes: `app.analytics.aggregate.run_collection_aggregate`/`AggregateRequestBody`/`UnknownAggregateField`, `app.analytics.duckdb_conn.open_connection`, `get_readable_collection`/`get_introspector` (déjà importés dans `features/routes.py`).
- Produces: dépendance FastAPI `get_duckdb_connection_factory()` (overridable en test) ; route `POST /collections/{collection_id}/aggregate`.

- [ ] **Step 1: Écrire le test (échoue — la route n'existe pas)**

Créer `core/tests/test_features_aggregate_routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import duckdb
import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(table_name="villes", pk_column="id", geometry_column="geometry",
                 geometry_type="Point", srid=4326,
                 columns=[ColumnInfo(name="region", type="string", required=True),
                          ColumnInfo(name="pop", type="integer", required=True)])


def fake_introspector(session, table_name):
    if table_name != "villes":
        raise TableNotFound(table_name)
    return INFO


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-07-18"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(tmp_path):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (lambda session, table: None)

    def fake_duckdb_factory():
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        return conn

    app.dependency_overrides[features_routes.get_duckdb_connection_factory] = lambda: fake_duckdb_factory
    monkeypatch_base_uri = str(tmp_path)
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: monkeypatch_base_uri

    client = TestClient(app)
    return app, client, admin, regular, tmp_path, tenant_id


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    return client.post("/collections", json={"tableName": "villes", "isPublic": public}).json()


def test_aggregate_returns_wide_rows_for_a_readable_collection(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=col["id"], rows=[
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)},
        {"id": 2, "region": "Sud", "pop": 5, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(1, 1)},
    ])

    response = client.post(f"/collections/{col['id']}/aggregate",
                           json={"groupBy": "region", "agg": "sum", "field": "pop"})

    assert response.status_code == 200
    body = response.json()
    assert body["categoryKey"] == "region"
    assert sorted(body["rows"], key=lambda r: r["region"]) == [
        {"region": "Nord", "value": 10}, {"region": "Sud", "value": 5},
    ]


def test_aggregate_on_unregistered_collection_returns_404(env):
    _app, client, _admin, regular, _tmp_path, _tenant_id = env
    _as(_app, regular)
    response = client.post("/collections/does-not-exist/aggregate", json={"groupBy": "region"})
    assert response.status_code == 404


def test_aggregate_on_private_collection_by_non_owner_returns_404(env):
    app, client, admin, regular, _tmp_path, _tenant_id = env
    col = _register(app, client, admin, public=False)
    _as(app, regular)
    response = client.post(f"/collections/{col['id']}/aggregate", json={"groupBy": "region"})
    assert response.status_code == 404  # cohérent avec GET /collections/{id}/items


def test_aggregate_unknown_group_by_field_returns_400(env):
    app, client, admin, _r, tmp_path, tenant_id = env
    col = _register(app, client, admin)
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=col["id"], rows=[
        {"id": 1, "region": "Nord", "pop": 10, "_op": "insert", "_lsn": 1, "_ts": 1.0, "geometry": Point(0, 0)},
    ])
    response = client.post(f"/collections/{col['id']}/aggregate", json={"groupBy": "inconnu"})
    assert response.status_code == 400
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

```bash
cd core && uv run pytest tests/test_features_aggregate_routes.py -v
```

Expected: FAIL — 404 sur toutes les requêtes (route inexistante) et `AttributeError: module 'app.features.routes' has no attribute 'get_duckdb_connection_factory'`.

- [ ] **Step 3: Ajouter la route à `core/app/features/routes.py`**

Ajouter les imports en tête de fichier :

```python
import os

from app.analytics.aggregate import AggregateRequestBody, UnknownAggregateField, run_collection_aggregate
```

Ajouter, après `list_features` :

```python
def get_duckdb_connection_factory():  # overridé en test
    from app.analytics.duckdb_conn import open_connection

    def factory():
        return open_connection(
            endpoint_url=os.environ["S3_ENDPOINT_URL"],
            access_key=os.environ["S3_ACCESS_KEY"],
            secret_key=os.environ["S3_SECRET_KEY"],
        )
    return factory


def get_analytics_base_uri():  # overridé en test (pointe un répertoire tmp_path local)
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    return f"s3://{bucket}/cdc"


@router.post("/collections/{collection_id}/aggregate")
def aggregate_features(
    collection_id: str, body: AggregateRequestBody,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    conn_factory=Depends(get_duckdb_connection_factory),
    base_uri: str = Depends(get_analytics_base_uri),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    conn = conn_factory()
    try:
        try:
            category_key, rows = run_collection_aggregate(
                conn, base_uri=base_uri, tenant_id=col.tenant_id, collection_id=col.id,
                table_info=info, request=body,
            )
        except UnknownAggregateField as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_field", "message": exc.message}])
    finally:
        conn.close()
    return {"categoryKey": category_key, "rows": rows}
```

Note : `get_analytics_base_uri` renvoie `s3://<bucket>/cdc` en production — cohérent avec le layout `cdc/tenant_id=.../collection_id=.../dt=.../part-*.parquet` posé par SP-11a (`app/analytics/aggregate.py` construit `f"{base_uri}/tenant_id=.../collection_id=.../dt=*/*.parquet"`, donc `base_uri` doit inclure le préfixe `cdc`).

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/test_features_aggregate_routes.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Exempter l'endpoint du mode démo lecture seule (`core/app/main.py`)**

Ajouter en tête de fichier (après les imports existants) :

```python
import re

_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")
```

Modifier `read_only_guard` :

```python
    @app.middleware("http")
    async def read_only_guard(request: Request, call_next):
        if (
            is_read_only_mode()
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path != "/mcp"
            and not _AGGREGATE_PATH_RE.match(request.url.path)
        ):
            return JSONResponse(
                status_code=403,
                content={"detail": "Mode démo : lecture seule, écritures désactivées."},
            )
        return await call_next(request)
```

- [ ] **Step 6: Test de régression — l'agrégation reste accessible en mode démo**

Ajouter à `core/tests/test_read_only_mode.py` :

```python
def test_read_only_mode_does_not_block_the_aggregate_endpoint(env, monkeypatch):
    """POST /collections/{id}/aggregate est une lecture malgré son verbe HTTP
    (le corps est structuré, pas une liste de query params — cf. spec SP-11b) ;
    le exempter du garde read-only évite de casser tout widget Graphique/
    Indicateur dans une démo publique."""
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.post("/collections/does-not-exist/aggregate", json={"groupBy": "x"})
    assert response.status_code == 404  # jamais 403 : passé le garde, arrêté par get_readable_collection
```

- [ ] **Step 7: Lancer la suite complète, vérifier 0 régression**

```bash
cd core && uv run pytest -v
```

Expected: tous verts (aucun test préexistant cassé), plus les nouveaux tests de ce plan.

- [ ] **Step 8: Commit**

```bash
git add core/app/features/routes.py core/app/main.py core/tests/test_features_aggregate_routes.py core/tests/test_read_only_mode.py
git commit -m "feat(core): SP-11b — endpoint POST /collections/{id}/aggregate, exempté du mode démo"
```

---

### Task 8: Migration shell (`itemClient.ts`) — `queryDataSource` appelle le nouvel endpoint

**Files:**
- Modify: `shell/src/api/itemClient.ts`

**Interfaces:**
- Consumes: `DataSource.query` (forme existante, inchangée : `groupBy`/`split`/`agg`/`field`/`measures` + clés de filtre libres).
- Produces: `queryDataSource` inchangé dans sa signature publique (`(source: DataSource) => Promise<DataRecord[]>`) — seul son implémentation interne pour `type === "statistics"` change.

- [ ] **Step 1: Supprimer `aggregateRecords`/`reduceValues`/`measureLabel`/`STAT_KEYS` et ajouter `buildAggregateBody`**

Dans `shell/src/api/itemClient.ts`, supprimer entièrement les définitions suivantes (lignes ~29-165 selon la version actuelle : `STAT_KEYS`, `type StatMeasure`, `reduceValues`, `measureLabel`, `aggregateRecords`) et les remplacer par :

```typescript
type StatMeasure = { field?: string; agg: string; label?: string };

// Construit le corps JSON de POST /collections/{id}/aggregate depuis
// DataSource.query (SP-11b) — même vocabulaire que l'agrégation client
// supprimée par cette migration (groupBy/split/agg/field/measures), plus
// toute autre clé de query non reconnue traitée comme un filtre attributaire
// (même convention que buildFeaturesUrl pour une source "features").
const STAT_KEYS = new Set(["groupBy", "split", "agg", "field", "measures"]);

function buildAggregateBody(query: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (query.groupBy) body.groupBy = String(query.groupBy);
  if (query.split) body.split = String(query.split);
  if (query.agg) body.agg = String(query.agg);
  if (query.field) body.field = String(query.field);
  if (Array.isArray(query.measures) && query.measures.length) {
    body.measures = (query.measures as StatMeasure[]).map((m) => ({
      field: m.field || undefined, agg: m.agg, label: m.label || undefined,
    }));
  }
  const filters: Record<string, string> = {};
  for (const [k, v] of Object.entries(query)) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      filters[k] = String(v);
    }
  }
  if (Object.keys(filters).length) body.filters = filters;
  return body;
}
```

Placer ce bloc à l'emplacement exact où vivaient `STAT_KEYS`/`aggregateRecords` (juste avant `export function createItemClient`).

- [ ] **Step 2: Modifier `queryDataSource` pour appeler le nouvel endpoint sur `type === "statistics"`**

Remplacer le corps actuel de `queryDataSource` :

```typescript
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      if (source.type === "static") {
        return (source.query.records as DataRecord[] | undefined) ?? [];
      }
      if (source.type === "statistics") {
        const body = buildAggregateBody(source.query);
        const data = await request<{ categoryKey: string; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${source.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: String(row[data.categoryKey] ?? ""), properties: row }));
      }
      const token = getToken();
      const res = await fetch(buildFeaturesUrl(coreUrl, source), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${source.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      return (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
    },
```

Note : `request<T>` (déjà défini plus haut dans ce fichier, utilisé par tout le reste du client) gère déjà l'ajout du header `Authorization`/`Content-Type` et le throw sur réponse non-`ok` — pas besoin de dupliquer cette logique comme le faisait l'ancien chemin `fetch` direct.

- [ ] **Step 3: Vérifier la compilation TypeScript**

```bash
cd shell && npm run build
```

Expected: succès, aucune erreur `tsc` (en particulier : aucune référence résiduelle à `aggregateRecords`/`reduceValues`/`measureLabel` ailleurs dans le fichier).

- [ ] **Step 4: Lancer la suite Vitest**

```bash
cd shell && npm run test
```

Expected: tous verts — `DataContext.test.tsx`/`AppRenderer.test.tsx`/`AppBuilderPage.test.tsx` mockent `queryDataSource` au niveau de l'interface `ItemClient` (pas `aggregateRecords` directement), donc non affectés par ce changement interne.

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts
git commit -m "feat(shell): SP-11b — queryDataSource statistics appelle POST /collections/{id}/aggregate (supprime l'agrégation client)"
```

---

### Task 9: Migration E2E (`mocks.ts`) — mock du nouvel endpoint

**Files:**
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: aucune (fichier de mocks Playwright).

- [ ] **Step 1: Remplacer le mock `**/collections/villes/items*` par un mock `**/collections/villes/aggregate`**

Dans `shell/e2e/mocks.ts`, remplacer :

```typescript
  // Cœur items for the "villes" collection — a statistics source aggregates
  // these client-side (groupBy region, split annee → 2 series).
  await page.route("**/collections/villes/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [
          { id: 1, properties: { region: "Nord", annee: "2025", pop: 10 } },
          { id: 2, properties: { region: "Nord", annee: "2026", pop: 12 } },
          { id: 3, properties: { region: "Sud", annee: "2025", pop: 5 } },
          { id: 4, properties: { region: "Sud", annee: "2026", pop: 7 } },
        ],
      },
    });
  });
```

par :

```typescript
  // POST /collections/villes/aggregate (SP-11b) — le cœur agrège désormais
  // côté serveur (DuckDB) ; le mock renvoie directement la forme large déjà
  // pivotée (groupBy region, split annee → 2 series), même contrat que
  // l'ancienne agrégation client qu'il remplace.
  await page.route("**/collections/villes/aggregate", async (route) => {
    await route.fulfill({
      json: {
        categoryKey: "region",
        rows: [
          { region: "Nord", "2025": 10, "2026": 12 },
          { region: "Sud", "2025": 5, "2026": 7 },
        ],
      },
    });
  });
```

- [ ] **Step 2: Lancer `chart.spec.ts`, vérifier qu'il passe sans modification**

```bash
cd shell && npx playwright test e2e/chart.spec.ts
```

Expected: 1 passed — le mock renvoie déjà la forme pivotée attendue par le test (2 séries), aucun changement nécessaire dans `chart.spec.ts` lui-même (confirme la note de la spec : "pas de nouvelle spec dédiée attendue si la forme de résultat est bien préservée").

- [ ] **Step 3: Lancer la suite E2E complète**

```bash
cd shell && npm run e2e
```

Expected: 37/37 specs vertes (aucune autre spec ne référence `/collections/villes/items` ou l'agrégation statistics).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/mocks.ts
git commit -m "test(shell): SP-11b — mock POST /collections/villes/aggregate (remplace le mock items agrégé client)"
```

---

### Task 10: Script empirique de performance (~1 M lignes, avant/après compaction)

**Files:**
- Create: `core/scripts/measure_aggregate_performance.py`

**Interfaces:**
- Produces: rapport texte (temps mesuré avant/après un cycle de compaction), pas de code produit consommé ailleurs.

- [ ] **Step 1: Écrire le script**

Créer `core/scripts/measure_aggregate_performance.py` :

```python
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
    table_name=COLLECTION_ID, pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
    columns=[ColumnInfo(name="region", type="string", required=True),
             ColumnInfo(name="pop", type="integer", required=True)],
)

REGIONS = ["Nord", "Sud", "Est", "Ouest"]


def _client():
    return boto3.client(
        "s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
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
    key = f"cdc/tenant_id={TENANT_ID}/collection_id={COLLECTION_ID}/dt=2026-07-18/part-{uuid.uuid4().hex}.parquet"
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
        conn, base_uri=f"s3://{BUCKET}/cdc", tenant_id=TENANT_ID, collection_id=COLLECTION_ID,
        table_info=TABLE_INFO, request=AggregateRequestBody(groupBy="region", agg="sum", field="pop"),
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

    print(f"Écriture de {INCREMENTAL_BATCHES} flushes incrémentaux "
          f"({INCREMENTAL_ROWS_PER_BATCH} lignes chacun)...")
    for i in range(INCREMENTAL_BATCHES):
        _write_batch(client, n_rows=INCREMENTAL_ROWS_PER_BATCH,
                    id_start=BACKFILL_ROWS + i * INCREMENTAL_ROWS_PER_BATCH, lsn=i + 2)

    elapsed_before = _measure_aggregate()
    print(f"Agrégation AVANT compaction : {elapsed_before:.3f}s "
          f"({'PASS' if elapsed_before < 2.0 else 'FAIL'}, critère <2s)")

    print("Cycle de compaction...")
    report = run_compaction_cycle(client, bucket=BUCKET)
    print(f"  {report.partitions_scanned} partitions scannées, "
          f"{report.partitions_compacted} compactées, {report.files_removed} fichiers retirés")

    elapsed_after = _measure_aggregate()
    print(f"Agrégation APRÈS compaction : {elapsed_after:.3f}s "
          f"({'PASS' if elapsed_after < 2.0 else 'FAIL'}, critère <2s)")

    return 0 if (elapsed_before < 2.0 and elapsed_after < 2.0) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Exécuter contre la stack réelle**

```bash
docker compose up -d minio
cd core && S3_ENDPOINT_URL=http://127.0.0.1:9000 \
  S3_ACCESS_KEY=${MINIO_USER} S3_SECRET_KEY=${MINIO_PASSWORD} \
  uv run python -m scripts.measure_aggregate_performance
```

Expected: `PASS` avant et après compaction. Si `FAIL` avant compaction seulement (nombreux petits fichiers ralentissent `read_parquet`) : documenter la mesure réelle, elle motive d'autant plus la compaction — ne pas ajuster le seuil de critère, documenter l'écart et le signaler pour investigation (index Parquet, taille de batch incrémental, etc.), cf. §Risques de la spec.

- [ ] **Step 3: Commit**

```bash
git add core/scripts/measure_aggregate_performance.py
git commit -m "test(core): SP-11b — script empirique de performance (~1M lignes, avant/après compaction)"
```

---

### Task 11: Vérification finale — suite complète + critères d'acceptation

**Files:** aucun fichier modifié — validation seule.

- [ ] **Step 1: Suite complète cœur (sans DB)**

```bash
cd core && uv run pytest -v
```

Expected: tous verts, y compris les nouveaux fichiers (`test_cdc_storage.py` étendu, `test_cdc_compaction.py`, `test_jobs.py` étendu, `test_analytics_duckdb_conn.py`, `test_analytics_aggregate.py`, `test_features_aggregate_routes.py`, `test_read_only_mode.py` étendu).

- [ ] **Step 2: `lint-imports`**

```bash
cd core && uv run lint-imports
```

Expected: clean — `app.cdc`/`app.analytics` restent hors du contrat `layered architecture` (non listés), même précédent que SP-11a ; `app.features` (layer listé) important `app.analytics` (non listé) n'est jamais un sens interdit par un contrat "layers" (seules les paires listées sont contraintes).

- [ ] **Step 3: Suite shell**

```bash
cd shell && npm run test && npm run build
```

Expected: tous verts, `tsc` clean.

- [ ] **Step 4: Suite E2E shell**

```bash
cd shell && npm run e2e
```

Expected: 37/37 specs vertes.

- [ ] **Step 5: Vérification empirique bout-en-bout contre la stack assemblée**

```bash
docker compose up -d --build worker core
docker compose logs worker --tail 30
```

Vérifier : le worker ne crash-loop pas avec la nouvelle queue `cdc` ; interroger `POST /collections/{une-collection-existante}/aggregate` via `curl` contre le `core` réel (avec une collection ayant déjà du CDC flushé par `cdc-worker`) et confirmer une réponse 200 avec `categoryKey`/`rows`.

- [ ] **Step 6: Revue des 5 critères d'acceptation de la spec**

1. Compaction réduit le nombre de fichiers sans changer le résultat lu — prouvé par Task 3 (`test_compact_partition_merges_eligible_files_and_removes_originals`, `test_compact_partition_writes_merged_file_before_deleting_originals_on_crash`).
2. ~1 M lignes agrégées en <2s sur un scénario multi-fichiers réaliste — prouvé par Task 10 (script empirique).
3. Collection non autorisée refusée, cohérent avec `GET /items` — prouvé par Task 7 (`test_aggregate_on_unregistered_collection_returns_404`, `test_aggregate_on_private_collection_by_non_owner_returns_404`).
4. `aggregateRecords` supprimé, `queryDataSource` migré, 0 régression E2E — prouvé par Task 8/Task 9.
5. Fraîcheur bornée par le seul SLO CDC existant — aucune nouvelle notion de fraîcheur introduite par ce plan (la compaction ne touche à aucune horloge, `_ts` reste celui du flush CDC d'origine).

- [ ] **Step 7: Rapport final (pas de commit — pour la synthèse humaine/CLAUDE.md)**

Résumer : nombre de tests cœur/shell avant/après, 37/37 E2E, résultat du script de performance (chiffres réels avant/après compaction), toute déviation trouvée en cours d'exécution (incantation bbox retenue par le spike Task 1, écarts éventuels par rapport au code présumé de Task 6/7).

---

## Self-Review

**Spec coverage** : job de compaction (Task 3/4) ; module analytique DuckDB + endpoint (Task 5/6/7) ; migration shell (Task 8/9) ; script de performance avant/après compaction sur scénario multi-fichiers (Task 10) ; les 5 critères d'acceptation tracés explicitement (Task 11) ; les 4 risques de la spec adressés (compatibilité spatial ↔ GeoParquet → spike Task 1 ; CRS non normalisé → hors périmètre, non traité, comme documenté ; croissance non bornée du change-log → hors périmètre, documenté ; connexion DuckDB éphémère → décision de conception #6 des Global Constraints, mesurée par Task 10 ; absence de coordination compaction/écriture → sûreté à l'interruption testée explicitement en Task 3).

**Placeholder scan** : aucun "TBD"/"à compléter" — le seul point explicitement laissé en suspens (l'incantation bbox exacte) est un point que la spec elle-même signale comme risque non vérifié, gated par un spike dont le code produit deux implémentations concrètes testées dans l'ordre, pas un placeholder.

**Type consistency** : `AggregateRequestBody`/`AggregateMeasure` définis une seule fois (Task 6, `app/analytics/aggregate.py`), réutilisés tels quels en Task 7 (import direct, pas de redéfinition) et dans les tests de Task 6/7. `CompactionReport` défini en Task 3, réutilisé identiquement dans le test `run_compaction_cycle` de Task 3 et le script de Task 10. `run_collection_aggregate(conn, *, base_uri, tenant_id, collection_id, table_info, request)` — signature identique entre sa définition (Task 6), son usage dans la route (Task 7) et le script de performance (Task 10).

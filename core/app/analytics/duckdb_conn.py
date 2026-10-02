# SPDX-License-Identifier: Apache-2.0
"""Connexion DuckDB in-process, ÉPHÉMÈRE PAR REQUÊTE (SP-11b) — pas de pool
ni de connexion partagée entre requêtes concurrentes (simplicité d'abord,
le coût de chargement des extensions — dizaines de ms — est négligeable
face au budget de 2s ; cf. spec §Architecture, à revisiter seulement si le
profilage montre un goulot réel). Extensions httpfs (lecture S3/MinIO),
spatial (ST_Intersects sur la colonne géométrie WKB du GeoParquet CDC)
et h3 (fonctions H3, SP-15c, transform.h3Aggregate)
installées une fois sur le disque de l'image lors du build (`core/Dockerfile`,
étape dédiée juste après l'installation des paquets Python — jamais à
l'exécution), chargées à chaque connexion sans accès réseau requis.

Les valeurs SET ci-dessous viennent de variables d'environnement serveur
(pas d'entrée utilisateur) : interpolées directement, comme le reste du
cœur fait déjà confiance à ses propres variables d'environnement (ex.
CORE_BASE_URL dans app/main.py)."""

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb


def open_connection(
    *, endpoint_url: str, access_key: str, secret_key: str
) -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute("INSTALL h3 FROM community; LOAD h3;")
    host = endpoint_url.split("://", 1)[-1]
    use_ssl = endpoint_url.startswith("https://")
    conn.execute(f"SET s3_endpoint = '{host}'")
    conn.execute(f"SET s3_use_ssl = {str(use_ssl).lower()}")
    conn.execute("SET s3_url_style = 'path'")
    conn.execute(f"SET s3_access_key_id = '{access_key}'")
    conn.execute(f"SET s3_secret_access_key = '{secret_key}'")
    # P16.03 : mémoire et débordement disque bornés (valeurs d'environnement
    # serveur, pas d'entrée utilisateur).
    conn.execute(f"SET memory_limit = '{os.environ.get('CORE_DUCKDB_MEMORY_LIMIT') or '2GB'}'")
    conn.execute(
        f"SET max_temp_directory_size = '{os.environ.get('CORE_DUCKDB_MAX_TEMP_SIZE') or '5GB'}'"
    )
    # P25.01 : threads bornés (comme sql_sandbox) pour qu'une requête HTTP
    # ne monopolise pas tous les coeurs.
    conn.execute(f"SET threads = {int(os.environ.get('CORE_DUCKDB_THREADS') or 4)}")
    return conn


def statement_timeout_s() -> float:
    return float(os.environ.get("CORE_DUCKDB_STATEMENT_TIMEOUT_S") or 30)


class StatementTimeout(Exception):
    pass


@contextmanager
def statement_timeout(
    conn: duckdb.DuckDBPyConnection, seconds: float | None = None
) -> Iterator[None]:
    """P25.01 : budget de temps d'une requête servie en HTTP — même mécanisme
    que sql_sandbox (Timer -> conn.interrupt). Lève StatementTimeout."""
    fired = threading.Event()

    def _fire() -> None:
        fired.set()
        conn.interrupt()

    timer = threading.Timer(statement_timeout_s() if seconds is None else seconds, _fire)
    timer.daemon = True
    timer.start()
    try:
        yield
    except duckdb.InterruptException as exc:
        raise StatementTimeout("query exceeded the time limit") from exc
    finally:
        timer.cancel()


def open_spatial_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour la seule conversion GPKG des exports
    (SP-16a) : contrairement à open_connection, ne touche jamais S3 — aucune
    variable d'environnement requise, aucun httpfs/h3 chargé."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn


def open_local_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour le mini-serveur autoporté (SP-18c) :
    lit un instantané GeoParquet local (jamais S3/MinIO) — seule l'extension
    spatial est nécessaire (ST_Intersects/ST_MakeEnvelope/ST_AsGeoJSON/
    ST_GeomFromGeoJSON), aucune configuration s3_* requise."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn

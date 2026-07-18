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

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
import duckdb


def open_connection(*, endpoint_url: str, access_key: str, secret_key: str) -> duckdb.DuckDBPyConnection:
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
    return conn


def open_spatial_connection() -> duckdb.DuckDBPyConnection:
    """Connexion DuckDB in-process pour la seule conversion GPKG des exports
    (SP-16a) : contrairement à open_connection, ne touche jamais S3 — aucune
    variable d'environnement requise, aucun httpfs/h3 chargé."""
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    return conn

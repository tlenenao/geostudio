# postgres:16-bookworm (image officielle, multi-arch amd64+arm64) sert de
# base — postgis/postgis:16-3.4 (Debian 11 bullseye) est mono-arch amd64,
# confirmé sur ce tag et les tags récents (16-3.5, 17-3.5, latest) via
# `docker manifest inspect`. Le dépôt PGDG (déjà configuré dans l'image
# officielle Postgres) sert aussi les paquets Debian
# postgresql-16-postgis-3(-scripts), postgresql-16-pgvector (SP-7) et
# postgresql-16-wal2json (SP-11a, décodage JSON du flux de réplication
# logique — pas de protocole binaire pgoutput à implémenter côté client) —
# tous les quatre publiés en arm64 sur bookworm-pgdg (vérifié).
FROM postgres:16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         postgresql-16-postgis-3 \
         postgresql-16-postgis-3-scripts \
         postgresql-16-pgvector \
         postgresql-16-wal2json \
    && rm -rf /var/lib/apt/lists/*

# L'ancienne base postgis/postgis embarquait /docker-entrypoint-initdb.d/
# 10_postgis.sh, qui exécutait `CREATE EXTENSION postgis` (+topology,
# fuzzystrmatch) contre $POSTGRES_DB au premier démarrage. postgres:16-bookworm
# n'a AUCUN script de ce genre — installer le paquet APT rend l'extension
# seulement DISPONIBLE, il ne la crée jamais dans aucune base. Sans ce script,
# tout `docker run` nu de cette image (CI core/core-qgis/stac-conformance,
# release.yml test-gate + test-gate-arm64, scripts/run-qgis-tests.sh) démarre
# avec un Postgres nu, pas un PostGIS — trouvé en revue finale de branche
# (`CREATE TABLE t (geom geometry(...))` échouait en
# `type "geometry" does not exist`). Seul `postgis` est recréé ici : rien
# dans ce dépôt n'utilise postgis_topology/postgis_tiger_geocoder/
# fuzzystrmatch (vérifié par grep) ; `vector`/`pg_trgm` restent créés par la
# migration Alembic 0012_pgvector_embeddings.py, que tout consommateur réel
# exécute déjà — pas dupliqués ici.
COPY 10_postgis.sh /docker-entrypoint-initdb.d/10_postgis.sh
RUN chmod +x /docker-entrypoint-initdb.d/10_postgis.sh

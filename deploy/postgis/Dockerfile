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

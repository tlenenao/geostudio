# postgis/postgis:16-3.4 ne fournit ni pgvector ni wal2json — le dépôt PGDG
# (déjà configuré dans l'image officielle pour installer les paquets postgis)
# sert aussi les paquets Debian postgresql-16-pgvector (SP-7) et
# postgresql-16-wal2json (SP-11a, décodage JSON du flux de réplication
# logique — pas de protocole binaire pgoutput à implémenter côté client).
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector postgresql-16-wal2json \
    && rm -rf /var/lib/apt/lists/*

# postgis/postgis:16-3.4 ne fournit pas pgvector — le dépôt PGDG (déjà
# configuré dans l'image officielle pour installer les paquets postgis) sert
# aussi le paquet Debian postgresql-16-pgvector (SP-7, recherche sémantique).
FROM postgis/postgis:16-3.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

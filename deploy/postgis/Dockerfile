# postgis/postgis:16-3.4 ne fournit ni pgvector ni wal2json — le dépôt PGDG
# (déjà configuré dans l'image officielle pour installer les paquets postgis)
# sert aussi les paquets Debian postgresql-16-pgvector (SP-7) et
# postgresql-16-wal2json (SP-11a, décodage JSON du flux de réplication
# logique — pas de protocole binaire pgoutput à implémenter côté client).
FROM postgis/postgis:16-3.4

# `-o Acquire::Check-Valid-Until=false` : cette image est basée sur Debian 11
# (bullseye), dont le dépôt bullseye-security sert un InRelease dont le champ
# Valid-Until expire régulièrement sans que le contenu du dépôt ne bouge —
# `apt-get update` échoue alors en "Release file ... is expired" (exit 100),
# panne d'infrastructure externe et non déterministe (observée le 2026-09-12),
# pas un problème de ce Dockerfile. Ce contournement standard désactive
# uniquement la vérification de fraîcheur du métadata, jamais la vérification
# de signature GPG des paquets eux-mêmes.
RUN apt-get update -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector postgresql-16-wal2json \
    && rm -rf /var/lib/apt/lists/*

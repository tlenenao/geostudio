# SPDX-License-Identifier: Apache-2.0
FROM alpine:3.20

# NB: le paquet Alpine `mc` est Midnight Commander (gestionnaire de fichiers
# terminal), pas le client MinIO — découvert en vérifiant Step 11 (lance une
# UI interactive au lieu de configurer un alias). Le client MinIO officiel
# n'est pas empaqueté sous Alpine ; on récupère le binaire statique officiel.
RUN apk add --no-cache postgresql16-client age curl jq bash tzdata python3 \
  && curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc \
  && chmod +x /usr/local/bin/mc

COPY backup.sh /usr/local/bin/backup.sh
COPY retention.py /usr/local/bin/retention.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh

# Cette image est désormais PUBLIÉE sur ghcr.io (SP-21) — c'est un acte de
# distribution du client MinIO `mc`, sous AGPL. La notice voyage donc avec
# l'image, pas seulement dans le dépôt.
COPY LICENSE-BACKUP.md /LICENSE-BACKUP.md
LABEL org.opencontainers.image.licenses="AGPL-3.0-or-later AND Apache-2.0"
LABEL org.opencontainers.image.source="https://github.com/tlenenao/geostudio"
LABEL org.opencontainers.image.description="Image de sauvegarde GeoStudio (pg_dump chiffré age + rétention -> S3/MinIO) — contient le client MinIO mc (AGPL). Voir /LICENSE-BACKUP.md."

RUN addgroup -S backup && adduser -S -G backup -h /home/backup backup

# backup.sh écrit sous /backup/work (répertoire de travail éphémère, purgé
# par le trap EXIT) et /backup/archives (volume nommé `backup-archives` du
# docker-compose.prod.yml — ni $HOME ni /tmp, un troisième cas non couvert
# par la checklist du plan, vérifié empiriquement : un volume nommé fraîchement
# monté hérite de l'utilisateur root si le point de montage n'existe pas déjà
# dans l'image avec le bon propriétaire — sans ce mkdir+chown ici, un
# `touch` non-root dans /backup/archives échoue en Permission denied
# (reproduit avant ce correctif). /home/backup existe déjà avec la bonne
# propriété via `adduser -h`, donc `mc alias set` (config sous $HOME/.mc)
# n'a besoin d'aucun réglage supplémentaire.
RUN mkdir -p /backup/archives /backup/work && chown -R backup:backup /backup
USER backup

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

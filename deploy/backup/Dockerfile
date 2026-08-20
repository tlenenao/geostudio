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

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

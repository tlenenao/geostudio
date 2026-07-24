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

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

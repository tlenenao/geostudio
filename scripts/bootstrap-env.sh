#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env existe déjà — rien à faire. Supprimez-le pour regénérer." >&2
  exit 0
fi

cp .env.example .env

gen() {
  openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 32
  echo
}

for var in PG_PASSWORD MINIO_PASSWORD KC_PASSWORD MARTIN_SECRET; do
  value="$(gen)"
  sed -i.bak "s|^${var}=.*|${var}=${value}|" .env
done
rm -f .env.bak

echo ".env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public."

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

for var in PG_PASSWORD MINIO_PASSWORD KC_PASSWORD; do
  value="$(gen)"
  sed -i.bak "s|^${var}=.*|${var}=${value}|" .env
done

# CORE_SECRETS_MASTER_KEY : contrairement aux 4 secrets ci-dessus (chaînes
# alphanumériques opaques), core/app/secrets/crypto.py::load_master_key()
# exige exactement 32 octets *décodés* depuis du base64 — gen() (tronqué à
# 32 caractères après filtrage de l'alphabet) ne le garantit pas, d'où une
# génération dédiée.
master_key="$(openssl rand -base64 32)"
sed -i.bak "s|^CORE_SECRETS_MASTER_KEY=.*|CORE_SECRETS_MASTER_KEY=${master_key}|" .env

rm -f .env.bak

echo ".env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public."

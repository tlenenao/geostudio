#!/usr/bin/env bash
# Allume, dans .env (non versionné), les capacités nécessaires à la suite
# d'audit : tout sauf le LLM. Idempotent : ne régénère jamais un secret déjà
# défini. Usage : scripts/audit/enable-flags.sh && docker compose up -d
set -euo pipefail
cd "$(dirname "$0")/../.."
[ -f .env ] || { echo "[audit] .env absent : cp .env.example .env d'abord" >&2; exit 1; }

set_kv() { # set_kv CLE VALEUR : remplace ou ajoute
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
set_secret() { # set_secret CLE : génère seulement si vide/absent
  local cur; cur="$(grep "^$1=" .env | head -1 | cut -d= -f2-)"
  [ -n "$cur" ] || set_kv "$1" "$(openssl rand -base64 32)"
}

for f in CORE_ETL_ENABLED CORE_EXPORT_ENABLED CORE_APPEXPORT_ENABLED \
         CORE_TILESET3D_ENABLED CORE_TERRAIN3D_ENABLED \
         CORE_ADMIN_TOOLS_ENABLED CORE_QUOTAS_ENABLED; do set_kv "$f" true; done
set_kv CORE_QUOTA_MAX_ITEMS_PER_TENANT 100000
set_kv CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT 10000
set_secret CORE_EXPORT_TOKEN_SECRET
set_secret CORE_ADMIN_TOOLS_TOKEN_SECRET
set_secret CORE_SHARE_LINK_TOKEN_SECRET
# Grafana : 3001 est refusé par WSL2/Windows sur certains postes.
set_kv GRAFANA_HOST_PORT "${GRAFANA_HOST_PORT:-3011}"
set_kv COMPOSE_PROFILES export,appexport,observability
# Le LLM reste éteint volontairement.
set_kv CORE_LLM_PROVIDER ""
echo "[audit] flags d'audit écrits dans .env (LLM éteint). Lancer : docker compose up -d"

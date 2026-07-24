#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

# Confirmation interactive — jamais d'action destructive/installante sans
# accord explicite (spec SP-Deploy §5.1). INSTALL_YES=1 permet un mode
# non-interactif pour les Steps de vérification de ce plan (jamais utilisé
# pour un vrai déploiement humain).
confirm() {
  if [ "${INSTALL_YES:-0}" = "1" ]; then
    echo "$1 [y/N] → y (INSTALL_YES=1)"
    return 0
  fi
  read -r -p "$1 [y/N] " reply
  case "$reply" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) return 1 ;;
  esac
}

echo "═══ GeoStudio — installeur guidé ═══"

ensure_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "✓ Docker + Docker Compose détectés ($(docker compose version --short))."
    return 0
  fi

  echo "✗ Docker (avec le plugin Compose v2) est requis et n'a pas été détecté."
  case "$(uname -s)" in
    Linux)
      if confirm "Installer Docker via le script officiel et ajouter l'utilisateur au groupe docker ?"; then
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        echo "Docker installé. Déconnectez-vous/reconnectez-vous (ou lancez 'newgrp docker')"
        echo "pour que l'appartenance au groupe docker prenne effet, puis relancez ce script."
        exit 0
      fi
      echo "Installation annulée — relancez ce script une fois Docker installé manuellement."
      exit 1
      ;;
    Darwin)
      echo "macOS : installez Docker Desktop manuellement : https://www.docker.com/products/docker-desktop/"
      echo "Relancez ce script une fois Docker Desktop démarré."
      exit 1
      ;;
    *)
      echo "OS non reconnu automatiquement : installez Docker manuellement"
      echo "(https://docs.docker.com/get-docker/), puis relancez ce script."
      exit 1
      ;;
  esac
}

ensure_docker

declare -A KNOWN_PROFILE_LABELS=(
  [observability]="Observabilité (Grafana/Loki/Tempo/Prometheus)"
  [etl]="ETL no-code (SP-17)"
)

SELECTED_PROFILES=()
SEED_DEMO=false

prompt_profiles() {
  local available
  available="$($COMPOSE config --profiles 2>/dev/null || true)"

  echo ""
  echo "── Profils disponibles ──"
  while IFS= read -r profile; do
    [ -z "$profile" ] && continue
    label="${KNOWN_PROFILE_LABELS[$profile]:-$profile}"
    if confirm "Activer : ${label} ?"; then
      SELECTED_PROFILES+=("$profile")
    fi
  done <<< "$available"

  # ETL (SP-17) : toujours affiché, jamais activable tant qu'absent du
  # dépôt — ne ment pas à l'utilisateur (spec §5.2).
  if ! grep -qx "etl" <<< "$available"; then
    echo "  (ETL no-code (SP-17) — à venir, pas encore disponible dans ce dépôt)"
  fi

  echo ""
  if confirm "Charger des données de démo (collections incidents/points_interet, publiques, éditables) ?"; then
    SEED_DEMO=true
  fi
}

prompt_profiles

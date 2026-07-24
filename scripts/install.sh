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

ensure_jq() {
  if command -v jq >/dev/null 2>&1; then
    echo "✓ jq détecté ($(jq --version))."
    return 0
  fi

  echo "✗ jq (parseur JSON) est requis et n'a pas été détecté."
  case "$(uname -s)" in
    Linux)
      if confirm "Installer jq via le gestionnaire de paquets du système ?"; then
        if command -v apt-get >/dev/null 2>&1; then
          sudo apt-get install -y jq
        elif command -v dnf >/dev/null 2>&1; then
          sudo dnf install -y jq
        elif command -v pacman >/dev/null 2>&1; then
          sudo pacman -S --noconfirm jq
        else
          echo "Gestionnaire de paquets non reconnu automatiquement : installez jq manuellement"
          echo "(https://jqlang.org/download/), puis relancez ce script."
          exit 1
        fi
        echo "jq installé."
        return 0
      fi
      echo "Installation annulée — relancez ce script une fois jq installé manuellement."
      exit 1
      ;;
    Darwin)
      echo "macOS : installez jq manuellement : brew install jq (ou https://jqlang.org/download/)."
      echo "Relancez ce script une fois jq installé."
      exit 1
      ;;
    *)
      echo "OS non reconnu automatiquement : installez jq manuellement"
      echo "(https://jqlang.org/download/), puis relancez ce script."
      exit 1
      ;;
  esac
}

ensure_jq

profile_label() {
  case "$1" in
    observability) echo "Observabilité (Grafana/Loki/Tempo/Prometheus)" ;;
    etl) echo "ETL no-code (SP-17)" ;;
    *) echo "$1" ;;
  esac
}

SELECTED_PROFILES=()
SEED_DEMO=false

prompt_profiles() {
  local available
  local label
  available="$($COMPOSE config --profiles 2>/dev/null || true)"

  echo ""
  echo "── Profils disponibles ──"
  while IFS= read -r profile; do
    [ -z "$profile" ] && continue
    label="$(profile_label "$profile")"
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

ensure_env_file() {
  if [ ! -f .env ]; then
    ./scripts/bootstrap-env.sh
  else
    echo "✓ .env existe déjà — secrets conservés (idempotent)."
  fi
}

set_env_var() {
  # $1 = nom, $2 = valeur — jamais d'écrasement d'une AUTRE variable que
  # celle ciblée (même précaution que bootstrap-env.sh : sed -i.bak, ligne
  # exacte "^NAME=", suffixe .bak supprimé immédiatement après).
  sed -i.bak "s|^${1}=.*|${1}=${2}|" .env
  rm -f .env.bak
}

ensure_env_file

prompt_public_host() {
  echo ""
  read -r -p "Nom d'hôte public (laisser vide pour le découvrir via Tailscale Funnel) : " PUBLIC_HOST_INPUT
  # TS_AUTHKEY déjà exporté dans l'environnement (automatisation, Step 5 de
  # cette tâche) : ne pas redemander — sinon, question interactive.
  if [ -z "${TS_AUTHKEY:-}" ]; then
    read -r -p "Clé Tailscale (TS_AUTHKEY — https://login.tailscale.com/admin/settings/keys) : " TS_AUTHKEY
  fi
  set_env_var TS_AUTHKEY "$TS_AUTHKEY"

  # Le tunnel (service `tunnel`, derrière `traefik`) doit démarrer dans TOUS
  # les cas : l'activation du Funnel (Step suivant) en a besoin, qu'un nom
  # d'hôte ait été saisi manuellement ou découvert automatiquement — seule
  # la BOUCLE DE DÉCOUVERTE ci-dessous est spécifique au cas "pas de nom
  # fourni" (bug de la version initiale du plan : le démarrage du tunnel
  # était sauté dans le cas d'un hôte manuel, alors que l'activation du
  # Funnel juste après en a besoin dans tous les cas).
  echo "Démarrage du tunnel Tailscale..."
  $COMPOSE up -d traefik tunnel

  if [ -n "$PUBLIC_HOST_INPUT" ]; then
    PUBLIC_HOST="$PUBLIC_HOST_INPUT"
    return 0
  fi

  echo "Découverte automatique d'un nom *.ts.net..."
  local dns_name=""
  for _ in $(seq 1 30); do
    dns_name="$($COMPOSE exec -T tunnel tailscale status --json 2>/dev/null \
      | jq -r '.Self.DNSName // empty' | sed 's/\.$//')"
    [ -n "$dns_name" ] && break
    sleep 2
  done
  if [ -z "$dns_name" ]; then
    echo "✗ Impossible de découvrir automatiquement un nom *.ts.net (délai dépassé)." >&2
    echo "  Vérifiez TS_AUTHKEY, ou fournissez un nom d'hôte manuellement et relancez." >&2
    exit 1
  fi
  PUBLIC_HOST="$dns_name"
  echo "✓ Hôte découvert : ${PUBLIC_HOST}"
}

prompt_public_host
set_env_var GEOSTUDIO_PUBLIC_HOST "$PUBLIC_HOST"

activate_funnel() {
  echo "Activation de Tailscale Funnel (accès public sans port ouvert)..."
  $COMPOSE exec -T tunnel tailscale funnel --bg 80
}

prompt_backup_target() {
  echo ""
  read -r -p "Cible de sauvegarde hors-site (endpoint S3-compatible, optionnel — Entrée pour ignorer) : " s3_endpoint
  if [ -n "$s3_endpoint" ]; then
    read -r -p "  Access key : " s3_access
    read -r -p "  Secret key : " s3_secret
    read -r -p "  Bucket [geostudio-backups] : " s3_bucket
    set_env_var BACKUP_S3_ENDPOINT "$s3_endpoint"
    set_env_var BACKUP_S3_ACCESS_KEY "$s3_access"
    set_env_var BACKUP_S3_SECRET_KEY "$s3_secret"
    set_env_var BACKUP_S3_BUCKET "${s3_bucket:-geostudio-backups}"
    echo "  Rappel : générez une paire de clés age (age-keygen) et renseignez la clé"
    echo "  PUBLIQUE dans BACKUP_AGE_RECIPIENT — gardez la clé privée hors de cette machine."
  else
    echo "  Aucune cible hors-site — les sauvegardes resteront locales (avertissement du service backup à chaque exécution)."
  fi
}

activate_funnel
prompt_backup_target

prompt_admin() {
  echo ""
  read -r -p "Email de l'administrateur (créera un compte Keycloak) : " ADMIN_EMAIL

  echo "Démarrage de Keycloak/cœur pour créer le compte admin..."
  $COMPOSE up -d postgis pgbouncer minio keycloak

  # L'image quay.io/keycloak/keycloak ne fournit ni curl ni wget (vérifié
  # empiriquement) — on utilise l'outil d'admin fourni par Keycloak lui-même
  # (kcadm.sh), qui sert aussi de sonde de disponibilité : il échoue tant
  # que Keycloak n'est pas prêt à répondre, donc la boucle ci-dessous fait
  # à la fois l'attente ET l'authentification.
  local kc="/opt/keycloak/bin/kcadm.sh"
  # KC_PASSWORD n'est pas exporté dans l'environnement du script (le script
  # ne fait jamais `source .env` — .env reste une donnée, jamais du code
  # exécuté, même précaution que set_env_var) : on lit la ligne exacte.
  local kc_password
  kc_password="$(grep '^KC_PASSWORD=' .env | cut -d= -f2-)"

  echo "Attente de Keycloak et authentification à l'API Admin..."
  local authenticated=false
  for _ in $(seq 1 30); do
    if $COMPOSE exec -T keycloak "$kc" config credentials \
        --server http://localhost:8080/auth --realm master \
        --user admin --password "$kc_password" --client admin-cli >/dev/null 2>&1; then
      authenticated=true
      break
    fi
    sleep 2
  done
  if [ "$authenticated" != true ]; then
    echo "✗ Échec d'authentification à l'API Admin Keycloak (délai dépassé)." >&2
    exit 1
  fi

  local admin_temp_password
  admin_temp_password="$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)"

  # Idempotent : si l'utilisateur existe déjà (relance de l'installeur),
  # récupérer son id plutôt que d'échouer sur un doublon.
  local existing_id
  existing_id="$($COMPOSE exec -T keycloak "$kc" get users -r geostudio -q "email=${ADMIN_EMAIL}" -q "exact=true" 2>/dev/null \
    | jq -r '.[0].id // empty')"

  if [ -n "$existing_id" ]; then
    echo "✓ Compte admin déjà existant (${ADMIN_EMAIL}) — id réutilisé."
    ADMIN_SUB="$existing_id"
  else
    $COMPOSE exec -T keycloak "$kc" create users -r geostudio \
      -s email="${ADMIN_EMAIL}" -s username="${ADMIN_EMAIL}" -s enabled=true -s emailVerified=true \
      -s "credentials=[{\"type\":\"password\",\"value\":\"${admin_temp_password}\",\"temporary\":true}]" \
      >/dev/null
    ADMIN_SUB="$($COMPOSE exec -T keycloak "$kc" get users -r geostudio -q "email=${ADMIN_EMAIL}" -q "exact=true" 2>/dev/null \
      | jq -r '.[0].id')"
    echo "✓ Compte admin créé : ${ADMIN_EMAIL} / mot de passe temporaire : ${admin_temp_password}"
    echo "  (à changer à la première connexion — non stocké par ce script au-delà de cet affichage)"
  fi

  set_env_var CORE_ADMIN_SUBS "$ADMIN_SUB"
}

prompt_admin

launch_stack() {
  echo ""
  echo "Démarrage complet de la stack..."
  local profile_args=()
  for p in "${SELECTED_PROFILES[@]}"; do
    profile_args+=(--profile "$p")
  done
  $COMPOSE "${profile_args[@]}" up -d

  echo "Attente de la disponibilité du cœur..."
  # Ni curl ni wget ne sont présents dans l'image core (python:3.12-slim +
  # uvicorn — vérifié empiriquement, même écueil que kcadm.sh/Keycloak dans
  # prompt_admin) : on interroge /me avec l'interpréteur Python déjà présent
  # dans le conteneur, qui sert aussi bien à faire la requête qu'à distinguer
  # "erreur HTTP" (code renvoyé) de "pas de connexion encore" (000).
  local code="000"
  for _ in $(seq 1 30); do
    code="$($COMPOSE exec -T core python3 -c '
import urllib.request, urllib.error
try:
    urllib.request.urlopen("http://localhost:8200/me", timeout=2)
    print(200)
except urllib.error.HTTPError as e:
    print(e.code)
except Exception:
    print("000")
' 2>/dev/null || echo 000)"
    [ "$code" = "401" ] && break
    sleep 2
  done
  if [ "$code" != "401" ]; then
    echo "✗ Le cœur ne répond pas comme attendu (code ${code}) — vérifiez 'docker compose logs core'." >&2
    exit 1
  fi
  echo "✓ Cœur opérationnel."

  if [ "$SEED_DEMO" = "true" ]; then
    $COMPOSE exec -T core python -m scripts.seed_demo || true
  fi
}

print_summary() {
  echo ""
  echo "═══ GeoStudio est en ligne ═══"
  echo "URL publique : https://${PUBLIC_HOST}/"
  echo "Admin        : ${ADMIN_EMAIL:-<déjà existant>}"
  echo ""
  echo "Prochaines étapes :"
  echo "  - Se connecter avec le compte admin (mot de passe temporaire affiché ci-dessus, à changer)."
  echo "  - Si une cible de sauvegarde a été configurée : générer une paire de clés"
  echo "    age (age-keygen) et renseigner BACKUP_AGE_RECIPIENT dans .env, puis"
  echo "    redémarrer le service backup ('docker compose ... restart backup')."
  echo "  - Conserver .env et la clé privée age en lieu sûr, hors de cette machine."
}

launch_stack
print_summary


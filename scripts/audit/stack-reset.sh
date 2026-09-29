#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Snapshot / reset de la stack locale entre deux agents d'audit Playwright
# (spec 2026-09-29 §5). Un seul tenant `default` existe : l'isolation entre
# agents passe par la restauration de la base (qui contient aussi Keycloak)
# et des 7 buckets MinIO — même voie que deploy/backup/restore.sh (SP-59).
#
#   scripts/audit/stack-reset.sh snapshot
#   scripts/audit/stack-reset.sh reset [--auth mock|oidc]
set -euo pipefail

cd "$(dirname "$0")/../.."
SNAP="${AUDIT_SNAPSHOT_DIR:-$PWD/.audit-snapshot}"
NET="${AUDIT_COMPOSE_NETWORK:-geostudio_gis-net}"
BUCKETS=(geostudio-thumbnails geostudio-uploads geostudio-cdc geostudio-tileset3d
         geostudio-terrain3d geostudio-mapicons geostudio-attachments)

set -a
# shellcheck disable=SC1091
. ./.env
set +a

mc_run() { # $1 = commande shell exécutée dans minio/mc, dossier snapshot monté sur /snap
  docker run --rm --network "$NET" -v "$SNAP/minio:/snap" \
    -e MINIO_USER="$MINIO_USER" -e MINIO_PASSWORD="$MINIO_PASSWORD" \
    --entrypoint sh minio/mc -c \
    "mc alias set l http://minio:9000 \"\$MINIO_USER\" \"\$MINIO_PASSWORD\" >/dev/null && $1"
}

cmd_snapshot() {
  mkdir -p "$SNAP/minio"
  docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
    pg_dump -h localhost -U gis -Fc gis > "$SNAP/postgres.dump"
  for b in "${BUCKETS[@]}"; do
    mc_run "mc mb --ignore-existing l/$b >/dev/null && mkdir -p /snap/$b && mc mirror --overwrite --remove --quiet l/$b /snap/$b"
  done
  echo "[audit] snapshot écrit dans $SNAP ($(du -sh "$SNAP" | cut -f1))"
}

cmd_reset() {
  local auth="mock" state=none errs
  while [ $# -gt 0 ]; do
    case "$1" in
      --auth) auth="$2"; shift 2 ;;
      *) echo "option inconnue: $1" >&2; exit 2 ;;
    esac
  done
  [ -f "$SNAP/postgres.dump" ] || { echo "aucun snapshot : lancer 'snapshot' d'abord" >&2; exit 1; }

  # cdc-worker arrêté aussi : son slot de réplication logique ne doit pas
  # lire la restauration comme du trafic métier.
  docker compose stop shell core worker cdc-worker keycloak
  # `pg_restore --clean` ne supprime QUE les objets présents dans le dump : une
  # table créée après le snapshot survivrait (constaté par l'auto-test). On
  # repart donc de schémas vides ; les extensions sont recréées par le dump.
  docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
    psql -h localhost -U gis -d gis -v ON_ERROR_STOP=1 -q -c \
    "SET client_min_messages=warning; DROP PUBLICATION IF EXISTS geostudio_cdc; DROP SCHEMA IF EXISTS public, tiger, tiger_data, topology CASCADE; CREATE SCHEMA public;" \
    2>&1 | grep -v -e 'collation version' -e '^DETAIL:' -e '^HINT:' || true
  errs=$(docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis \
    pg_restore -h localhost -U gis -d gis --clean --if-exists --no-owner \
    < "$SNAP/postgres.dump" 2>&1 >/dev/null | grep -c '^pg_restore: error' || true)
  echo "[audit] pg_restore : $errs erreur(s) rapportée(s) (les erreurs d'objets d'extension postgis sont attendues ; le marqueur de l'auto-test fait foi)"
  for b in "${BUCKETS[@]}"; do
    [ -d "$SNAP/minio/$b" ] || continue
    mc_run "mc mb --ignore-existing l/$b >/dev/null && mc mirror --overwrite --remove --quiet /snap/$b l/$b"
  done

  if [ "$auth" = "oidc" ] && [ -f "$SNAP/personas.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$SNAP/personas.env"
    set +a
  fi
  CORE_AUTH_MODE="$auth" VITE_AUTH_MODE="$auth" CORE_ENV=development \
    docker compose up -d keycloak core worker cdc-worker shell

  for svc in core worker shell keycloak; do
    for _ in $(seq 1 60); do
      state=$(docker inspect "$(docker compose ps -q "$svc")" --format '{{.State.Health.Status}}' 2>/dev/null || echo none)
      [ "$state" = "healthy" ] && break
      sleep 3
    done
    [ "$state" = "healthy" ] || { echo "[audit] $svc jamais healthy (état: $state)" >&2; exit 1; }
  done
  echo "[audit] stack restaurée, mode auth=$auth"
}

case "${1:-}" in
  snapshot) cmd_snapshot ;;
  reset) shift; cmd_reset "$@" ;;
  *) echo "usage: $0 snapshot | reset [--auth mock|oidc]" >&2; exit 2 ;;
esac

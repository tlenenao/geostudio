#!/bin/bash
set -euo pipefail

HOUR="$(printf '%02d' "${BACKUP_HOUR:-3}")"
# P27.07 : tentatives bornées par jour, espacées (au lieu d'un dump complet
# toutes les 60 s pendant toute l'heure en échec). Passé le plafond, le jour
# est abandonné ; le healthcheck (fraîcheur de .last_success) passe unhealthy.
MAX_ATTEMPTS="${BACKUP_MAX_ATTEMPTS:-3}"
RETRY_DELAY="${BACKUP_RETRY_DELAY_SECONDS:-900}"
echo "[backup] planifié quotidiennement à ${HOUR}:00 UTC"

run_day() {
  local rc=0 attempt
  for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
    if [ "$rc" = 2 ]; then
      /usr/local/bin/backup.sh --upload-only && return 0 || rc=$?
    else
      /usr/local/bin/backup.sh && return 0 || rc=$?
    fi
    echo "[backup] échec (code ${rc}), tentative ${attempt}/${MAX_ATTEMPTS}" >&2
    [ "$attempt" -lt "$MAX_ATTEMPTS" ] && sleep "$RETRY_DELAY"
  done
  return 1
}

LAST_RUN_DATE=""
while true; do
  now_date="$(date -u +%Y-%m-%d)"
  now_hour="$(date -u +%H)"
  if [ "$now_hour" = "$HOUR" ] && [ "$now_date" != "$LAST_RUN_DATE" ]; then
    run_day || echo "[backup] ERREUR: abandon pour ${now_date} après ${MAX_ATTEMPTS} tentatives" >&2
    LAST_RUN_DATE="$now_date"
  fi
  sleep 60
done

#!/bin/bash
set -euo pipefail

HOUR="$(printf '%02d' "${BACKUP_HOUR:-3}")"
echo "[backup] planifié quotidiennement à ${HOUR}:00 UTC"

LAST_RUN_DATE=""
while true; do
  now_date="$(date -u +%Y-%m-%d)"
  now_hour="$(date -u +%H)"
  if [ "$now_hour" = "$HOUR" ] && [ "$now_date" != "$LAST_RUN_DATE" ]; then
    if /usr/local/bin/backup.sh; then
      LAST_RUN_DATE="$now_date"
    else
      echo "[backup] échec — nouvelle tentative au prochain cycle (60s)" >&2
    fi
  fi
  sleep 60
done

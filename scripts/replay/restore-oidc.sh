#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# REV-164 : rejeu scripté de docs/runbooks/2026-07-24-restauration-sauvegardes.md §7 (OIDC réel, jamais mock).
# DESTRUCTIF : `down -v` détruit les volumes de la stack courante (pg-data, minio-data, keycloak-data…).
# À lancer uniquement sur la stack de rejeu (DOMAIN=localhost), jamais sur une stack à conserver.
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p .replay-results
export RESTORE_ID_FILE="$PWD/.replay-results/restore-item-id"
grep -q '^CORE_AUTH_MODE=oidc' .env || { echo "CORE_AUTH_MODE doit être oidc dans .env" >&2; exit 1; }
grep -q '^DOMAIN=localhost$' .env || { echo "refus : DOMAIN != localhost (stack de rejeu uniquement)" >&2; exit 1; }

BASE=(docker compose)                                   # stack de rejeu (down -v / up)
PROD=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)  # service `backup` (overlay prod seul)
# L'image `backup` est reconstruite depuis deploy/backup (celle de ghcr peut être antérieure à restore.sh).
# GEOSTUDIO_VERSION n'est posé que pour les invocations `backup` : aucune autre image n'est touchée.
BK_IMAGE="ghcr.io/tlenenao/geostudio-backup:replay"
bk() { GEOSTUDIO_VERSION=replay "${PROD[@]}" run --rm --no-deps "$@"; }
wait_healthy() { # wait_healthy <service> [secondes]
  local cid st i
  for ((i = 0; i < ${2:-240}; i += 5)); do
    cid="$("${BASE[@]}" ps -q "$1")"
    st="$([ -n "$cid" ] && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" || true)"
    [ "$st" = healthy ] || [ "$st" = running ] && return 0
    sleep 5
  done
  echo "[restore] $1 jamais healthy (dernier état : ${st:-absent})" >&2; return 1
}

echo "[restore] 1-2 : connexion alice (OIDC réel) + création d'une carte"
( cd shell && RESTORE_PHASE=before npx playwright test -c playwright.oidc.config.ts e2e-oidc/restore-reconnect.spec.ts )

echo "[restore] 3 : backup réel (clé age jetable, envoi hors-site désactivé)"
docker build -q -t "$BK_IMAGE" deploy/backup >/dev/null
KEY="$PWD/.replay-results/age-key.txt"
rm -f "$KEY"
docker run --rm --entrypoint age-keygen "$BK_IMAGE" > "$KEY" 2>/dev/null
RECIPIENT="$(grep '^# public key:' "$KEY" | awk '{print $4}')"
[ -n "$RECIPIENT" ] || { echo "clé age non générée" >&2; exit 1; }
bk -e BACKUP_AGE_RECIPIENT="$RECIPIENT" -e BACKUP_S3_ENDPOINT= -e KEYCLOAK_BASE_URL=http://keycloak:8080 --entrypoint /usr/local/bin/backup.sh backup

echo "[restore] 3b : runbook §1 — déchiffrer la dernière archive vers un répertoire hôte"
RESTORE_ROOT="$PWD/.replay-results/restore-work"
rm -rf "$RESTORE_ROOT"; mkdir -p "$RESTORE_ROOT"
bk --user "$(id -u):$(id -g)" -v "$KEY:/key.txt:ro" -v "$RESTORE_ROOT:/out" --entrypoint sh backup -c '
  set -e
  f="$(ls -1 /backup/archives/*.tar.gz.age | sort | tail -n 1)"
  age -d -i /key.txt -o /tmp/restored.tar.gz "$f"
  tar -xzf /tmp/restored.tar.gz -C /out'
TS="$(ls -1 "$RESTORE_ROOT" | sort | tail -n 1)"
[ -s "$RESTORE_ROOT/$TS/postgres.dump" ] || { echo "archive sans postgres.dump" >&2; exit 1; }

echo "[restore] 4 : destruction complète de la stack (volumes compris)"
"${BASE[@]}" down -v

echo "[restore] 5 : runbook §2-5 — postgis/pgbouncer/minio seuls, restore.sh, puis le reste de la stack"
"${BASE[@]}" up -d postgis pgbouncer minio
wait_healthy postgis; wait_healthy minio
bk -v "$RESTORE_ROOT/$TS:/backup/restore:ro" --entrypoint /usr/local/bin/restore.sh backup "$TS"
"${BASE[@]}" up -d
wait_healthy keycloak 420; wait_healthy core 300; wait_healthy shell 300

echo "[restore] 6-7 : reconnexion OIDC réelle du même compte + carte visible"
( cd shell && RESTORE_PHASE=after npx playwright test -c playwright.oidc.config.ts e2e-oidc/restore-reconnect.spec.ts )
rm -rf "$RESTORE_ROOT" "$KEY"   # clair + clé jetable : jamais conservés
echo "[restore] OK"

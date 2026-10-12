#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ARC-19 : drill de restauration automatisé — sauvegarde -> `down -v` -> restauration -> fumée OIDC.
#
# DESTRUCTIF mais CONFINÉ : tout se passe sous un projet compose dédié (DRILL_PROJECT, défaut
# `arc1-drill`), avec ses propres volumes, son propre réseau, son propre .env généré
# (.replay-results/drill/env). Ne lit ni ne modifie jamais ./.env ni la stack de référence.
# Refuse de démarrer si le projet vaut `geostudio` ou si un port cible est déjà occupé.
#
#   scripts/replay/drill.sh                         # CI (ports 8180/8300/8200/9000)
#   DRILL_PORT_OFFSET=10000 scripts/replay/drill.sh # poste de dev avec une stack déjà levée
#
# Sorties : .replay-results/drill/result.json (+ $GITHUB_STEP_SUMMARY). Code != 0 si une
# vérification échoue (bucket sauvegardé manquant/altéré, realm absent, reconnexion OIDC KO,
# sonde de fraîcheur périmée) ou si DRILL_RTO_MAX_S (optionnel) est dépassé.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROJECT="${DRILL_PROJECT:-arc1-drill}"
OFF="${DRILL_PORT_OFFSET:-0}"
case "$PROJECT" in geostudio | "") echo "refus : projet '$PROJECT' = stack de référence" >&2; exit 2 ;; esac

OUT="$PWD/.replay-results/drill"
mkdir -p "$OUT"
ENVF="$OUT/env"
KC_PORT=$((8180 + OFF)); SHELL_PORT=$((8300 + OFF)); CORE_PORT=$((8200 + OFF))
MINIO_PORT=$((9000 + OFF)); MINIO_CONSOLE_PORT=$((9001 + OFF))
for p in $KC_PORT $SHELL_PORT $CORE_PORT $MINIO_PORT $MINIO_CONSOLE_PORT; do
  if ss -ltn "sport = :$p" | grep -q LISTEN; then
    echo "refus : le port $p est déjà utilisé (utiliser DRILL_PORT_OFFSET)" >&2; exit 2
  fi
done

SHELL_URL="http://localhost:$SHELL_PORT"; CORE_URL="http://localhost:$CORE_PORT"
ISSUER="http://localhost:$KC_PORT/realms/geostudio"
PG_PASSWORD="$(openssl rand -hex 12)"; KC_PASSWORD="$(openssl rand -hex 12)"
MINIO_USER="drill-$(openssl rand -hex 4)"; MINIO_PASSWORD="$(openssl rand -hex 12)"
sed "s#http://localhost:8300#$SHELL_URL#g" deploy/keycloak/geostudio-realm.json > "$OUT/realm.json"
cat > "$ENVF" <<EOF
PG_PASSWORD=$PG_PASSWORD
MINIO_USER=$MINIO_USER
MINIO_PASSWORD=$MINIO_PASSWORD
KC_PASSWORD=$KC_PASSWORD
DOMAIN=localhost
CORE_AUTH_MODE=oidc
CORE_ENV=
CORE_OIDC_ISSUER=$ISSUER
CORE_BASE_URL=$CORE_URL
CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
S3_PUBLIC_ENDPOINT_URL=http://localhost:$MINIO_PORT
VITE_AUTH_MODE=oidc
VITE_CORE_URL=$CORE_URL
CORE_LLM_PROVIDER=fake
DRILL_KC_PORT=$KC_PORT
DRILL_SHELL_PORT=$SHELL_PORT
DRILL_CORE_PORT=$CORE_PORT
DRILL_MINIO_PORT=$MINIO_PORT
DRILL_MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT
DRILL_REALM_FILE=$OUT/realm.json
EOF
DC=(docker compose -p "$PROJECT" --env-file "$ENVF" -f docker-compose.yml -f deploy/drill/docker-compose.drill.yml)
SERVICES=(postgis pgbouncer minio keycloak core shell)
NET="${PROJECT}_gis-net"
ARCHIVES="${PROJECT}-archives"
BK_IMAGE="geostudio-backup:drill"
KEY="$OUT/age-key.txt"; RESTORE_ROOT="$OUT/restore-work"
FAILS=()

cleanup() {
  local rc=$?
  [ "${DRILL_KEEP:-0}" = 1 ] && { echo "[drill] DRILL_KEEP=1 : projet $PROJECT conservé" >&2; return; }
  "${DC[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  docker volume rm "$ARCHIVES" >/dev/null 2>&1 || true
  rm -rf "$KEY" "$RESTORE_ROOT" "$ENVF"   # clé jetable, clair, mots de passe générés : jamais conservés
  return $rc
}
trap cleanup EXIT

wait_healthy() { # wait_healthy <service> [secondes]
  local cid st i
  for ((i = 0; i < ${2:-240}; i += 5)); do
    cid="$("${DC[@]}" ps -q "$1")"
    st="$([ -n "$cid" ] && docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid" || true)"
    if [ "$st" = healthy ] || [ "$st" = running ]; then return 0; fi
    sleep 5
  done
  echo "[drill] $1 jamais healthy (dernier état : ${st:-absent})" >&2; return 1
}
# conteneur one-shot du client MinIO/backup, sur le réseau du projet
bk() { docker run --rm --network "$NET" -e PG_PASSWORD -e MINIO_USER -e MINIO_PASSWORD "$@"; }
export PG_PASSWORD MINIO_USER MINIO_PASSWORD
oidc() { ( cd shell && RESTORE_PHASE="$1" OIDC_SHELL_URL="$SHELL_URL" OIDC_CORE_URL="$CORE_URL" \
  RESTORE_ID_FILE="$OUT/restore-item-id" npx playwright test -c playwright.oidc.config.ts e2e-oidc/restore-reconnect.spec.ts ); }
fail() { echo "[drill] ÉCHEC : $*" >&2; FAILS+=("$*"); }

# Buckets sauvegardés = ceux de la boucle de backup.sh (source unique, pas de copie).
mapfile -t BUCKETS < <(sed -n '/^for bucket in/,/; do/p' deploy/backup/backup.sh | grep -o 'geostudio-[a-z0-9]*')
[ "${#BUCKETS[@]}" -eq 7 ] || { echo "backup.sh : ${#BUCKETS[@]} buckets lus (7 attendus)" >&2; exit 1; }
REGENERABLE=(geostudio-exports geostudio-appexports)   # exclus du backup par décision (BACKUP_EXCLUDED_BUCKETS)

T_START=$SECONDS
echo "[drill] 0 : build + démarrage du projet $PROJECT (ports +$OFF)"
"${DC[@]}" build "${SERVICES[@]:0:1}" minio core shell >/dev/null
"${DC[@]}" up -d "${SERVICES[@]}"
for s in postgis minio; do wait_healthy "$s"; done
wait_healthy keycloak 420; wait_healthy core 300; wait_healthy shell 300
T_UP=$((SECONDS - T_START))

echo "[drill] 1-2 : connexion alice (OIDC réel) + création d'une carte"
oidc before

echo "[drill] 3 : sentinelles dans les ${#BUCKETS[@]} buckets sauvegardés + backup réel (clé age jetable)"
docker build -q -t "$BK_IMAGE" deploy/backup >/dev/null
docker run --rm --entrypoint age-keygen "$BK_IMAGE" > "$KEY" 2>/dev/null
RECIPIENT="$(grep '^# public key:' "$KEY" | awk '{print $4}')"
[ -n "$RECIPIENT" ] || { echo "clé age non générée" >&2; exit 1; }
for b in "${BUCKETS[@]}"; do
  bk --entrypoint /bin/bash "$BK_IMAGE" -c "mc alias set l http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD >/dev/null \
    && mc mb --ignore-existing l/$b >/dev/null && echo 'drill-sentinel-$b' | mc pipe l/$b/_drill-sentinel.txt >/dev/null"
done
docker volume create "$ARCHIVES" >/dev/null
T0=$SECONDS
bk -v "$ARCHIVES:/backup/archives" -e BACKUP_AGE_RECIPIENT="$RECIPIENT" -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD="$KC_PASSWORD" -e KEYCLOAK_BASE_URL=http://keycloak:8080 \
  --entrypoint /usr/local/bin/backup.sh "$BK_IMAGE"
T_BACKUP=$((SECONDS - T0))

# Sonde de fraîcheur (celle du healthcheck prod, fenêtre réduite à 5 min) : prouve que le
# backup n'a touché .last_success qu'après un succès complet.
bk -v "$ARCHIVES:/backup/archives:ro" --entrypoint /bin/bash "$BK_IMAGE" -c \
  'test -n "$(find /backup/archives/.last_success -mmin -5 2>/dev/null)"' || fail "sonde de fraîcheur : .last_success absent ou périmé"

echo "[drill] 3b : déchiffrement de la dernière archive vers un répertoire hôte (runbook §1)"
rm -rf "$RESTORE_ROOT"; mkdir -p "$RESTORE_ROOT"
bk --user "$(id -u):$(id -g)" -v "$ARCHIVES:/backup/archives:ro" -v "$KEY:/key.txt:ro" -v "$RESTORE_ROOT:/out" \
  --entrypoint /bin/bash "$BK_IMAGE" -c '
  set -e
  f="$(ls -1 /backup/archives/*.tar.gz.age | sort | tail -n 1)"
  age -d -i /key.txt -o /tmp/restored.tar.gz "$f"
  tar -xzf /tmp/restored.tar.gz -C /out'
TS="$(ls -1 "$RESTORE_ROOT" | sort | tail -n 1)"
[ -s "$RESTORE_ROOT/$TS/postgres.dump" ] || fail "archive sans postgres.dump"
# jq absent de l'hôte : on l'exécute dans l'image backup (qui l'embarque, backup.sh en dépend).
bk -v "$RESTORE_ROOT/$TS:/r:ro" --entrypoint jq "$BK_IMAGE" -e '.realm == "geostudio"' /r/keycloak-realm.json >/dev/null 2>&1 \
  || fail "archive sans export du realm geostudio"
for b in "${BUCKETS[@]}"; do
  [ -s "$RESTORE_ROOT/$TS/minio/$b/_drill-sentinel.txt" ] || fail "archive : sentinelle absente du bucket $b"
done

echo "[drill] 4 : destruction complète du projet (volumes compris)"
T_DOWN0=$SECONDS
"${DC[@]}" down -v --remove-orphans

echo "[drill] 5 : postgis/pgbouncer/minio seuls, restore.sh, puis le reste de la stack"
T0=$SECONDS
"${DC[@]}" up -d postgis pgbouncer minio
wait_healthy postgis; wait_healthy minio
bk -v "$RESTORE_ROOT/$TS:/backup/restore:ro" --entrypoint /usr/local/bin/restore.sh "$BK_IMAGE" "$TS"
T_RESTORE_SH=$((SECONDS - T0))
"${DC[@]}" up -d "${SERVICES[@]}"
wait_healthy keycloak 420; wait_healthy core 300; wait_healthy shell 300
T_STACK_BACK=$((SECONDS - T_DOWN0))

echo "[drill] 6 : vérifications — buckets, realm"
# Falsification du drill lui-même (DRILL_FALSIFY=1) : retire une sentinelle restaurée, le drill DOIT échouer.
if [ "${DRILL_FALSIFY:-0}" = 1 ]; then
  bk --entrypoint /bin/bash "$BK_IMAGE" -c "mc alias set l http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD >/dev/null && mc rm l/${BUCKETS[0]}/_drill-sentinel.txt >/dev/null"
fi
for b in "${BUCKETS[@]}"; do
  got="$(bk --entrypoint /bin/bash "$BK_IMAGE" -c "mc alias set l http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD >/dev/null && mc cat l/$b/_drill-sentinel.txt" 2>/dev/null || true)"
  [ "$got" = "drill-sentinel-$b" ] || fail "bucket $b : sentinelle absente ou altérée après restauration"
done
curl -sf "http://localhost:$KC_PORT/realms/geostudio/.well-known/openid-configuration" | grep -q "\"issuer\":\"$ISSUER\"" \
  || fail "realm geostudio absent ou issuer inattendu (attendu $ISSUER)"

echo "[drill] 7 : reconnexion OIDC réelle du même compte + carte visible"
oidc after || fail "reconnexion OIDC / carte visible après restauration"
T_RTO=$((SECONDS - T_DOWN0))

cat > "$OUT/result.json" <<EOF
{
  "project": "$PROJECT",
  "archive": "$TS",
  "buckets_verified": ${#BUCKETS[@]},
  "buckets_regenerable_not_backed_up": ${#REGENERABLE[@]},
  "seconds": {
    "initial_up": $T_UP,
    "backup": $T_BACKUP,
    "restore_script": $T_RESTORE_SH,
    "down_to_stack_healthy": $T_STACK_BACK,
    "rto_down_to_oidc_reconnect": $T_RTO,
    "total": $((SECONDS - T_START))
  },
  "failures": $(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${FAILS[@]+"${FAILS[@]}"}"),
  "ok": $([ "${#FAILS[@]}" -eq 0 ] && echo true || echo false)
}
EOF
cat "$OUT/result.json"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  { echo "### Drill de restauration (ARC-19)"; echo; echo '```json'; cat "$OUT/result.json"; echo '```'; } >> "$GITHUB_STEP_SUMMARY"
fi
if [ -n "${DRILL_RTO_MAX_S:-}" ] && [ "$T_RTO" -gt "$DRILL_RTO_MAX_S" ]; then fail "RTO ${T_RTO}s > plafond ${DRILL_RTO_MAX_S}s"; fi
[ "${#FAILS[@]}" -eq 0 ] || exit 1
echo "[drill] OK — RTO mesuré ${T_RTO}s"

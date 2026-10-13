#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ARC-18 / ADR 0019 : HA bornée, documentée ET testée.
#   1. `docker compose up --scale core=2` derrière Traefik passe la fumée (scripts/ci/stack-smoke.sh) ;
#   2. perte brutale (kill) puis arrêt propre (stop) d'un réplica : indisponibilité MESURÉE vue du
#      client (scripts/replay/ha_failover_probe.py) ;
#   3. budget du limiteur MESURÉ avec 2 réplicas (ARC-32 : partagé Postgres => 1 budget, pas 2) ;
#   5. ARC-32 : perte d'un `core` SOUS CHARGE D'ÉCRITURE : bascule < 30 s, 0 écriture acquittée perdue
#      (scripts/replay/ha_write_probe.py, comptage avant/après) ;
#   6. ARC-32 : `cdc-worker` x2 : un seul leader (verrou consultatif), reprise < 30 s à sa perte.
#
# Confiné : projet compose dédié (HA_PROJECT, défaut `arc1-ha`), .env généré, ports décalés de
# HA_PORT_OFFSET, Traefik isolé de la stack de référence (cf. deploy/ha/docker-compose.ha-test.yml).
# Ne lit ni ne modifie ./.env. Sortie : .replay-results/ha/result.json.
set -euo pipefail
cd "$(dirname "$0")/../.."

PROJECT="${HA_PROJECT:-arc1-ha}"
OFF="${HA_PORT_OFFSET:-0}"
case "$PROJECT" in geostudio | "") echo "refus : projet '$PROJECT' = stack de référence" >&2; exit 2 ;; esac
OUT="$PWD/.replay-results/ha"; mkdir -p "$OUT"
HTTP_PORT=$((8081 + OFF)); HTTPS_PORT=$((8443 + OFF)); MINIO_PORT=$((9000 + OFF)); MINIO_CONSOLE_PORT=$((9001 + OFF))
for p in $HTTP_PORT $HTTPS_PORT $MINIO_PORT $MINIO_CONSOLE_PORT; do
  if ss -ltn "sport = :$p" | grep -q LISTEN; then echo "refus : port $p occupé (HA_PORT_OFFSET)" >&2; exit 2; fi
done

ENVF="$OUT/env"
cat > "$ENVF" <<EOF
PG_PASSWORD=$(openssl rand -hex 12)
MINIO_USER=ha-$(openssl rand -hex 4)
MINIO_PASSWORD=$(openssl rand -hex 12)
KC_PASSWORD=$(openssl rand -hex 12)
DOMAIN=localhost
ACME_EMAIL=ha-test@example.org
CORE_AUTH_MODE=mock
CORE_ENV=development
CORE_SECRETS_MASTER_KEY=AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
CORE_ETL_ENABLED=true
CORE_APPEXPORT_ENABLED=true
CORE_SHARE_LINK_TOKEN_SECRET=ha-share-link-secret-0123456789abcdef
CORE_EXPORT_TOKEN_SECRET=ha-export-token-secret-0123456789abcdef
CORE_BASE_URL=https://localhost:$HTTPS_PORT/api
S3_PUBLIC_ENDPOINT_URL=http://localhost:$MINIO_PORT
CORE_LLM_PROVIDER=
HA_PROJECT=$PROJECT
HA_HTTP_PORT=$HTTP_PORT
HA_HTTPS_PORT=$HTTPS_PORT
HA_MINIO_PORT=$MINIO_PORT
HA_MINIO_CONSOLE_PORT=$MINIO_CONSOLE_PORT
EOF

BASE=(docker compose -p "$PROJECT" --env-file "$ENVF" -f docker-compose.yml -f deploy/ha/docker-compose.ha-test.yml)
# Labels des services routés (core, shell) SANS `traefik.enable=true` : sans cela, le Traefik de la
# stack de référence (même docker.sock) importerait nos routeurs homonymes et les fusionnerait avec
# les siens. Généré depuis la config résolue ; `$` ré-échappé en `$$` (regex des middlewares).
python3 - "$OUT/labels.yml" "${BASE[@]}" <<'PY'
import json, subprocess, sys
dest, *base = sys.argv[1:]
cfg = json.loads(subprocess.check_output([*base, "config", "--format", "json"], stderr=subprocess.DEVNULL))
out = "services:\n"
for name in ("core", "shell"):
    out += f"  {name}:\n    labels: !override\n"   # !override : sinon traefik.enable=true du fichier de base survit
    for k, v in cfg["services"][name].get("labels", {}).items():
        if k != "traefik.enable":
            out += f"      - {json.dumps(k + '=' + str(v).replace('$', '$$'))}\n"
open(dest, "w").write(out)
PY
BASE+=(-f "$OUT/labels.yml")
SERVICES=(postgis pgbouncer minio core worker cdc-worker shell traefik)
RES="$OUT/result.json"
FAILS=()
fail() { echo "[ha] ÉCHEC : $*" >&2; FAILS+=("$*"); }

cleanup() {
  local rc=$?
  [ "${HA_KEEP:-0}" = 1 ] && { echo "[ha] HA_KEEP=1 : projet $PROJECT conservé" >&2; return; }
  "${BASE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$ENVF" "$OUT/curlhome" "$OUT/labels.yml"
  return $rc
}
trap cleanup EXIT

wait_healthy() { # wait_healthy <service> <nb attendu> [secondes]
  local i ids n h
  for ((i = 0; i < ${3:-300}; i += 5)); do
    mapfile -t ids < <("${BASE[@]}" ps -q "$1")
    n=0; h=0
    for c in "${ids[@]}"; do
      [ -n "$c" ] || continue
      n=$((n + 1))
      st="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$c")"
      { [ "$st" = healthy ] || [ "$st" = running ]; } && h=$((h + 1))
    done
    [ "$n" -ge "$2" ] && [ "$h" -ge "$2" ] && return 0
    sleep 5
  done
  echo "[ha] $1 : $h/$n sains (attendus $2)" >&2; return 1
}

echo "[ha] 0 : build + démarrage (core x2) — projet $PROJECT"
"${BASE[@]}" build core worker cdc-worker shell postgis minio >/dev/null
T0=$SECONDS
"${BASE[@]}" up -d --scale core=2 --scale cdc-worker=2 "${SERVICES[@]}"
wait_healthy core 2 420; wait_healthy cdc-worker 2 300; wait_healthy shell 1 300; wait_healthy traefik 1 120
T_UP=$((SECONDS - T0))
"${BASE[@]}" --profile appexport run --rm appexport-runtime-builder >/dev/null

mkdir -p "$OUT/curlhome"; echo insecure > "$OUT/curlhome/.curlrc"   # certificat Traefik par défaut, auto-signé
export CURL_HOME="$OUT/curlhome"
CORE_BASE="https://localhost:$HTTPS_PORT"

echo "[ha] 1 : le LB répartit réellement sur les 2 réplicas"
mapfile -t CORES < <("${BASE[@]}" ps -q core)
[ "${#CORES[@]}" -eq 2 ] || fail "${#CORES[@]} réplicas core au lieu de 2"
for i in $(seq 1 40); do curl -sf -o /dev/null "$CORE_BASE/api/health" || true; done
SPREAD=()
for c in "${CORES[@]}"; do SPREAD+=("$(docker logs "$c" 2>&1 | grep -c 'GET /health')"); done
echo "[ha]    requêtes /health vues par réplica (healthcheck compris) : ${SPREAD[*]}"
# les healthchecks docker interrogent aussi /health : on exige que CHAQUE réplica ait reçu >= 15 des 40 requêtes de plus
for s in "${SPREAD[@]}"; do [ "$s" -ge 15 ] || fail "répartition LB : un réplica n'a presque rien reçu (${SPREAD[*]})"; done

echo "[ha] 2 : fumée de bout en bout à travers Traefik (2 réplicas core)"
if CORE_URL="$CORE_BASE/api" SHELL_URL="$CORE_BASE" scripts/ci/stack-smoke.sh; then SMOKE=true; else SMOKE=false; fail "stack-smoke.sh en échec avec 2 réplicas"; fi

echo "[ha] 3 : budget du limiteur (groupe 'sql' = 10/min/appelant ; backend ${CORE_RATELIMIT_BACKEND:-postgres})"
ALLOWED=0; W_BEFORE=$(($(date +%s) / 60))
for i in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Authorization: Bearer ha-limiter-probe' -H 'Content-Type: application/json' -d '{}' "$CORE_BASE/api/v1/analytics/sql")"
  [ "$code" != 429 ] && ALLOWED=$((ALLOWED + 1))
done
W_AFTER=$(($(date +%s) / 60))
echo "[ha]    requêtes non limitées sur 60 envoyées : $ALLOWED (budget configuré : 10 ; mémoire x2 réplicas => ~20)"
# Fenêtre fixe de 60 s : une rafale à cheval sur deux fenêtres peut passer jusqu'à 2x le budget.
if [ "${CORE_RATELIMIT_BACKEND:-postgres}" = postgres ] && [ "$W_BEFORE" = "$W_AFTER" ] && [ "$ALLOWED" -gt 10 ]; then
  fail "limiteur partagé : $ALLOWED requêtes passées dans une même fenêtre, budget 10 attendu"
fi

echo "[ha] 4 : perte d'un réplica — mesure client"
PROBE=(python3 scripts/replay/ha_failover_probe.py --url "$CORE_BASE/api/health" --max-window 5)
set +e
KILL_JSON="$("${PROBE[@]}" --kill-cmd "docker kill ${CORES[0]}")"; KILL_RC=$?
set -e
echo "[ha]    kill : $KILL_JSON"
[ "$KILL_RC" -eq 0 ] || fail "perte brutale (kill) : fenêtre d'erreurs > 5 s, service non rétabli ou erreurs avant la perte"
docker start "${CORES[0]}" >/dev/null; wait_healthy core 2 300
set +e
STOP_JSON="$("${PROBE[@]}" --kill-cmd "docker stop ${CORES[1]}")"; STOP_RC=$?
set -e
echo "[ha]    stop : $STOP_JSON"
[ "$STOP_RC" -eq 0 ] || fail "arrêt propre (stop) : fenêtre d'erreurs > 5 s, service non rétabli ou erreurs avant l'arrêt"
docker start "${CORES[1]}" >/dev/null; wait_healthy core 2 300

echo "[ha] 5 : perte d'un core SOUS CHARGE D'ÉCRITURE — 0 écriture acquittée perdue, bascule < 30 s"
set +e
WRITE_JSON="$(python3 scripts/replay/ha_write_probe.py --base "$CORE_BASE/api" --threads 4 --kill-cmd "docker kill ${CORES[0]}" --max-recovery 30)"; WRITE_RC=$?
set -e
echo "[ha]    écritures : $WRITE_JSON"
[ "$WRITE_RC" -eq 0 ] || fail "écritures sous perte d'un réplica : écriture acquittée perdue, bascule > 30 s ou service non rétabli"
docker start "${CORES[0]}" >/dev/null 2>&1 || true; wait_healthy core 2 300

echo "[ha] 6 : cdc-worker x2 — un seul leader, reprise < 30 s"
CDC_KEY="$(python3 -c 'import hashlib; k=int.from_bytes(hashlib.sha256(b"geostudio.cdc-worker.leader").digest()[:8],"big")>>1; print(k)')"
PSQL=("${BASE[@]}" exec -T postgis psql -U gis -d gis -At)
holders() { "${PSQL[@]}" -c "select coalesce(a.client_addr::text,'') from pg_locks l join pg_stat_activity a using(pid) where l.locktype='advisory' and l.granted and l.classid::bigint=($CDC_KEY>>32) and l.objid::bigint=($CDC_KEY & 4294967295)" | tr -d '\r' | sed '/^$/d'; }
slot_active() { "${PSQL[@]}" -c "select active from pg_replication_slots where slot_name='geostudio_cdc_slot'" 2>/dev/null | tr -d '\r'; }
SLOT_NAME_OK="$("${PSQL[@]}" -c "select count(*) from pg_replication_slots" | tr -d '\r')"
mapfile -t CDCS < <("${BASE[@]}" ps -q cdc-worker)
[ "${#CDCS[@]}" -eq 2 ] || fail "${#CDCS[@]} cdc-worker au lieu de 2"
sleep 5
mapfile -t H < <(holders)
[ "${#H[@]}" -eq 1 ] || fail "élection : ${#H[@]} détenteurs du verrou (1 attendu)"
LEADER=""
for c in "${CDCS[@]}"; do
  ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$c")"
  case " $ip " in *" ${H[0]%%/*} "*) LEADER="$c";; esac
done
[ -n "$LEADER" ] || fail "leader CDC non identifiable (verrou tenu par ${H[0]:-?})"
echo "[ha]    leader = ${LEADER:0:12} ; slot(s) de réplication : $SLOT_NAME_OK"
T_KILL=$(date +%s.%N)
docker kill "$LEADER" >/dev/null
TAKEOVER=""
for _ in $(seq 1 150); do   # 30 s, pas 0,2 s
  mapfile -t H2 < <(holders)
  if [ "${#H2[@]}" -eq 1 ] && [ "${H2[0]}" != "${H[0]}" ] && [ "$(slot_active)" = t ]; then
    TAKEOVER="$(python3 -c "import time;print(round(time.time()-$T_KILL,2))")"; break
  fi
  sleep 0.2
done
if [ -n "$TAKEOVER" ]; then echo "[ha]    reprise par l'autre cdc-worker en ${TAKEOVER}s (verrou + slot actif)"
else fail "cdc-worker : pas de reprise en 30 s après la perte du leader"; fi
docker start "$LEADER" >/dev/null 2>&1 || true

CSP="$(curl -sI "$CORE_BASE/" | tr -d '\r' | grep -ic '^content-security-policy' || true)"
python3 - "$RES" <<PY
import json, sys
json.dump({
  "project": "$PROJECT", "core_replicas": ${#CORES[@]}, "seconds_initial_up": $T_UP,
  "smoke_with_2_replicas": json.loads("$SMOKE"),
  "lb_health_requests_per_replica": "${SPREAD[*]}".split(),
  "limiter": {"group": "sql", "configured_budget_per_min": 10, "allowed_with_2_replicas": $ALLOWED},
  "write_failover": json.loads('''$WRITE_JSON'''),
  "cdc_takeover_s": ${TAKEOVER:-None},
  "failover_kill": json.loads('''$KILL_JSON'''), "failover_stop": json.loads('''$STOP_JSON'''),
  "csp_header_through_traefik": $CSP,
  "failures": json.loads('''$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "${FAILS[@]+"${FAILS[@]}"}")'''),
}, open(sys.argv[1], "w"), indent=2)
PY
cat "$RES"
[ "${#FAILS[@]}" -eq 0 ] || exit 1
echo "[ha] OK"

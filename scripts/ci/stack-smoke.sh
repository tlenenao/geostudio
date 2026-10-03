#!/usr/bin/env bash
# P27 : fumée « stack composée » — ce que ni pytest (SQLite/postgis nu) ni les
# E2E Playwright (cœur mocké) ne voient : le cœur, le worker, MinIO et nginx
# réellement assemblés par docker-compose. Chaque étape correspond à une classe
# de défaut de l'audit 2026-09-29 :
#   RC-1 .defer() hors App procrastinate (import, run de pipeline, export d'app)
#   RC-2 files/variables du worker (le run de pipeline s'exécute dans `worker`)
#   RC-3 MinIO (CORS, secrets HMAC du lien de partage)
#   RC-4 nginx (type MIME du worker MapLibre .mjs)
# Pré-requis : stack up en CORE_AUTH_MODE=mock + CORE_ENV=development, flags
# CORE_ETL_ENABLED/CORE_APPEXPORT_ENABLED allumés, profil appexport démarré.
# Usage : scripts/ci/stack-smoke.sh   (CORE_URL / SHELL_URL / WAIT_S surchargeables)
set -euo pipefail

CORE="${CORE_URL:-http://localhost:8200}/v1"
SHELL_URL="${SHELL_URL:-http://localhost:8300}"
WAIT_S="${WAIT_S:-180}"
AUTH=(-H "Authorization: Bearer smoke")
TAG="smoke-$(date +%s)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

# JSON via python3 (présent partout, jq ne l'est pas) : pj '<expr sur d>' < json
pj() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
step() { echo "[smoke] $*"; }
fail() { echo "[smoke] ÉCHEC: $*" >&2; exit 1; }
api() { # api METHOD PATH [json-body] -> corps ; échoue sur HTTP >= 400
  local m="$1" p="$2" b="${3:-}" out="$WORK/resp" code
  if [ -n "$b" ]; then
    code="$(curl -s -o "$out" -w '%{http_code}' -X "$m" "${AUTH[@]}" -H 'Content-Type: application/json' -d "$b" "$CORE$p")"
  else
    code="$(curl -s -o "$out" -w '%{http_code}' -X "$m" "${AUTH[@]}" "$CORE$p")"
  fi
  [ "$code" -lt 400 ] || fail "$m $p -> HTTP $code : $(head -c 400 "$out")"
  cat "$out"
}
poll() { # poll "<commande renvoyant le statut>" "<état final ok>" libellé
  local t0=$SECONDS s
  while :; do
    s="$(eval "$1")"
    [ "$s" = "$2" ] && return 0
    case "$s" in failed|error) fail "$3 : statut $s ($(cat "$WORK/resp" 2>/dev/null | head -c 400))";; esac
    [ $((SECONDS - t0)) -lt "$WAIT_S" ] || fail "$3 : délai dépassé (dernier statut: $s)"
    sleep 2
  done
}

step "attente du cœur"
t0=$SECONDS
until curl -sf "${CORE_URL:-http://localhost:8200}/health" >/dev/null; do
  [ $((SECONDS - t0)) -lt "$WAIT_S" ] || fail "cœur injoignable"
  sleep 2
done

step "attente du shell"
t0=$SECONDS
until curl -sf "$SHELL_URL/" >/dev/null; do
  [ $((SECONDS - t0)) -lt "$WAIT_S" ] || fail "shell injoignable"
  sleep 2
done

# ── RC-4 : le worker MapLibre doit partir en type JavaScript, jamais octet-stream ──
step "shell : /assets/maplibre-gl-worker.mjs servi en JavaScript"
ctype="$(curl -sI "$SHELL_URL/assets/maplibre-gl-worker.mjs" | tr -d '\r' | awk -F': ' 'tolower($1)=="content-type"{print tolower($2)}')"
case "$ctype" in *javascript*) ;; *) fail "content-type du worker MapLibre = '$ctype'";; esac

# ── RC-1/RC-3 : import GeoJSON réel (presign S3 -> PUT -> job -> worker) ──
step "import GeoJSON"
cat > "$WORK/pts.geojson" <<'J'
{"type":"FeatureCollection","features":[
{"type":"Feature","properties":{"nom":"a","n":1},"geometry":{"type":"Point","coordinates":[2.35,48.85]}},
{"type":"Feature","properties":{"nom":"b","n":2},"geometry":{"type":"Point","coordinates":[4.83,45.76]}},
{"type":"Feature","properties":{"nom":"c","n":3},"geometry":{"type":"Point","coordinates":[-0.57,44.84]}}]}
J
pre="$(api POST /uploads/presign '{"filename":"pts.geojson","contentType":"application/geo+json"}')"
curl -sf -X PUT -H 'Content-Type: application/geo+json' --data-binary @"$WORK/pts.geojson" "$(pj 'd["uploadUrl"]' <<<"$pre")" \
  || fail "PUT présigné vers S3"
KEY="$(pj 'd["key"]' <<<"$pre")"
job="$(api POST /uploads "{\"key\":\"$KEY\",\"filename\":\"pts.geojson\",\"collectionTitle\":\"$TAG\"}")"
JOB_ID="$(pj 'd["jobId"]' <<<"$job")"
poll "api GET /uploads/$JOB_ID | pj 'd[\"status\"]'" "done" "job d'import"
IMPORT="$(api GET "/uploads/$JOB_ID")"
COLL="$(pj 'd["collectionId"]' <<<"$IMPORT")"; MAP_ITEM="$(pj 'd["itemId"]' <<<"$IMPORT")"
[ -n "$COLL" ] && [ "$COLL" != None ] || fail "import sans collectionId : $IMPORT"
n="$(api GET "/collections/$COLL/items?limit=10" | pj 'len(d["features"])')"
[ "$n" = 3 ] || fail "3 entités attendues dans la collection importée, trouvé $n"

# ── RC-3 : lien de partage (secret HMAC configuré) résolu SANS authentification ──
step "lien de partage public"
tok="$(api POST "/items/$MAP_ITEM/share-links" '{"ttlDays":1}' | pj 'd["token"]')"
code="$(curl -s -o /dev/null -w '%{http_code}' "$CORE/share-links/$tok")"
[ "$code" = 200 ] || fail "résolution publique du lien de partage -> HTTP $code"

# ── RC-1/RC-2 : run de pipeline par l'API, exécuté par le worker (file etl) ──
step "run de pipeline"
PIPE_BODY="{\"title\":\"$TAG-pipe\",\"config\":{\"version\":1,\"kind\":\"pipeline\",\"pipeline\":{\"nodes\":[{\"id\":\"r\",\"kind\":\"reader\",\"op\":\"reader.collection\",\"params\":{\"collectionId\":\"$COLL\"}},{\"id\":\"w\",\"kind\":\"writer\",\"op\":\"writer.export\",\"params\":{\"format\":\"csv\",\"key\":\"smoke/$TAG.csv\"}}],\"edges\":[{\"id\":\"r-w\",\"from\":\"r\",\"to\":\"w\"}]}}}"
PIPE="$(api POST /configs "$PIPE_BODY" | pj 'd["itemId"]')"
# reader.collection lit le lac GeoParquet alimenté par le cdc-worker : tant que
# la première matérialisation n'a pas eu lieu, le run échoue « no data yet » —
# on relance (nouveau run) plutôt que de dormir à l'aveugle.
ok=""
for attempt in 1 2 3 4 5 6 7 8; do
  RUN="$(api POST "/pipelines/$PIPE/run" | pj 'd["runId"]')"
  st=""; t0=$SECONDS
  while [ "$st" != succeeded ] && [ "$st" != failed ] && [ $((SECONDS - t0)) -lt "$WAIT_S" ]; do
    sleep 2
    st="$(api GET "/pipelines/$PIPE/runs" | pj "next(r['status'] for r in d if r['id']=='$RUN')")"
  done
  [ "$st" = succeeded ] && { ok=1; break; }
  err="$(api GET "/pipelines/$PIPE/runs" | pj "next(str(r['error']) for r in d if r['id']=='$RUN')")"
  case "$err" in *"no data yet"*) echo "[smoke] lac pas encore matérialisé, nouvel essai ($attempt/8)"; sleep 10;; *) fail "run de pipeline : statut '$st' ($err)";; esac
done
[ -n "$ok" ] || fail "run de pipeline : le lac n'a jamais été matérialisé"

# ── RC-1/RC-3 : export d'app statique (worker, runtime d'export, S3) ──
step "export d'app"
APP_BODY="{\"title\":\"$TAG-app\",\"config\":{\"version\":1,\"kind\":\"app\",\"theme\":{},\"dataSources\":[],\"messages\":[],\"layout\":{\"type\":\"grid\",\"breakpoints\":{},\"items\":[]}}}"
APP="$(api POST /configs "$APP_BODY" | pj 'd["itemId"]')"
EXP="$(api POST /app-exports "{\"itemId\":\"$APP\",\"mode\":\"static\"}" | pj 'd["jobId"]')"
poll "api GET /app-exports/jobs/$EXP | pj 'd[\"status\"]'" "done" "export d'app"
url="$(api GET "/app-exports/jobs/$EXP" | pj 'd["resultUrl"]')"
[ -n "$url" ] && [ "$url" != None ] || fail "export d'app sans resultUrl"

step "OK"

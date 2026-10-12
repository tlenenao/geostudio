#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# ARC-18 : preuve du standby Postgres en streaming sur conteneurs JETABLES (pas la stack GeoStudio) :
#   primaire -> pg_basebackup -R -> standby ; écritures en boucle ; kill -9 du primaire ; promotion.
# Mesure : (a) retard de réplication, (b) lignes perdues (RPO observé) en asynchrone ET avec
# synchronous_commit=remote_apply, (c) durée de promotion (RTO base). Aucune ressource hors
# préfixe `arc1-pgha` n'est touchée.
#   scripts/replay/pg-standby-check.sh [image]   (défaut geostudio-postgis:latest, localement construite)
set -euo pipefail
cd "$(dirname "$0")/../.."
IMG="${1:-geostudio-postgis:latest}"
P=arc1-pgha
NET="$P-net"
PW="$(openssl rand -hex 8)"
cleanup() { docker rm -f "$P-primary" "$P-standby" "$P-seed" >/dev/null 2>&1 || true; docker volume rm "$P-pdata" "$P-sdata" >/dev/null 2>&1 || true; docker network rm "$NET" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup_pair() { docker rm -f "$P-primary" "$P-standby" >/dev/null 2>&1 || true; docker volume rm "$P-pdata" "$P-sdata" >/dev/null 2>&1 || true; docker volume create "$P-pdata" >/dev/null; docker volume create "$P-sdata" >/dev/null; }
cleanup
docker network create "$NET" >/dev/null

setup_pair() {
docker volume create "$P-pdata" >/dev/null; docker volume create "$P-sdata" >/dev/null

psql_p() { docker exec -e PGPASSWORD="$PW" "$P-primary" psql -h localhost -U gis -d gis -At -v ON_ERROR_STOP=1 "$@"; }
psql_s() { docker exec -e PGPASSWORD="$PW" "$P-standby" psql -h localhost -U gis -d gis -At -v ON_ERROR_STOP=1 "$@"; }
wait_pg() { for _ in $(seq 1 60); do docker exec "$1" pg_isready -U gis -h localhost >/dev/null 2>&1 && return 0; sleep 1; done; echo "$1 jamais prêt" >&2; return 1; }

docker run -d --name "$P-primary" --network "$NET" -v "$P-pdata:/var/lib/postgresql/data" \
  -e POSTGRES_USER=gis -e POSTGRES_PASSWORD="$PW" -e POSTGRES_DB=gis "$IMG" \
  -c wal_level=replica -c max_wal_senders=5 -c hot_standby=on >/dev/null
wait_pg "$P-primary"; sleep 3; wait_pg "$P-primary"
psql_p -c "CREATE ROLE replicator REPLICATION LOGIN PASSWORD '$PW'" >/dev/null
docker exec "$P-primary" sh -c "echo 'host replication replicator all scram-sha-256' >> \"\$PGDATA/pg_hba.conf\""
psql_p -c "SELECT pg_reload_conf()" >/dev/null
psql_p -c "CREATE TABLE ha_probe (id bigserial PRIMARY KEY, t timestamptz DEFAULT now())" >/dev/null

# standby : copie de base depuis le primaire (-R écrit standby.signal + primary_conninfo)
docker run --rm --network "$NET" -v "$P-sdata:/var/lib/postgresql/data" -e PGPASSWORD="$PW" --entrypoint sh "$IMG" -c \
  "pg_basebackup -h $P-primary -U replicator -D /var/lib/postgresql/data -R -X stream && chown -R postgres:postgres /var/lib/postgresql/data && chmod 700 /var/lib/postgresql/data" >/dev/null
docker run -d --name "$P-standby" --network "$NET" -v "$P-sdata:/var/lib/postgresql/data" -e POSTGRES_PASSWORD="$PW" "$IMG" >/dev/null
wait_pg "$P-standby"
[ "$(psql_s -c 'SELECT pg_is_in_recovery()')" = t ] || { echo "le standby n'est pas en recovery" >&2; exit 1; }
echo "[pgha] standby en streaming : $(psql_p -c "SELECT state||' / '||sync_state FROM pg_stat_replication")"
}

run_case() { # run_case <label> <sync:on|off>
  local label="$1" mode="$2"
  if [ "$mode" = sync ]; then
    psql_p -c "ALTER SYSTEM SET synchronous_standby_names = '*'" -c "ALTER SYSTEM SET synchronous_commit = 'remote_apply'" -c "SELECT pg_reload_conf()" >/dev/null
  else
    psql_p -c "ALTER SYSTEM SET synchronous_standby_names = ''" -c "ALTER SYSTEM SET synchronous_commit = 'on'" -c "SELECT pg_reload_conf()" >/dev/null
  fi
  psql_p -c "TRUNCATE ha_probe" >/dev/null
  sleep 2
  # écrivain : chaque INSERT est un commit ; les ids acquittés au client sont consignés
  docker exec -e PGPASSWORD="$PW" "$P-primary" sh -c \
    "i=0; while psql -h localhost -U gis -d gis -At -c \"INSERT INTO ha_probe DEFAULT VALUES RETURNING id\" >> /tmp/acked 2>/dev/null; do i=\$((i+1)); done" &
  local wpid=$!
  sleep 5
  local lag; lag="$(psql_p -c "SELECT coalesce(max(extract(epoch FROM replay_lag)),0)::numeric(8,4) FROM pg_stat_replication")"
  docker kill "$P-primary" >/dev/null
  wait "$wpid" 2>/dev/null || true
  local acked; acked="$(docker cp "$P-primary:/tmp/acked" - 2>/dev/null | tar -xO 2>/dev/null | grep -cE '^[0-9]+$' || echo 0)"
  local t0 t1; t0="$(date +%s.%N)"
  docker exec -u postgres "$P-standby" pg_ctl promote -D /var/lib/postgresql/data -w >/dev/null
  t1="$(date +%s.%N)"
  local kept; kept="$(psql_s -c 'SELECT count(*) FROM ha_probe')"
  echo "[pgha] $label : retard de réplication ${lag}s avant la panne ; commits acquittés=$acked ; lignes présentes sur le standby promu=$kept ; perdus=$((acked - kept)) ; promotion=$(python3 -c "print(round($t1-$t0,2))")s"
}

# Le primaire est tué à chaque cas : on reconstruit la paire entre les deux.
for case in "asynchrone (défaut)|async" "synchrone remote_apply|sync"; do
  cleanup_pair
  setup_pair
  run_case "${case%%|*}" "${case##*|}"
done
echo "[pgha] OK"

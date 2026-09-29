#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Prouve que `reset` restaure vraiment l'état du snapshot : on pose un
# marqueur Postgres et un marqueur MinIO APRÈS le snapshot, on reset, et les
# deux doivent avoir disparu. Sans cette preuve, « reset » pourrait n'être
# qu'un redémarrage (l'assertion « les tests passent » ne prouve rien).
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a
# shellcheck disable=SC1091
. ./.env
set +a
NET="${AUDIT_COMPOSE_NETWORK:-geostudio_gis-net}"
B=geostudio-uploads

psql_q() { docker compose exec -T -e PGPASSWORD="$PG_PASSWORD" postgis psql -h localhost -U gis -d gis -tAc "$1" 2>/dev/null; }
mc_q() {
  docker run --rm --network "$NET" -e U="$MINIO_USER" -e P="$MINIO_PASSWORD" --entrypoint sh minio/mc -c \
    "mc alias set l http://minio:9000 \"\$U\" \"\$P\" >/dev/null && $1"
}

scripts/audit/stack-reset.sh snapshot

psql_q "CREATE TABLE audit_reset_marker(x int); INSERT INTO audit_reset_marker VALUES (1);" >/dev/null
mc_q "echo hi | mc pipe l/$B/audit-reset-marker.txt" >/dev/null
[ "$(psql_q "SELECT count(*) FROM audit_reset_marker")" = "1" ] || { echo "FAIL: marqueur PG non posé"; exit 1; }
mc_q "mc stat l/$B/audit-reset-marker.txt" >/dev/null || { echo "FAIL: marqueur MinIO non posé"; exit 1; }

scripts/audit/stack-reset.sh reset --auth mock

[ "$(psql_q "SELECT to_regclass('audit_reset_marker') IS NULL")" = "t" ] \
  || { echo "FAIL: le marqueur Postgres a survécu au reset"; exit 1; }
if mc_q "mc stat l/$B/audit-reset-marker.txt" >/dev/null 2>&1; then
  echo "FAIL: le marqueur MinIO a survécu au reset"; exit 1
fi
[ "$(docker inspect "$(docker compose ps -q worker)" --format '{{.RestartCount}}')" -le 1 ] \
  || echo "AVERTISSEMENT: worker redémarré plusieurs fois après reset (vérifier Task 1)"
echo "OK: reset restaure Postgres et MinIO, stack healthy"

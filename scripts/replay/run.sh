#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Orchestrateur du rejeu sur stack réelle (lot D de la clôture des 38 REV).
# Voir docs/runbooks/2026-10-04-rejeu-stack-reelle.md (checklist + table lettres->preuve).
#
#   scripts/replay/run.sh --list
#   scripts/replay/run.sh <stage> [args]      # un stage à la fois, relançable
#   scripts/replay/run.sh all                 # enchaîne tous les stages automatisables
#
# Les journeys sont exécutés par scripts/audit/run-suite.sh (inchangé).
set -uo pipefail
cd "$(dirname "$0")/../.."

STAGES="preflight up journeys e2e-mock oidc restore-oidc smoke rebuild-images plans measure admin-tools report"

if [ "${1:-}" = "--list" ]; then for s in $STAGES; do echo "$s"; done; exit 0; fi
if [ $# -lt 1 ] || [ "$1" = "--help" ] || [ "$1" = "-h" ]; then
  echo "usage: $0 --list | <stage> [args] | all" >&2
  [ $# -ge 1 ] && exit 0 || exit 2
fi

RES=".replay-results"
if [ -f "$RES/LATEST" ] && [ "$1" != "preflight" ] && [ "$1" != "all" ]; then
  OUT="$(cat "$RES/LATEST")"
else
  OUT="$RES/$(date +%Y%m%d-%H%M%S)"; mkdir -p "$OUT"; echo "$OUT" > "$RES/LATEST"
fi
mkdir -p "$OUT"

record() { echo "STAGE=$1 RC=$2" >> "$OUT/summary.txt"; echo "[replay] $1 -> RC=$2 (log: $OUT/$1.log)"; }
need() { [ -e "$1" ] || { echo "[replay] fichier requis absent : $1" >&2; return 1; }; }

stage_preflight() {
  command -v docker >/dev/null || { echo "docker absent" >&2; return 1; }
  [ -f .env ] || { echo ".env absent : lancer scripts/bootstrap-env.sh" >&2; return 1; }
  uptime
  free -m | sed -n 1,2p
  echo "git: $(git rev-parse HEAD) ($(git status --short | grep -vc '^?? .codegraph') fichiers modifiés)"
}
stage_up() {
  # COMPOSE_PROFILES (export,appexport,observability) est posé dans .env par enable-flags.sh
  scripts/audit/enable-flags.sh && docker compose up -d --build \
    && scripts/audit/seed-personas.sh && scripts/audit/stack-reset.sh snapshot
}
stage_journeys() { scripts/audit/run-suite.sh "$@"; }  # --lane/--verify/--only/--workers
stage_e2e_mock() { ( cd shell && npm run e2e ); }
stage_oidc() { ( cd shell && npm run e2e:oidc ); }
stage_restore_oidc() { need scripts/replay/restore-oidc.sh && scripts/replay/restore-oidc.sh "$@"; }
# stack-smoke.sh exige CORE_AUTH_MODE=mock : à lancer sur une stack remontée en mock (runbook).
stage_smoke() { scripts/ci/stack-smoke.sh; }
stage_rebuild_images() {
  docker compose build titiler otel-lgtm 2>&1 | tail -20 \
    && docker compose up -d titiler otel-lgtm \
    && sleep 20 && docker compose ps titiler otel-lgtm
}
stage_plans() { need scripts/replay/index_plans_pg.py && ( cd core && uv run python ../scripts/replay/index_plans_pg.py ); }
stage_measure() {
  need scripts/replay/measure_pk_sort.py && need scripts/replay/measure_groupby_memory.py \
    && ( cd core && uv run python ../scripts/replay/measure_pk_sort.py \
         && uv run python ../scripts/replay/measure_groupby_memory.py )
}
stage_admin_tools() {
  ( cd shell && AUDIT_AUTH=oidc AUDIT_VERIFY=1 npx playwright test -c playwright.journeys.config.ts e2e/journeys/j09c --workers=1 )
}
stage_report() { need scripts/replay/report.py && python3 scripts/replay/report.py "$OUT"; }

run_stage() { # run_stage <stage> [args]
  local s="$1"; shift
  local fn="stage_${s//-/_}"
  declare -F "$fn" >/dev/null || { echo "stage inconnu : $s" >&2; return 2; }
  "$fn" "$@" > "$OUT/$s.log" 2>&1; local rc=$?
  record "$s" "$rc"; return $rc
}

if [ "$1" = all ]; then
  for s in preflight up; do run_stage "$s" || { echo "[replay] arrêt : $s a échoué" >&2; exit 1; }; done
  run_stage journeys --lane all --verify
  for s in e2e-mock oidc admin-tools plans measure smoke rebuild-images restore-oidc report; do run_stage "$s"; done
  cat "$OUT/summary.txt"; exit 0
fi
run_stage "$@"

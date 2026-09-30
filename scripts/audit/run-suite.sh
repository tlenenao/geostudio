#!/usr/bin/env bash
# Rejoue la suite de parcours d'audit (shell/e2e/journeys) en deux voies sur
# la même stack réelle (oidc, flags d'audit allumés — cf. enable-flags.sh).
#
#   scripts/audit/run-suite.sh [--lane parallel|serial|all] [--verify]
#                              [--workers N] [--only "j01 j05"]
#
#   parallel : dossiers qui ne lisent que ce qu'ils créent (stamp()) ; un seul
#              reset puis N workers Playwright (défaut 3).
#   serial   : dossiers touchant l'état global (rôles, quotas, alertes,
#              arrêt de services, mesures de temps) ; reset oidc AVANT CHAQUE
#              dossier, 1 worker.
#   --verify : AUDIT_VERIFY=1, exécute aussi les tests `bug(...)` (rejeu de la
#              preuve : ils doivent échouer tant que le bug existe ; après
#              correctif, remplacer `bug(` par `test(` et ils doivent passer).
#
# Résultats : .audit-results/<horodatage>/{<dossier>.json,summary.md}
set -uo pipefail
cd "$(dirname "$0")/../.."
LANE=all; VERIFY=""; WORKERS=3; ONLY=""
while [ $# -gt 0 ]; do case "$1" in
  --lane) LANE="$2"; shift 2;;
  --verify) VERIFY=1; shift;;
  --workers) WORKERS="$2"; shift 2;;
  --only) ONLY="$2"; shift 2;;
  *) echo "option inconnue : $1" >&2; exit 2;;
esac; done

PARALLEL="j01 j02 j03 j04 j05 j05b j06 j06b j07 j10 j10b j12 t01 t01b t04"
SERIAL="j08 j08b j09 j09b j11 j13 t02 t03 t03b"
OUT=".audit-results/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"

# Garde : la suite suppose les flags d'audit allumés, sinon des dizaines de
# tests échouent pour une raison d'environnement et non de produit.
preflight() {
  local paths; paths="$(curl -sf localhost:8200/openapi.json)" || { echo "cœur injoignable" >&2; return 1; }
  for p in /v1/pipelines /v1/app-exports /v1/export; do
    echo "$paths" | grep -q "\"$p" || { echo "flag manquant (route $p absente) : lancer enable-flags.sh puis docker compose up -d" >&2; return 1; }
  done
}

run_dir() { # run_dir dossier workers
  local d="$1" w="$2"
  [ -d "shell/e2e/journeys/$d" ] || { echo "$d : dossier absent, ignoré"; return; }
  ( cd shell && AUDIT_AUTH=oidc AUDIT_VERIFY="$VERIFY" PLAYWRIGHT_JSON_OUTPUT_NAME="$OUT/$d.json" \
      npx playwright test -c playwright.journeys.config.ts "e2e/journeys/$d" --workers="$w" --reporter=list,json \
      > "$OUT/$d.log" 2>&1 ); echo "$d : code $?"
}

want() { [ -z "$ONLY" ] && return 0; for x in $ONLY; do [ "$x" = "$1" ] && return 0; done; return 1; }

if [ "$LANE" = parallel ] || [ "$LANE" = all ]; then
  scripts/audit/stack-reset.sh reset --auth oidc >/dev/null 2>&1 || { echo "reset KO" >&2; exit 1; }
  preflight || exit 1
  for d in $PARALLEL; do want "$d" && run_dir "$d" "$WORKERS"; done
fi
if [ "$LANE" = serial ] || [ "$LANE" = all ]; then
  for d in $SERIAL; do want "$d" || continue
    scripts/audit/stack-reset.sh reset --auth oidc >/dev/null 2>&1 || { echo "reset KO avant $d" >&2; exit 1; }
    preflight || exit 1
    run_dir "$d" 1
  done
fi

python3 - "$OUT" "$VERIFY" <<'PY'
import json, glob, os, sys
out, verify = sys.argv[1], sys.argv[2]
rows, tot = [], {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
def walk(s, acc):
    for sp in s.get("specs", []):
        for t in sp["tests"]:
            st = t["status"] if "status" in t else t.get("expectedStatus")
            acc[st] = acc.get(st, 0) + 1
    for x in s.get("suites", []): walk(x, acc)
for f in sorted(glob.glob(f"{out}/*.json")):
    try: d = json.load(open(f))
    except Exception: rows.append((os.path.basename(f)[:-5], "JSON illisible")); continue
    acc = {}
    for s in d["suites"]: walk(s, acc)
    n = os.path.basename(f)[:-5]
    rows.append((n, acc))
    for k, v in acc.items():
        key = {"expected": "passed", "unexpected": "failed"}.get(k, k)
        tot[key] = tot.get(key, 0) + v
mode = "VERIFY (tests bug() exécutés)" if verify else "régression (tests bug() ignorés)"
L = [f"# Suite d'audit — {mode}", "", "| dossier | résultat |", "|---|---|"]
L += [f"| {n} | {a} |" for n, a in rows]
L += ["", f"**Total** : {tot}"]
open(f"{out}/summary.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
PY
echo "résultats : $OUT"

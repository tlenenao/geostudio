#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
#
# Exécute les 5 tests `@pytest.mark.qgis` contre un VRAI sidecar qgis-worker.
#
# Pourquoi ce script existe : ces tests skippent silencieusement dès que
# CORE_TEST_QGIS_WORKER_URL est absent. SP-15d (2026-08-06) les a écrits sans
# jamais les exécuter ; SP-44 (2026-09-05) les a exécutés pour la première
# fois et y a trouvé deux bugs de production réels — mais la recette n'était
# consignée nulle part et devait être redérivée à chaque session.
#
# Contrainte que ce script résout : `app/pipelines/runtime.py` code « /scratch »
# en dur (_QGIS_SCRATCH_ROOT) et le process de test doit écrire dans le MÊME
# répertoire que celui monté par le sidecar. Sur un poste de développement,
# `/scratch` appartient à root et `sudo` n'est pas toujours disponible — d'où
# l'exécution de pytest DANS un conteneur, sur un volume Docker nommé, plutôt
# qu'un bind mount sur l'hôte.
#
# L'uid du conteneur de test (1001) est celui de la production (SP-26 C1), le
# même que `qgis` dans le sidecar : sans cette égalité, les permissions des
# fichiers créés diffèrent silencieusement de la réalité et inventent ou
# masquent des symptômes.
#
# Usage : scripts/run-qgis-tests.sh [args pytest supplémentaires]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NET=qgis-tests-net
VOL=qgis-tests-scratch
WORKER=qgis-tests-worker
PG=qgis-tests-postgres
RUNNER_IMAGE=geostudio-qgis-testrunner:local

cleanup() {
  docker rm -f "$WORKER" "$PG" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  docker volume rm "$VOL" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Images (construites seulement si absentes)"
docker image inspect geostudio-qgis-worker:latest >/dev/null 2>&1 \
  || docker build -t geostudio-qgis-worker:latest "$REPO/deploy/qgis-worker"
docker image inspect geostudio-postgis-ci:latest >/dev/null 2>&1 \
  || docker build -t geostudio-postgis-ci:latest "$REPO/deploy/postgis"
docker image inspect geostudio-core:latest >/dev/null 2>&1 \
  || docker build -t geostudio-core:latest "$REPO/core"

# Le lanceur de tests part de l'image `core` (mêmes uid 1001 et mêmes
# dépendances système que la production) et n'y ajoute que de quoi amorcer
# `uv sync --frozen`, qui installera ensuite l'environnement EXACT du
# uv.lock — l'image de production seule ne suffit pas : son jeu de versions
# a dérivé du lock et fait échouer la collecte (filterwarnings=error).
echo "==> Image du lanceur de tests"
docker build -q -t "$RUNNER_IMAGE" - <<'DOCKERFILE'
FROM geostudio-core:latest
USER root
RUN uv pip install --system pytest
USER app
DOCKERFILE

echo "==> Réseau, volume et services"
cleanup
docker network create "$NET" >/dev/null
docker volume create "$VOL" >/dev/null
docker run -d --rm --name "$WORKER" --network "$NET" \
  -e QT_QPA_PLATFORM=offscreen -v "$VOL:/scratch" \
  geostudio-qgis-worker:latest >/dev/null
docker run -d --rm --name "$PG" --network "$NET" \
  -e POSTGRES_USER=gis -e POSTGRES_PASSWORD=gis -e POSTGRES_DB=gis_test \
  geostudio-postgis-ci:latest \
  -c wal_level=logical -c output_plugin_libraries=wal2json,pgoutput,test_decoding >/dev/null

for _ in $(seq 1 30); do
  docker exec "$PG" pg_isready -U gis >/dev/null 2>&1 && break
  sleep 2
done

echo "==> Exécution des tests qgis"
docker run --rm --network "$NET" -v "$VOL:/scratch" -v "$REPO/core:/src:ro" \
  --entrypoint sh "$RUNNER_IMAGE" -c '
set -e
mkdir -p /tmp/run
cp -r /src/app /src/tests /src/scripts /src/pyproject.toml /src/uv.lock \
      /src/alembic /src/alembic.ini /tmp/run/
cd /tmp/run
export UV_PROJECT_ENVIRONMENT=/tmp/run/.venv UV_CACHE_DIR=/tmp/uvcache
uv sync --frozen --no-progress >/dev/null 2>&1
export CORE_TEST_QGIS_WORKER_URL=http://'"$WORKER"':8000
export CORE_TEST_QGIS_SCRATCH_DIR=/scratch
export CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@'"$PG"':5432/gis_test
export CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
exec uv run --frozen pytest -m qgis '"$*"'
'

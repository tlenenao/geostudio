#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
#
# Scripte les étapes 3 (Postgres) et 4 (MinIO) du runbook
# docs/runbooks/2026-07-24-restauration-sauvegardes.md — l'étape 1
# (récupération+déchiffrement de l'archive offsite) reste une opération
# préalable documentée en commandes (spec SP-59 §3.2) : c'est elle qui
# produit le répertoire monté ici en lecture seule.
#
# Invocation (patron backup.sh, image `backup` déjà publiée) :
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
#     -v "$(pwd)/<horodatage>:/backup/restore:ro" \
#     --entrypoint /usr/local/bin/restore.sh backup <horodatage>
#
# La liste de buckets MinIO ci-dessous DOIT rester identique à celle de
# deploy/backup/backup.sh — un test dédié
# (core/tests/test_deployability.py::test_restore_recreates_every_bucket_backup_mirrors)
# garantit que les deux ne peuvent plus dériver silencieusement l'une de
# l'autre (spec SP-59 §1.2b : 5 buckets recréés ici contre 7 réellement
# sauvegardés, avant ce correctif).
set -eu

TS="$1"
# RESTORE_DIR est surchargeable (tests avec doubles) — la valeur de
# production reste /backup/restore (montage du runbook/de l'invocation
# ci-dessus), inchangée par défaut.
RESTORE_DIR="${RESTORE_DIR:-/backup/restore}"

echo "[restore] ${TS} — début"

# --- Postgres (restaure aussi Keycloak, même base `gis`) ---
PGPASSWORD="$PG_PASSWORD" pg_restore -h postgis -U gis -d gis \
  --clean --if-exists --no-owner "${RESTORE_DIR}/postgres.dump"
echo "[restore] postgres.dump restauré."

# --- MinIO : même liste que deploy/backup/backup.sh, tenue synchronisée
# par test_restore_recreates_every_bucket_backup_mirrors plutôt que
# recopiée à l'œil — c'est exactement la dérive silencieuse trouvée en
# session (spec SP-59 §1.2b) que ce script et son test doivent rendre
# impossible à reproduire. ---
mc alias set local http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" >/dev/null
for bucket in "${S3_THUMBNAILS_BUCKET:-geostudio-thumbnails}" \
              "${S3_UPLOADS_BUCKET:-geostudio-uploads}" \
              "${S3_CDC_BUCKET:-geostudio-cdc}" \
              "${S3_TILESET3D_BUCKET:-geostudio-tileset3d}" \
              "${S3_TERRAIN3D_BUCKET:-geostudio-terrain3d}" \
              "${S3_MAPICONS_BUCKET:-geostudio-mapicons}" \
              "${S3_ATTACHMENTS_BUCKET:-geostudio-attachments}"; do
  mc mb --ignore-existing "local/${bucket}"
  b="${RESTORE_DIR}/minio/${bucket}"
  # Garde contre le glob vide (bug déjà rencontré et documenté par le
  # runbook, §1.2 de la spec) : si l'archive ne contient aucun fichier pour
  # ce bucket (jamais utilisé avant le sinistre), son répertoire est absent
  # — sans cette garde, `mc mirror` recevrait un chemin littéral inexistant
  # et échouerait.
  [ -d "$b" ] || continue
  mc mirror --overwrite --quiet "$b" "local/${bucket}"
done
echo "[restore] buckets MinIO recréés et repeuplés."

echo "[restore] ${TS} — restauration Postgres + MinIO terminée."
echo "[restore] Étapes restantes (manuelles, hors périmètre de ce script) :"
echo "[restore]   1. docker compose ... up -d   (démarrer le reste de la stack)."
echo "[restore]   2. Vérifier la reconnexion OIDC réelle — voir le runbook, section OIDC."

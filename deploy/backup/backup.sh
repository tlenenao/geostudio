#!/bin/bash
set -euo pipefail

DATE="$(date -u +%Y%m%d-%H%M%S)"
WORKDIR="/backup/work/${DATE}"
ARCHIVES_DIR="/backup/archives"
# Purge systématique du répertoire de travail en clair (dump Postgres, export
# Keycloak, miroir MinIO) et de l'archive intermédiaire non chiffrée, quelle
# que soit l'issue du script (succès, échec sous `set -e`, signal) — cf. plan
# §4.1 : le contenu en clair ne doit jamais survivre au-delà de cette
# exécution.
trap 'rm -rf "$WORKDIR" "/tmp/${DATE}.tar.gz"' EXIT
mkdir -p "$WORKDIR" "$ARCHIVES_DIR"

echo "[backup] ${DATE} — début"

# ── 1. Postgres (dump logique, format custom — compressé, portable) ──
PGPASSWORD="$PG_PASSWORD" pg_dump -h postgis -p 5432 -U gis -d gis \
  --format=custom --file="${WORKDIR}/postgres.dump"
echo "[backup] postgres.dump: $(du -h "${WORKDIR}/postgres.dump" | cut -f1)"

# ── 2. MinIO (miroir des 3 buckets applicatifs) ──
mc alias set local http://minio:9000 "$MINIO_USER" "$MINIO_PASSWORD" >/dev/null
mkdir -p "${WORKDIR}/minio"
for bucket in "${S3_THUMBNAILS_BUCKET:-geostudio-thumbnails}" \
              "${S3_UPLOADS_BUCKET:-geostudio-uploads}" \
              "${S3_CDC_BUCKET:-geostudio-cdc}"; do
  if mc ls "local/${bucket}" >/dev/null 2>&1; then
    mc mirror --overwrite --quiet "local/${bucket}" "${WORKDIR}/minio/${bucket}"
  else
    echo "[backup] bucket ${bucket} absent — rien à mirorer (jamais utilisé)"
  fi
done

# ── 3. Keycloak (export du realm — filet de sécurité redondant, cf. §4.1
#    du plan : Keycloak persiste déjà dans `gis`, donc déjà couvert par le
#    pg_dump ci-dessus ; ce JSON est un secours portable/lisible en plus) ──
KC_TOKEN="$(curl -sf -X POST \
  "http://keycloak:8080/auth/realms/master/protocol/openid-connect/token" \
  -d "client_id=admin-cli" -d "username=${KEYCLOAK_ADMIN}" \
  -d "password=${KEYCLOAK_ADMIN_PASSWORD}" -d "grant_type=password" \
  | jq -r .access_token)"
if [ -z "$KC_TOKEN" ] || [ "$KC_TOKEN" = "null" ]; then
  echo "[backup] ERREUR: impossible d'obtenir un token admin Keycloak" >&2
  exit 1
fi
curl -sf -X POST \
  "http://keycloak:8080/auth/admin/realms/geostudio/partial-export?exportClients=true&exportGroupsAndRoles=true" \
  -H "Authorization: Bearer ${KC_TOKEN}" -H "Content-Type: application/json" -d '{}' \
  -o "${WORKDIR}/keycloak-realm.json"
if ! jq -e '.realm == "geostudio"' "${WORKDIR}/keycloak-realm.json" >/dev/null 2>&1; then
  echo "[backup] ERREUR: export du realm Keycloak invalide/vide" >&2
  exit 1
fi

# ── 4. Empaqueter + chiffrer (jamais de clair au-delà de cette étape) ──
tar -czf "/tmp/${DATE}.tar.gz" -C /backup/work "${DATE}"
if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  age -r "$BACKUP_AGE_RECIPIENT" -o "${ARCHIVES_DIR}/${DATE}.tar.gz.age" "/tmp/${DATE}.tar.gz"
else
  echo "[backup] ERREUR: BACKUP_AGE_RECIPIENT non défini — refus de stocker un backup en clair" >&2
  exit 1
fi
echo "[backup] archive chiffrée: ${ARCHIVES_DIR}/${DATE}.tar.gz.age"

# ── 5. Envoi hors-site (optionnel — avertissement clair si absent) ──
if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
  mc alias set offsite "$BACKUP_S3_ENDPOINT" "$BACKUP_S3_ACCESS_KEY" "$BACKUP_S3_SECRET_KEY" >/dev/null
  mc cp --quiet "${ARCHIVES_DIR}/${DATE}.tar.gz.age" "offsite/${BACKUP_S3_BUCKET}/"
  echo "[backup] envoyé vers offsite/${BACKUP_S3_BUCKET}/${DATE}.tar.gz.age"
else
  echo "[backup] AVERTISSEMENT: aucune cible hors-site configurée (BACKUP_S3_ENDPOINT vide)." >&2
  echo "[backup] Les sauvegardes restent UNIQUEMENT sur cette machine — ne protège ni de" >&2
  echo "[backup] l'incendie, ni du vol, ni de la panne disque. Configurer BACKUP_S3_* dès que possible." >&2
fi

# ── 6. Rotation (7 quotidiennes + 4 hebdomadaires, locale ET hors-site) ──
LOCAL_FILES="$(cd "$ARCHIVES_DIR" && ls -1 *.tar.gz.age 2>/dev/null || true)"
TO_DELETE="$(python3 /usr/local/bin/retention.py "$LOCAL_FILES")"
for f in $TO_DELETE; do
  rm -f "${ARCHIVES_DIR}/${f}"
  echo "[backup] rotation: supprimé localement ${f}"
  if [ -n "${BACKUP_S3_ENDPOINT:-}" ]; then
    mc rm --quiet "offsite/${BACKUP_S3_BUCKET}/${f}" 2>/dev/null || true
  fi
done

echo "[backup] ${DATE} — terminé"

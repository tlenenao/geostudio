# SP-Deploy-b — Durabilité (sauvegarde + restauration testée) : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un service `backup` qui sauvegarde quotidiennement Postgres (`pg_dump`), MinIO (`mc mirror`) et le realm Keycloak vers une archive chiffrée expédiée hors-site, avec rotation (7 quotidiennes + 4 hebdomadaires) ; et une procédure de restauration **réellement exécutée** sur des volumes vierges qui prouve qu'une donnée écrite avant le backup est relisible après restauration.

**Architecture:** Un service compose dédié (`deploy/backup/`, petite image Alpine avec `pg_dump`/`mc`/`age`/`curl`/`jq`), sans dépendance au code applicatif du cœur. Une boucle shell (pas de démon cron) déclenche `backup.sh` une fois par jour à une heure configurable. `backup.sh` orchestre : dump Postgres (connexion directe à `postgis`, jamais `pgbouncer` — comme le `cdc-worker`, pour les mêmes raisons de compatibilité avec le mode `transaction` de PgBouncer), miroir des 3 buckets MinIO, export du realm Keycloak via l'API Admin REST (`partial-export`), le tout empaqueté en une seule archive `tar.gz` chiffrée par `age` avant tout envoi hors-site (jamais de clair sur le réseau ni au repos). La politique de rétention (quelle archive garder/supprimer) est isolée dans une fonction pure Python testée indépendamment de Docker — c'est la seule partie de ce sous-plan avec un risque algorithmique réel (arithmétique de dates), le reste étant de l'orchestration shell vérifiée en tournant réellement (même patron que `2026-07-16-sp9-install-secrets.md`).

**Tech Stack:** Alpine 3.20, `postgresql16-client` (dump/restore), `mc` (client MinIO/S3), `age` (chiffrement), `curl`/`jq` (API Admin Keycloak), Python 3 stdlib (rétention, testé via `pytest` autonome — aucune dépendance à `core/pyproject.toml`).

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md` (§4).
- **Chiffrement au repos avant tout envoi hors-site** (spec §4.1) — l'archive `.tar.gz` en clair ne doit jamais toucher le disque au-delà de la durée du `tar`, ni jamais quitter la machine ; seul le `.tar.gz.age` (chiffré) est conservé/expédié.
- **Aucune cible hors-site configurée → avertissement clair, jamais un échec silencieux** (spec §4.1) : si `BACKUP_S3_ENDPOINT` est vide, `backup.sh` continue (sauvegarde locale seule) et écrit un avertissement explicite sur stderr à chaque exécution.
- **Rétention 7 quotidiennes + 4 hebdomadaires** (spec §4.1), appliquée identiquement en local et hors-site.
- **La clé privée `age` ne vit JAMAIS dans le dépôt, l'image, ni un volume Docker** — seule la clé **publique** (`BACKUP_AGE_RECIPIENT`) est en `.env`. Documenté explicitement dans le runbook de restauration (Task 2).
- **Connexion Postgres directe à `postgis:5432`, jamais via `pgbouncer:6432`** — même raison déjà documentée pour `cdc-worker` dans `docker-compose.yml` (PgBouncer en `POOL_MODE: transaction`, incompatible avec des opérations de session longues comme `pg_dump`/`pg_restore`).
- **Pas de nouveau code dans `core/`** — ce sous-plan ne touche que `deploy/backup/`, `docker-compose.prod.yml`, `.env.example`, et un nouveau `docs/runbooks/`.
- **En-tête SPDX** `# SPDX-License-Identifier: Apache-2.0` en première ligne de tout nouveau fichier Python.
- **Commandes de test.** Rétention : `uv run --with pytest pytest deploy/backup/test_retention.py -v` (aucune dépendance à `core/`, script Python autonome). Le reste (dump/restore/mirror/export/rotation en conditions réelles) est vérifié en le faisant tourner réellement contre le compose — pas de suite pytest/Vitest pour l'orchestration shell elle-même.
- **Docs et messages en français** (code/identifiants en anglais), conformément à `CLAUDE.md`.

---

### Task 1 : service `backup` (dump + mirror + export + chiffrement + rotation)

**Files:**
- Create: `deploy/backup/Dockerfile`
- Create: `deploy/backup/entrypoint.sh`
- Create: `deploy/backup/backup.sh`
- Create: `deploy/backup/retention.py`
- Create: `deploy/backup/test_retention.py`
- Modify: `docker-compose.prod.yml` (ajout service `backup`, extension du bloc `volumes:` top-level créé en SP-Deploy-a Task 5)
- Modify: `.env.example` (variables `BACKUP_*`)

**Interfaces:**
- Consumes: `PG_PASSWORD`/`MINIO_USER`/`MINIO_PASSWORD`/`KC_PASSWORD` (déjà dans `.env.example`, inchangés) ; réseau `gis-net` (déjà défini par `docker-compose.yml`).
- Produces: archives `/backup/archives/<horodatage>.tar.gz.age` sur le volume nommé `backup-archives` ; consommé par le runbook de restauration (Task 2).

**Contexte vérifié en lisant le code :**
- `deploy/postgis/Dockerfile` : `FROM postgis/postgis:16-3.4` — Postgres 16, donc `postgresql16-client` (paquet Alpine) pour un `pg_dump`/`pg_restore` de version compatible.
- `docker-compose.yml` service `keycloak` : `KC_DB_URL: jdbc:postgresql://postgis:5432/gis` — Keycloak persiste **dans la même base `gis`** que le reste du cœur. Conséquence importante, à documenter dans le runbook (Task 2) : un `pg_dump`/`pg_restore` complet de `gis` restaure **déjà** l'intégralité des données Keycloak (realms, utilisateurs, clients) — l'export JSON via l'API Admin ci-dessous est un **filet de sécurité redondant, portable et lisible**, pas le mécanisme de restauration principal.
- `core/app/items/storage.py`, `core/app/ingestion/storage.py`, `core/app/cdc/storage.py` créent leurs buckets MinIO paresseusement (`create_bucket`, idempotent) au premier usage — mais ce sont des objets **MinIO**, jamais capturés par un dump Postgres : le service `backup` doit lister/mirorer les buckets existants tels quels, et la restauration (Task 2) devra les recréer explicitement (`mc mb`) avant de les repeupler, sans dépendre du démarrage du cœur pour ça.
- `.env.example` définit déjà `S3_THUMBNAILS_BUCKET`, `S3_UPLOADS_BUCKET`, `S3_CDC_BUCKET` — 3 buckets, noms lus depuis l'environnement (repris tels quels par `backup.sh`, jamais codés en dur).
- `docker-compose.yml` service `keycloak` : `KEYCLOAK_ADMIN: admin`, `KEYCLOAK_ADMIN_PASSWORD: ${KC_PASSWORD}` — identifiants admin déjà disponibles, réutilisés pour l'authentification à l'API Admin REST (`grant_type=password`, `client_id=admin-cli`, réalm `master`).
- Le sous-plan SP-Deploy-a (Task 3) fixe `KC_HTTP_RELATIVE_PATH: /auth` en prod — toutes les URLs Keycloak internes de ce service utilisent donc le préfixe `/auth` (`http://keycloak:8080/auth/realms/...`), cohérent avec le reste de la stack prod.

- [ ] **Step 1: Écrire le test de rétention (rouge)**

Créer `deploy/backup/test_retention.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta

from retention import select_files_to_delete


def _name(dt: datetime) -> str:
    return dt.strftime("%Y%m%d-%H%M%S") + ".tar.gz.age"


def test_daily_window_of_7_is_never_deleted():
    now = datetime(2026, 7, 24, 3, 0, 0)
    names = [_name(now - timedelta(days=i)) for i in range(7)]
    assert select_files_to_delete(names, now) == []


def test_keeps_4_most_recent_distinct_older_weeks_deletes_rest():
    now = datetime(2026, 7, 24, 3, 0, 0)
    # 14, 21, ..., 63 jours en arrière — 8 semaines ISO distinctes, toutes
    # hors de la fenêtre quotidienne de 7 jours.
    names = [_name(now - timedelta(weeks=w)) for w in range(2, 10)]
    deleted = select_files_to_delete(names, now)
    kept = [n for n in names if n not in deleted]
    assert set(kept) == set(names[:4])
    assert set(deleted) == set(names[4:])


def test_ignores_filenames_not_matching_the_naming_pattern():
    now = datetime(2026, 7, 24, 3, 0, 0)
    assert select_files_to_delete(["notes.txt", "backup.tar.gz"], now) == []
```

- [ ] **Step 2: Vérifier que le test échoue**

```bash
cd deploy/backup && uv run --with pytest pytest test_retention.py -v 2>&1 | tail -10
```

Expected: `ModuleNotFoundError: No module named 'retention'`.

- [ ] **Step 3: Écrire `retention.py`**

Créer `deploy/backup/retention.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Sélectionne les archives de sauvegarde à supprimer selon la politique de
rétention (spec SP-Deploy §4.1) : 7 quotidiennes + 4 hebdomadaires. Fonction
pure sur des noms de fichiers (aucun accès disque/réseau) — appelée depuis
`backup.sh` à la fois pour la rotation locale (`/backup/archives`) et
hors-site (sortie de `mc ls`), sur la même politique."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

_NAME_RE = re.compile(r"^(\d{8})-(\d{6})\.tar\.gz\.age$")


def _parse(filename: str) -> datetime | None:
    match = _NAME_RE.match(filename)
    if not match:
        return None
    return datetime.strptime(match.group(1) + match.group(2), "%Y%m%d%H%M%S")


def select_files_to_delete(
    filenames: list[str],
    now: datetime,
    daily_count: int = 7,
    weekly_count: int = 4,
) -> list[str]:
    dated = [(f, _parse(f)) for f in filenames]
    dated = [(f, d) for f, d in dated if d is not None]
    dated.sort(key=lambda pair: pair[1], reverse=True)

    daily_cutoff = now - timedelta(days=daily_count)
    keep: set[str] = set()
    older: list[tuple[str, datetime]] = []
    for filename, d in dated:
        if d >= daily_cutoff:
            keep.add(filename)
        else:
            older.append((filename, d))

    # Une sauvegarde par semaine ISO distincte parmi les plus anciennes, les
    # `weekly_count` semaines les plus récentes (older est trié décroissant
    # -> la première rencontrée pour chaque semaine est la plus récente).
    seen_weeks: dict[tuple[int, int], str] = {}
    for filename, d in older:
        week_key = d.isocalendar()[:2]
        if week_key not in seen_weeks and len(seen_weeks) < weekly_count:
            seen_weeks[week_key] = filename
    keep.update(seen_weeks.values())

    return [f for f in filenames if f not in keep]


def _main() -> None:
    """CLI utilisée par `backup.sh` (Step 6) : `python3 retention.py "$(ls
    ...)"` — une liste de noms de fichiers séparés par des espaces/retours
    à la ligne en argument unique, une suppression suggérée par ligne de
    sortie."""
    import sys

    filenames = sys.argv[1].split() if len(sys.argv) > 1 and sys.argv[1] else []
    for name in select_files_to_delete(filenames, datetime.utcnow()):
        print(name)


if __name__ == "__main__":
    _main()
```

- [ ] **Step 4: Lancer les tests (vert)**

```bash
cd deploy/backup && uv run --with pytest pytest test_retention.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Dockerfile du service backup**

Créer `deploy/backup/Dockerfile` :

```dockerfile
# SPDX-License-Identifier: Apache-2.0
FROM alpine:3.20

RUN apk add --no-cache postgresql16-client mc age curl jq bash tzdata python3

COPY backup.sh /usr/local/bin/backup.sh
COPY retention.py /usr/local/bin/retention.py
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/backup.sh /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
```

- [ ] **Step 6: Script d'orchestration `backup.sh`**

Créer `deploy/backup/backup.sh` :

```bash
#!/bin/bash
set -euo pipefail

DATE="$(date -u +%Y%m%d-%H%M%S)"
WORKDIR="/backup/work/${DATE}"
ARCHIVES_DIR="/backup/archives"
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
  rm -rf "/tmp/${DATE}.tar.gz" "$WORKDIR"
  exit 1
fi
rm -f "/tmp/${DATE}.tar.gz"
rm -rf "$WORKDIR"
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
```

- [ ] **Step 7: Boucle de planification `entrypoint.sh`**

Créer `deploy/backup/entrypoint.sh` :

```bash
#!/bin/bash
set -euo pipefail

HOUR="$(printf '%02d' "${BACKUP_HOUR:-3}")"
echo "[backup] planifié quotidiennement à ${HOUR}:00 UTC"

LAST_RUN_DATE=""
while true; do
  now_date="$(date -u +%Y-%m-%d)"
  now_hour="$(date -u +%H)"
  if [ "$now_hour" = "$HOUR" ] && [ "$now_date" != "$LAST_RUN_DATE" ]; then
    if /usr/local/bin/backup.sh; then
      LAST_RUN_DATE="$now_date"
    else
      echo "[backup] échec — nouvelle tentative au prochain cycle (60s)" >&2
    fi
  fi
  sleep 60
done
```

```bash
chmod +x deploy/backup/backup.sh deploy/backup/entrypoint.sh
```

- [ ] **Step 8: Variables `.env.example`**

Ajouter à la section « Déploiement prod » de `.env.example` (créée en SP-Deploy-a) :

```bash
# ─── Sauvegarde (SP-Deploy-b, service `backup`) ──────────
# Heure UTC (0-23) du backup quotidien.
BACKUP_HOUR=3
# Clé PUBLIQUE age (générée via `age-keygen`) — la clé privée ne doit
# JAMAIS être stockée sur cette machine ni dans ce dépôt (cf. runbook de
# restauration, docs/runbooks/2026-07-24-restauration-sauvegardes.md).
BACKUP_AGE_RECIPIENT=
# Cible hors-site S3-compatible (Cloudflare R2 gratuit ≤10 Go, Backblaze
# B2, Scaleway...). Laisser vide = sauvegarde locale seule (avertissement
# émis à chaque exécution).
BACKUP_S3_ENDPOINT=
BACKUP_S3_ACCESS_KEY=
BACKUP_S3_SECRET_KEY=
BACKUP_S3_BUCKET=geostudio-backups
```

- [ ] **Step 9: Brancher le service dans `docker-compose.prod.yml`**

Modifier le bloc `volumes:` en tête de `docker-compose.prod.yml` (créé en SP-Deploy-a Task 5, contient déjà `tailscale-state:`) — ajouter `backup-archives:` :

```yaml
volumes:
  tailscale-state:
  backup-archives:
```

Ajouter le service (nouveau bloc, à la suite des services existants) :

```yaml
  backup:
    build: ./deploy/backup
    restart: unless-stopped
    environment:
      PG_PASSWORD: ${PG_PASSWORD}
      MINIO_USER: ${MINIO_USER}
      MINIO_PASSWORD: ${MINIO_PASSWORD}
      S3_THUMBNAILS_BUCKET: geostudio-thumbnails
      S3_UPLOADS_BUCKET: geostudio-uploads
      S3_CDC_BUCKET: geostudio-cdc
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: ${KC_PASSWORD}
      BACKUP_HOUR: ${BACKUP_HOUR:-3}
      BACKUP_AGE_RECIPIENT: ${BACKUP_AGE_RECIPIENT:-}
      BACKUP_S3_ENDPOINT: ${BACKUP_S3_ENDPOINT:-}
      BACKUP_S3_ACCESS_KEY: ${BACKUP_S3_ACCESS_KEY:-}
      BACKUP_S3_SECRET_KEY: ${BACKUP_S3_SECRET_KEY:-}
      BACKUP_S3_BUCKET: ${BACKUP_S3_BUCKET:-geostudio-backups}
    volumes:
      - backup-archives:/backup/archives
    networks: [gis-net]
    depends_on:
      postgis:
        condition: service_healthy
      minio:
        condition: service_healthy
      keycloak:
        condition: service_healthy
```

- [ ] **Step 10: Valider la syntaxe**

```bash
./scripts/bootstrap-env.sh
{ echo "GEOSTUDIO_PUBLIC_HOST=test.ts.net"; echo "GEOSTUDIO_VERSION=latest"; echo "TS_AUTHKEY="; \
  echo "BACKUP_AGE_RECIPIENT=age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq"; } >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "compose prod OK"
rm -f .env
```

- [ ] **Step 11: Vérifier réellement une exécution de backup**

```bash
age-keygen -o /tmp/sp-deploy-test-key.txt 2>/tmp/sp-deploy-test-key.pub
RECIPIENT="$(grep 'Public key' /tmp/sp-deploy-test-key.pub | awk '{print $NF}')"
./scripts/bootstrap-env.sh
{ echo "GEOSTUDIO_PUBLIC_HOST=test.ts.net"; echo "GEOSTUDIO_VERSION=latest"; echo "TS_AUTHKEY="; \
  echo "BACKUP_AGE_RECIPIENT=${RECIPIENT}"; } >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgis pgbouncer minio keycloak
sleep 15
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup /usr/local/bin/backup.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint sh backup \
  -c "ls -la /backup/archives/"
```

Expected : un fichier `<horodatage>.tar.gz.age` non vide dans `/backup/archives/` ; logs affichant `postgres.dump: ...`, l'avertissement hors-site (aucun `BACKUP_S3_ENDPOINT` défini dans ce test), pas de trace `ERREUR`.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
rm -f .env /tmp/sp-deploy-test-key.txt /tmp/sp-deploy-test-key.pub
```

(Conserver la clé privée `age` de **test** n'a aucun intérêt — elle est jetée ici. La Task 2 documente où stocker une vraie clé de production.)

- [ ] **Step 12: Commit**

```bash
git add deploy/backup docker-compose.prod.yml .env.example
git commit -m "feat(deploy): service backup — pg_dump + mirror MinIO + export Keycloak, chiffré, rotation 7+4"
```

---

### Task 2 : runbook de restauration — exécuté réellement (critère §7-5)

**Files:**
- Create: `docs/runbooks/2026-07-24-restauration-sauvegardes.md`

**Interfaces:** consomme le service `backup` (Task 1) ; ne modifie aucun code.

**Contexte vérifié en lisant le code :** `docker-compose.yml` keycloak `KC_DB_URL: jdbc:postgresql://postgis:5432/gis` — un `pg_restore` complet de `gis` restaure déjà Keycloak (cf. Task 1). Les buckets MinIO, eux, ne sont **pas** dans ce dump (concept S3, pas Postgres) et doivent être recréés explicitement avant le `mc mirror` de restauration.

- [ ] **Step 1: Écrire le runbook**

Créer `docs/runbooks/2026-07-24-restauration-sauvegardes.md` :

```markdown
# Runbook — restauration d'une sauvegarde GeoStudio

Procédure de reprise sur perte totale (machine détruite/volée/disque mort).
À exécuter sur une machine neuve (ou des volumes Docker vierges).

## Prérequis

- La clé **privée** `age` correspondant à `BACKUP_AGE_RECIPIENT` — stockée
  **hors de la machine de production** (gestionnaire de mots de passe,
  copie papier). Sans elle, les archives sont irrécupérables : c'est
  volontaire (chiffrement au repos, spec SP-Deploy §4.1).
- Accès à la cible hors-site (`BACKUP_S3_ENDPOINT`/`BACKUP_S3_BUCKET`) ou,
  à défaut, une copie locale d'une archive `.tar.gz.age`.
- Ce dépôt cloné, `.env` reconstruit (`./scripts/bootstrap-env.sh` puis
  compléter les secrets — de nouveaux secrets `PG_PASSWORD`/`MINIO_PASSWORD`
  sont acceptables : ils ne doivent PAS matcher ceux d'avant la perte, la
  restauration réinjecte les données, pas les identifiants d'infra).

## 1. Récupérer et déchiffrer la dernière archive

```bash
mc alias set offsite "$BACKUP_S3_ENDPOINT" "$BACKUP_S3_ACCESS_KEY" "$BACKUP_S3_SECRET_KEY"
mc ls offsite/$BACKUP_S3_BUCKET/ | tail -5   # repérer le plus récent .tar.gz.age
mc cp offsite/$BACKUP_S3_BUCKET/<horodatage>.tar.gz.age .
age -d -i /chemin/vers/age-private-key.txt -o restored.tar.gz <horodatage>.tar.gz.age
tar -xzf restored.tar.gz
# Produit un répertoire <horodatage>/ avec postgres.dump, minio/, keycloak-realm.json
```

## 2. Démarrer uniquement la base de données

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgis pgbouncer minio
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps postgis minio
# attendre "healthy" avant de continuer
```

## 3. Restaurer Postgres (restaure aussi Keycloak — même base `gis`)

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v "$(pwd)/<horodatage>:/backup/restore:ro" --no-deps backup \
  sh -c "PGPASSWORD=\$PG_PASSWORD pg_restore -h postgis -U gis -d gis --clean --if-exists --no-owner /backup/restore/postgres.dump"
```

**Note :** Keycloak stocke ses realms/utilisateurs dans la même base `gis`
(`KC_DB_URL: jdbc:postgresql://postgis:5432/gis`, `docker-compose.yml`) —
cette seule commande restaure donc **déjà** tous les comptes utilisateurs.
L'export `keycloak-realm.json` de l'archive est un filet redondant (portable,
lisible), pas requis pour cette étape.

## 4. Recréer les buckets MinIO et les repeupler

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps backup sh -c "
  mc alias set local http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD
  mc mb --ignore-existing local/geostudio-thumbnails local/geostudio-uploads local/geostudio-cdc
"
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v "$(pwd)/<horodatage>/minio:/backup/restore-minio:ro" --no-deps backup sh -c "
  mc alias set local http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD
  for b in /backup/restore-minio/*/; do
    mc mirror --overwrite \"\$b\" \"local/\$(basename \$b)\"
  done
"
```

## 5. Démarrer le reste de la stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Keycloak redémarre avec `--import-realm` : le realm `geostudio` existe déjà
(restauré à l'étape 3) — à confirmer empiriquement lors de l'exécution
réelle de ce runbook (Task 2, Step 2) que l'import n'écrase ni ne duplique
rien. `core` applique `alembic upgrade head` sur une base déjà à jour
(restaurée à la bonne révision) — no-op attendu.

## 6. Vérifier

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://$GEOSTUDIO_PUBLIC_HOST/api/me
```

Se connecter via le shell, confirmer qu'un utilisateur restauré peut se
reconnecter et qu'une donnée écrite avant le sinistre est relisible.
```

- [ ] **Step 2: Exécuter réellement la procédure (critère §7-5)**

Sur l'environnement de vérification (volumes jetables, jamais la prod) :

```bash
# Préparer une donnée connue AVANT le backup
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# ... créer un item de test via le shell/l'API (ex. un item nommé
# "sp-deploy-restore-check"), noter son identifiant.

age-keygen -o /tmp/restore-test-key.txt 2>/tmp/restore-test-key.pub
RECIPIENT="$(grep 'Public key' /tmp/restore-test-key.pub | awk '{print $NF}')"
# (ajuster BACKUP_AGE_RECIPIENT dans .env à $RECIPIENT, redémarrer `backup`)
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm backup /usr/local/bin/backup.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint sh backup \
  -c "cp /backup/archives/*.tar.gz.age /backup/archives/latest-for-test.tar.gz.age"
docker cp "$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -q backup):/backup/archives/latest-for-test.tar.gz.age" /tmp/

# Détruire TOUT (simulateur de perte totale)
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v

age -d -i /tmp/restore-test-key.txt -o /tmp/restored.tar.gz /tmp/latest-for-test.tar.gz.age
mkdir -p /tmp/restore-workdir && tar -xzf /tmp/restored.tar.gz -C /tmp/restore-workdir

# Suivre les étapes 2-5 du runbook ci-dessus avec /tmp/restore-workdir/<horodatage> comme chemin source.

# Vérifier :
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec core \
  curl -s -H 'Authorization: Bearer x' http://localhost:8200/items/<identifiant-noté>
```

Expected : l'item `sp-deploy-restore-check` créé avant le backup est présent
dans la réponse — preuve du cycle complet écriture → backup → destruction →
restauration → relecture (critère §7-5).

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
rm -rf /tmp/restore-workdir /tmp/restored.tar.gz /tmp/latest-for-test.tar.gz.age /tmp/restore-test-key.*
```

- [ ] **Step 3: Commit**

```bash
git add docs/runbooks/2026-07-24-restauration-sauvegardes.md
git commit -m "docs(deploy): runbook de restauration — exécuté et vérifié (critère §7-5)"
```

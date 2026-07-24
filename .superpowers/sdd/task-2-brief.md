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

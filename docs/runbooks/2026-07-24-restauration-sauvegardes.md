# Runbook — restauration d'une sauvegarde GeoStudio

Procédure de reprise sur perte totale (machine détruite/volée/disque mort).
À exécuter sur une machine neuve (ou des volumes Docker vierges).

## Prérequis

- La clé **privée** `age` correspondant à `BACKUP_AGE_RECIPIENT`. Elle ne
  vit **jamais** dans le dépôt git, dans l'image `backup` (ni aucune autre
  image), ni dans un volume Docker — seule la clé **publique**
  (`BACKUP_AGE_RECIPIENT`) a sa place en `.env`. La clé privée est stockée
  **hors de la machine de production**, exclusivement chez l'opérateur
  (gestionnaire de mots de passe, copie papier, ou tout autre stockage
  personnel sécurisé équivalent). Sans elle, les archives sont
  irrécupérables : c'est volontaire (chiffrement au repos, spec
  SP-Deploy §4.1).
- Accès à la cible hors-site (`BACKUP_S3_ENDPOINT`/`BACKUP_S3_BUCKET`) ou,
  à défaut, une copie locale d'une archive `.tar.gz.age`.
- Ce dépôt cloné, `.env` reconstruit (`./scripts/bootstrap-env.sh` puis
  compléter les secrets — de nouveaux secrets `PG_PASSWORD`/`MINIO_PASSWORD`
  sont acceptables : ils ne doivent PAS matcher ceux d'avant la perte, la
  restauration réinjecte les données, pas les identifiants d'infra).
- Le client MinIO officiel (`mc`) et `age` sur la machine qui pilote la
  restauration — ou, plus simplement, utiliser le conteneur `backup` déjà
  construit (image `deploy/backup/`) pour exécuter `mc`/`pg_restore`/`age`,
  comme fait ci-dessous : il embarque les trois. **Ne jamais** réintroduire
  `apk add mc` dans son Dockerfile — c'est Midnight Commander sous Alpine,
  pas le client MinIO (cf. Task 1).

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
  -v "$(pwd)/<horodatage>:/backup/restore:ro" --no-deps --entrypoint sh backup \
  -c "PGPASSWORD=\$PG_PASSWORD pg_restore -h postgis -U gis -d gis --clean --if-exists --no-owner /backup/restore/postgres.dump"
```

**Note :** Keycloak stocke ses realms/utilisateurs dans la même base `gis`
(`KC_DB_URL: jdbc:postgresql://postgis:5432/gis`, `docker-compose.yml`) —
cette seule commande restaure donc **déjà** tous les comptes utilisateurs.
L'export `keycloak-realm.json` de l'archive est un filet redondant (portable,
lisible), pas requis pour cette étape.

**Note d'invocation :** l'image `backup` définit `ENTRYPOINT
["/usr/local/bin/entrypoint.sh"]` (la boucle de planification quotidienne) —
Docker ne fait *pas* `exec "$@"` automatiquement avec cet entrypoint, donc
toute commande passée sans `--entrypoint` est silencieusement ignorée et le
conteneur reste bloqué dans sa boucle infinie. Toutes les invocations
manuelles de ce runbook utilisent donc `--entrypoint sh backup -c "..."` (ou
`--entrypoint /usr/local/bin/backup.sh backup` pour relancer un backup
complet) — jamais `backup <commande>` nu.

**Vérifié empiriquement (Task 2, Step 2)** : sur une base fraîche (volumes
neufs, rien à `--clean`), `pg_restore` ne produit **aucune sortie** — succès
silencieux, code de retour 0. Si la base cible contient déjà des objets
(cas d'un deuxième essai sur le même volume), `pg_restore --clean
--if-exists` peut émettre des avertissements `role "..." does not exist` sur
des objets possédés par des rôles non recréés ; `--no-owner` les rend sans
conséquence, la restauration continue.

## 4. Recréer les buckets MinIO et les repeupler

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh backup -c "
  mc alias set local http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD
  mc mb --ignore-existing local/geostudio-thumbnails local/geostudio-uploads local/geostudio-cdc
"
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v "$(pwd)/<horodatage>/minio:/backup/restore-minio:ro" --no-deps --entrypoint sh backup -c "
  mc alias set local http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD
  for b in /backup/restore-minio/*/; do
    [ -d \"\$b\" ] || continue
    mc mirror --overwrite \"\$b\" \"local/\$(basename \$b)\"
  done
"
```

**Bug trouvé en exécutant réellement cette étape (Task 2, Step 2)** : si
l'archive ne contient aucun bucket (cas d'un environnement où aucun fichier
n'a jamais été uploadé — les buckets applicatifs sont créés paresseusement
par `core`), le répertoire `minio/` de l'archive est vide et le glob
`/backup/restore-minio/*/` ne matche rien. Sous `sh` (pas de `nullglob`), le
motif reste alors **littéral** : `mc mirror` reçoit `/backup/restore-minio/*/`
comme chemin source et échoue avec `Unable to stat source ... not found`
(code de retour 1). La garde `[ -d "$b" ] || continue` ci-dessus (absente
d'une première version de ce runbook) corrige ce cas — vérifié : avec la
garde, le bloc se termine en code 0 sans rien mirorer quand `minio/` est
vide, et mirore correctement quand des buckets sont présents (testé avec un
fichier de test réel dans un bucket : `mc mirror` copie et le fichier est
relisible via `mc ls` après coup).

## 5. Démarrer le reste de la stack

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Keycloak redémarre avec `--import-realm` : le realm `geostudio` existe déjà
(restauré à l'étape 3). **Confirmé empiriquement (Task 2, Step 2)** :
`--import-realm` utilise la stratégie `IGNORE_EXISTING` par défaut — au
démarrage, Keycloak détecte que le realm `geostudio` existe déjà en base et
n'importe rien (pas de doublon, pas d'écrasement des données restaurées),
logs observés :
```
KC-SERVICES0030: Full model import requested. Strategy: IGNORE_EXISTING
Realm 'geostudio' already exists. Import skipped
KC-SERVICES0032: Import finished successfully
```
`core` applique `alembic upgrade head` sur une base déjà à jour (restaurée
à la bonne révision) — no-op confirmé : comparé à un premier démarrage sur
base vierge (qui journalise une ligne `Running upgrade X -> Y` par révision,
17 au total dans cet état du projet), le redémarrage post-restauration ne
journalise **aucune** ligne `Running upgrade` — le service sert
immédiatement.

## 6. Vérifier

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://$GEOSTUDIO_PUBLIC_HOST/api/me
```

Se connecter via le shell, confirmer qu'un utilisateur restauré peut se
reconnecter et qu'une donnée écrite avant le sinistre est relisible.

**Ce qui a été vérifié en exécution réelle (Task 2, Step 2)** : la moitié
« survie de la donnée » du critère §7-5 — cycle complet écriture → backup →
destruction totale (`down -v`) → étapes 1-5 ci-dessus → relecture, sur
environnement isolé (volumes jetables). Un item `sp-deploy-restore-check`
créé avant le backup (`GET /items/<id>` avant destruction) a été retrouvé
identique après restauration : d'abord relu **directement en base** via
`psql -c 'select id, title, resource_type from items;'` juste après
`pg_restore` (étape 3, avant même le redémarrage de `core`), puis via
`GET /items/<id>` après l'étape 5 (même `id`, même `title`, même horodatage
de création `date` à la microseconde près) — confirmant que la restauration
réinjecte les données existantes plutôt que d'en créer de nouvelles.

**Ce qui n'a PAS été vérifié** : la reconnexion utilisateur réelle via
Keycloak/OIDC. Cette exécution a démarré `core` avec un override local non
commité (`CORE_AUTH_MODE: mock`) pour appeler l'API avec un
`Authorization: Bearer x` factice, spécifiquement pour isoler le test sur
le cycle de restauration des données sans monter tout le flux OIDC
Keycloak/Traefik (hors périmètre de ce test). La surcouche prod
(`docker-compose.prod.yml`) fixe `CORE_AUTH_MODE: oidc` en dur en
production réelle, donc ce contournement ne s'applique pas à un vrai
déploiement — mais cela signifie que **le critère §7-5 n'a été vérifié qu'à
moitié par cette exécution** : la connexion effective d'un compte Keycloak
restauré via un vrai flux OIDC contre une stack restaurée reste un point
ouvert, à couvrir lors d'un futur exercice de restauration grandeur nature
(ou de la première restauration réelle en production).

Détail de l'exécution : rapport `.superpowers/sdd/task-2-report.md`.

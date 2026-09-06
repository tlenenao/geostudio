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
  restauration — ou, plus simplement, utiliser le conteneur `backup` pour
  exécuter `mc`/`pg_restore`/`age`, comme fait ci-dessous : il embarque les
  trois. Depuis SP-21 cette image est **publiée**
  (`ghcr.io/tlenenao/geostudio-backup:${GEOSTUDIO_VERSION}`) et l'overlay de
  production la substitue au `build:` du compose de base : sur une machine de
  restauration, `docker compose … run backup` la *télécharge*, il n'y a plus
  rien à construire. (Corollaire à connaître si le registre est inaccessible :
  la construction locale n'est plus un repli disponible depuis l'overlay
  prod, qui efface le `build:` — il faut alors le compose de base seul.) **Ne jamais** réintroduire
  `apk add mc` dans son Dockerfile — c'est Midnight Commander sous Alpine,
  pas le client MinIO (cf. Task 1).

## Avant une mise en production réelle

Checklist minimale de variables `.env` à régler explicitement avant un
déploiement réel (GAP-76, SP-49) — aucune ne bloque `docker compose up`,
mais chacune retombe silencieusement sur un défaut de démo/dev sinon :

- **`GRAFANA_ALERT_WEBHOOK_URL`** : vide par défaut, `docker-compose.yml`
  retombe alors sur un localhost inatteignable
  (`http://127.0.0.1:1/grafana-alert-webhook-not-configured`, décision
  assumée — une chaîne vide ferait échouer le provisioning alerting de
  Grafana au démarrage, cf. commentaire de `.env.example`). Sans cette
  variable, les alertes SLO Grafana (dossier `deploy/observability/grafana/
  provisioning/alerting/`) ne notifient personne.
- `PG_PASSWORD`/`MINIO_PASSWORD`/secrets Keycloak : voir Prérequis
  ci-dessous pour la restauration ; en déploiement initial, ne jamais garder
  les valeurs générées par `./scripts/bootstrap-env.sh` sans les avoir
  vérifiées (elles sont aléatoires, pas des placeholders faibles — mais à
  confirmer, pas à supposer).
- `CORE_SECRETS_MASTER_KEY` : requise dès le premier démarrage (garde
  SP-15e/SP-26) — `./scripts/bootstrap-env.sh` la génère désormais
  (`openssl rand -base64 32`, corrigé SP-42).

## Périmètre de la sauvegarde (ce qui revient, et ce qui ne revient pas)

**Restauré** : la base Postgres complète (donc aussi les comptes Keycloak,
même base `gis`), et sept buckets MinIO — `thumbnails`, `uploads`, `cdc`,
`tileset3d`, `terrain3d`, `mapicons`, `attachments`. **Correction SP-59** :
cette section n'en listait que cinq jusqu'ici (`mapicons`/`attachments`
ajoutés à `deploy/backup/backup.sh` après SP-33/SP-40, jamais reportés ici
ni côté restauration) — `restore.sh` (§3-4 ci-dessous) et cette liste sont
désormais synchronisés avec ce que `backup.sh` sauvegarde réellement,
garanti par `test_restore_recreates_every_bucket_backup_mirrors`.

**Volontairement non restauré** : les buckets `exports` et `appexports`. Ils
ne contiennent que des artefacts régénérables — un PDF de rapport planifié,
un bundle d'export d'app. Après restauration, un lien de téléchargement
émis avant la perte sera mort : c'est attendu, l'export se re-demande.

**Ce qui est prouvé, ce qui ne l'est pas (dernière mesure : SP-Deploy-b,
détail complet §6)** : la survie des données à travers un cycle complet
destruction→restauration a été observée une fois, en environnement isolé
(`CORE_AUTH_MODE=mock`) — voir §6 pour le détail exact de ce qui a été
vérifié. La reconnexion utilisateur via un vrai flux OIDC/Keycloak, et
l'affichage correct d'un item `tileset3d` après restauration, **restent non
vérifiés** à ce jour — voir la checklist OIDC en fin de document (§7,
SP-59) pour rejouer cet exercice correctement la prochaine fois qu'un
environnement Keycloak réel est disponible.

## 1. Récupérer et déchiffrer la dernière archive

Cette étape reste manuelle (SP-59 ne la scripte pas, spec §6) — elle produit
le répertoire `<horodatage>/` que `restore.sh` (chemin recommandé pour les
étapes 3+4 ci-dessous, `deploy/backup/restore.sh`, SP-59) consomme ensuite en
lecture seule.

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

**Chemin recommandé (SP-59)** : les étapes 3 et 4 ci-dessous sont désormais
scriptées ensemble par `deploy/backup/restore.sh`, embarqué dans l'image
`backup` — sa liste de buckets MinIO est tenue synchronisée avec
`deploy/backup/backup.sh` par un test dédié
(`core/tests/test_deployability.py::test_restore_recreates_every_bucket_backup_mirrors`),
ce que les commandes recopiées à la main ci-dessous ne garantissent pas :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm \
  -v "$(pwd)/<horodatage>:/backup/restore:ro" \
  --entrypoint /usr/local/bin/restore.sh backup <horodatage>
```

**Repli** : si l'image `backup` en service a été construite/publiée avant
SP-59 (ne contient pas encore `restore.sh` — cf. §5 de la spec SP-59, risque
de version d'image), les commandes détaillées ci-dessous restent le chemin
de dépannage documenté, étape par étape :

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

**Chemin recommandé (SP-59)** : couvert par la même invocation de
`restore.sh` que l'étape 3 ci-dessus — rien de plus à exécuter ici si le
script est disponible dans l'image `backup` en service.

**Repli** (commandes détaillées, si `restore.sh` n'est pas encore dans
l'image en service) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh backup -c "
  mc alias set local http://minio:9000 \$MINIO_USER \$MINIO_PASSWORD
  mc mb --ignore-existing local/\$S3_THUMBNAILS_BUCKET local/\$S3_UPLOADS_BUCKET local/\$S3_CDC_BUCKET local/\$S3_TILESET3D_BUCKET local/\$S3_TERRAIN3D_BUCKET local/\$S3_MAPICONS_BUCKET local/\$S3_ATTACHMENTS_BUCKET
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

**Note :** la commande `mc mb` ci-dessus recrée les sept buckets déclarés dans
la section « Périmètre de la sauvegarde » ci-dessus, en lisant les mêmes variables
d'environnement que `deploy/backup/backup.sh` (`S3_THUMBNAILS_BUCKET`,
`S3_UPLOADS_BUCKET`, `S3_CDC_BUCKET`, `S3_TILESET3D_BUCKET`,
`S3_TERRAIN3D_BUCKET`, `S3_MAPICONS_BUCKET`, `S3_ATTACHMENTS_BUCKET`) plutôt
que des noms de buckets recopiés en dur — ces sept variables sont déjà
injectées dans le service `backup` par `docker-compose.prod.yml`, dans
lequel cette commande tourne (`docker compose run --rm ... backup`).
**Correction SP-59** : cette commande n'en listait que cinq jusqu'ici — les
deux derniers buckets (`mapicons`, `attachments`) n'étaient jamais recréés,
silencieusement (cf. la correction de la section « Périmètre » ci-dessus).

Ajouter un bucket au périmètre de sauvegarde demande **trois** changements,
pas un (la version précédente de cette note promettait « une seule liste » —
c'est faux, et c'est le genre de promesse qui laisse une restauration
incomplète) : la liste de `deploy/backup/backup.sh`, l'`environment:` du
service `backup` dans `docker-compose.yml`, et la ligne `mc mb` ci-dessus (ou
la liste équivalente dans `deploy/backup/restore.sh`, chemin recommandé). Le
premier est outillé côté sauvegarde
(`test_backup_covers_every_bucket_the_core_uses`, qui compare les buckets lus
par `core/app/` à ceux que `backup.sh` sauvegarde) et, depuis SP-59, côté
restauration scriptée
(`test_restore_recreates_every_bucket_backup_mirrors`, qui compare
`backup.sh` à `restore.sh`) ; la commande `mc mb` ci-dessus (repli manuel,
non scripté) reste à la charge du rédacteur — c'est exactement pourquoi
`restore.sh` est désormais le chemin recommandé.

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

## 7. Checklist de vérification OIDC réelle (SP-59)

**Statut constaté à la clôture (Tâche 8 du plan SP-59, 2026-09-06) :
checklist rédigée, NON rejouée dans cette session.** Constat réel de
l'environnement d'exécution (`docker info` fonctionne, mais) : aucun realm
Keycloak réel ni stack complète ne tournait dans ce worktree au moment de
la clôture ; `.env` n'y a jamais été bootstrappé ; les ports 9000/9001
(service `minio` de ce compose) étaient déjà occupés par un conteneur
appartenant à une autre session concurrente sur la même machine ; la charge
machine mesurée au même instant (`uptime`) affichait une charge moyenne de
10 à 29 sur 6 à 13 processus `pytest` concurrents d'autres sessions —
construire les images `core`/`worker` et piloter une reconnexion OIDC
navigateur réelle dans ces conditions n'était pas une vérification fiable
à tenter dans cette session. Même limite d'environnement déjà rencontrée et
documentée honnêtement par SP-55 (volet SEO/Traefik) et SP-32 avant sa
session de levée. **Ne pas présumer cette checklist exécutée par défaut** :
relire ce paragraphe avant de citer cette section comme une preuve.

Objectif : couvrir la moitié du critère §7-5 laissée ouverte par
l'exécution SP-Deploy-b (§6 ci-dessus) — la reconnexion utilisateur via un
**vrai** flux OIDC/Keycloak après restauration, jamais `CORE_AUTH_MODE=mock`
pour cet exercice précis (à la différence de l'exercice SP-Deploy-b déjà
documenté plus haut dans ce même fichier).

**Préconditions** :
- Un realm Keycloak réel et accessible (le realm `geostudio` provisionné
  par ce dépôt convient), avec au moins un utilisateur de test capable de
  s'authentifier par mot de passe.
- `CORE_AUTH_MODE=oidc` explicitement — jamais `mock` — sur toute la durée
  de l'exercice.
- Un accès navigateur réel au shell (pas seulement `curl`/l'API).
- Docker fonctionnel sur la machine d'exécution (constat préalable,
  Tâche 8 du plan SP-59).

**Séquence** :
1. Sur la stack de départ (avant tout sinistre), créer — ou confirmer
   l'existence d' — un utilisateur Keycloak de test, et se connecter avec
   ce compte via le flux de connexion réel du shell (pas mock).
2. Toujours avec ce compte, créer un item de test (ex. une collection vide
   ou une carte), en noter l'identifiant.
3. Déclencher un backup réel (`deploy/backup/backup.sh` via le service
   `backup`, ou attendre son cycle planifié).
4. Détruire totalement l'environnement (`docker compose down -v` — volumes
   compris).
5. Restaurer via `restore.sh` (§3-4 ci-dessus, chemin recommandé) puis
   démarrer le reste de la stack (§5 ci-dessus).
6. Se connecter à nouveau via le shell, avec le **même compte Keycloak**,
   par un flux de connexion navigateur réel (redirection OIDC complète —
   pas un jeton mock, pas un `Authorization: Bearer` fabriqué à la main).
7. Confirmer que l'item créé à l'étape 2, avant le sinistre, est visible et
   accessible **par ce compte reconnecté** — pas seulement en base ou via
   un jeton de test.

**Ce qui clôt réellement cette checklist** : succès des 7 étapes
ci-dessus, en particulier l'étape 6 (redirection OIDC complète, pas de
`CORE_AUTH_MODE=mock`) et l'étape 7 (donnée visible par le compte
reconnecté, pas seulement par l'API). Un échec à l'étape 6 (impossible de
se reconnecter) est le signal le plus grave possible de ce runbook — à
documenter précisément (message d'erreur réel), jamais à arrondir en
« probablement OK ».

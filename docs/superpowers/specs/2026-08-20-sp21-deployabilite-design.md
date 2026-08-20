# Déployabilité de ce qui est déjà livré (SP-21)

> Vague 1 du plan d'action `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
> (§4, chantiers 1.1 → 1.6). Constats sources : C4, C5, I5, I8, I14.
> Spec écrite le 2026-08-20, après vérification de chaque chantier contre le
> code réel (les six constats du plan ont tous été retrouvés ; deux écarts,
> cf. §2).

## 1. Contexte & objectif

Cinq SP livrés et payés n'ont **aucun chemin de déploiement en production** :
l'export PDF (SP-17a) et les rapports planifiés qui en dépendent (SP-17b), les
algorithmes QGIS (SP-15d), l'export d'apps (SP-18a/b) et — le plus grave — le
mécanisme de sauvegarde. Déployer l'un d'eux exige aujourd'hui de cloner les
sources sur l'hôte de production et d'y compiler Chromium ou QGIS, ce qui
contredit l'en-tête de `docker-compose.prod.yml` lui-même (« images depuis
GHCR (au lieu de `build:`) »).

Cette vague ne livre **aucune fonctionnalité produit**. Elle rend utilisable
ce qui existe déjà, et elle installe le contrôle automatique qui empêche la
classe de bug de revenir : trois incidents documentés (SP-17a, SP-17b,
tileset3d) sont exactement le même défaut — une capacité livrée, testée,
mergée, et non câblée dans la stack packagée.

Objectif de sortie : un tag `v*` produit tout ce qu'il faut pour déployer
n'importe quelle capacité du produit, et la CI refuse toute régression de
cette propriété.

## 2. État vérifié (2026-08-20) et écarts avec le plan

| # | Constat du plan | Vérification |
|---|---|---|
| 1.1 | `release.yml` ne publie que 4 images | **confirmé** : `geostudio-core`, `-shell`, `-postgis`, `-appexport-standalone` |
| 1.2 | L'overlay prod ne substitue que 5 services | **confirmé** : `postgis`, `core`, `worker`, `cdc-worker`, `shell`. Restent en `build:` : `export-worker`, `qgis-worker`, `appexport-runtime-builder` (base) et `backup` (déclaré uniquement dans l'overlay) |
| 1.3 | `backup.sh` couvre 3 buckets sur 7 | **confirmé** : `thumbnails`, `uploads`, `cdc` ; le cœur lit aussi `exports`, `appexports`, `tileset3d`, `terrain3d`. `S3_EXPORTS_BUCKET`, `S3_APPEXPORTS_BUCKET`, `S3_CDC_BUCKET` absents de `.env.example` |
| 1.5 | Aucun contrôle de déployabilité | **confirmé** : 52 variables lues par `os.environ` dans `core/app/`, aucune vérification |
| 1.6 | Images non pinnées, healthchecks absents | **confirmé** : `minio/minio` **sans aucun tag**, `tailscale/tailscale:latest`, `traefik:v3.0`, `keycloak:24.0` ; healthchecks sur `postgis`/`minio`/`keycloak` seulement |

Deux écarts, tous deux dans le sens de l'aggravation :

- **Écart 1 (nouveau constat)** — les quatre variables `CORE_EMBEDDING_*`
  (fournisseur d'embeddings de SP-7) et `CORE_ANALYST_SUBS` (rôle analyste de
  SP-11c) ne sont câblées sur **aucun** service. La recherche sémantique et le
  rôle analyste ne sont donc pas configurables dans la stack packagée : le
  cœur retombe silencieusement sur ses valeurs par défaut. Ces cinq variables
  n'étaient pas dans la liste du plan ; elles sortent de la règle de §4.2
  (test 3), ce qui est une preuve d'utilité de la règle avant même son
  écriture — elles sont câblées en §4.3.
- **Écart 2 (règle du plan trop large)** — la formulation du plan (« toute
  variable lue par `os.environ` figure dans l'environnement d'au moins un
  service **et** dans `.env.example` ») est fausse sur sa seconde moitié :
  `DATABASE_URL`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `APPEXPORT_RUNTIME_DIR` sont
  des valeurs **dérivées**, calculées dans le compose à partir d'autres
  variables ; les exiger dans `.env.example` inviterait l'opérateur à les
  régler à la main, ce qui est un piège. La règle est donc scindée en deux
  tests distincts (§4.2, tests 3 et 4) : « câblée sur un service » d'un côté,
  « documentée dans `.env.example` » de l'autre, cette seconde règle ne
  portant que sur les substitutions `${VAR}`, c'est-à-dire exactement les
  valeurs que l'opérateur doit fournir.

## 3. Périmètre

Dans le périmètre : **1.1**, **1.2**, **1.3**, **1.5**, **1.6**.

Hors périmètre, décidé en session le 2026-08-20 : **1.4 — rejouer la
restauration pour de vrai**, renvoyé au lot de la vague 2. Conséquence directe
sur 1.3, dont le plan faisait dépendre la preuve de sortie de ce cycle réel :
elle est remplacée par une vérification mécanique (§4.4), et la garantie « un
item `tileset3d` reste affichable après restauration » reste **non prouvée
empiriquement** jusqu'à la vague 2. C'est un renoncement assumé, pas un oubli :
la sauvegarde couvrira le bucket, mais personne n'aura vu la restauration
fonctionner.

Également hors périmètre (mentionné pour éviter la confusion) : le rate
limiting différencié (vague 3.4), l'unification des trois gardes d'egress
(vague 6.2), et toute correction du volume `pg-data` cassé du projet compose
par défaut (suivi non bloquant préexistant).

## 4. Mécanisme

### 4.1 Le garde-fou est le test qui échoue d'abord

L'ordre d'exécution est une inversion volontaire, et c'est le cœur de la
spec : `core/tests/test_deployability.py` s'écrit **avant** tout correctif de
câblage. Ses tests sont rouges sur le dépôt d'aujourd'hui, et chacun des
chantiers 1.1/1.2/1.3/1.6 existe pour en faire passer un. Le TDD s'applique
donc au dépôt lui-même, pas seulement au code applicatif : la « feature » est
la propriété « ce dépôt est déployable », et le test la définit.

Choix de forme (décidé en session) : des tests `pytest` dans `core/tests/`,
pas un job CI dédié avec un script autonome. Raisons :

- le job `core` de `ci.yml` fait déjà tourner `uv run pytest` — aucune
  infrastructure CI nouvelle, donc rien de plus à câbler (ce serait
  ironique) ;
- chaque règle porte un nom de test et un message d'échec en français
  actionnable, là où un script produit une sortie plate ;
- les exemptions sont des constantes commentées du fichier de test, versionnées
  avec leur raison — c'est ce qui distingue « exempté sciemment » de
  « oublié », et c'est le seul mécanisme qui survit à des sessions successives
  sans mémoire partagée ;
- `core/` est le seul répertoire du dépôt qui possède déjà un runner Python.
  `PyYAML` y est présent (6.0.3) mais seulement en **dépendance transitive**,
  non déclarée : ces tests l'importent directement, donc `pyyaml` entre dans
  le groupe `dev` de `core/pyproject.toml` avec son commentaire de raison
  (même classe de dette que le `anyio` non déclaré fermé le matin même — un
  import direct d'une dépendance qu'on ne demande pas casse au premier
  changement d'arbre transitif).

Entorse assumée : `core/tests/` teste du déploiement, donc des fichiers hors
de `core/`. Le fichier le dit dans son docstring de module.

Aucun test de ce fichier n'exige docker : ils lisent les YAML et les scripts.
Le plan (1.2) demandait littéralement un `docker compose config` ; l'équivalent
sémantique — « tout service `build:` de la base est substitué par un `image:`
dans l'overlay » — est vérifiable sans docker et **plus précis** (il nomme le
service fautif). Un `docker compose config` réel sera exécuté **une fois, à la
main, pendant l'implémentation**, et son résultat consigné dans le rapport de
tâche ; il ne devient pas un test permanent.

### 4.2 Les six règles

| Test | Règle | État initial attendu |
|---|---|---|
| `test_every_build_service_has_a_released_image` | tout service portant un `build:` (base ou overlay) a une entrée correspondante dans la matrice `build-and-push` de `release.yml` | **rouge** (4 manquants) |
| `test_prod_overlay_leaves_no_build_directive` | tout service `build:` de la base est substitué par un `image:` dans l'overlay prod ; l'overlay n'introduit lui-même aucun `build:` | **rouge** (4 manquants) |
| `test_every_core_env_var_is_wired_to_a_service` | toute variable lue par `os.environ` dans `core/app/` apparaît dans l'`environment` d'au moins un service de `docker-compose.yml`, sauf exemption déclarée | **rouge** (5 manquantes) |
| `test_every_compose_substitution_is_documented` | toute substitution `${VAR}` des deux composes apparaît dans `.env.example` | **vert** (43/43 aujourd'hui) — pur garde-fou anti-régression |
| `test_backup_covers_every_bucket_the_core_uses` | la boucle de miroir de `deploy/backup/backup.sh` couvre tous les buckets `S3_*_BUCKET` lus par le cœur, sauf exclusion déclarée | **rouge** (4 manquants) |
| `test_images_are_pinned_to_a_patch_version` | tout `image:` des deux composes porte un tag explicite à trois composants | **rouge** (4 non conformes) |

Le quatrième test est vert dès l'écriture. C'est délibéré et il est conservé :
la propriété est aujourd'hui vraie par chance, elle a de la valeur en
régression, et son coût est nul. Le rapport de tâche doit le signaler comme tel
plutôt que de le présenter comme un correctif.

Trois exemptions prévues pour la règle de câblage, chacune avec sa raison :

- `S3_CDC_BUCKET_BASE_URI` — couture de test (lecture locale de partitions CDC),
  jamais réglée en production ;
- `APPEXPORT_STANDALONE_DATA_DIR` et `APPEXPORT_STANDALONE_RUNTIME_DIR` — lues
  par l'image mini-serveur de l'export autoporté (SP-18c), dont le compose est
  **généré** par `build_standalone_bundle_zip`, pas celui du dépôt.

La liste d'exemptions est fermée : toute variable nouvelle est soit câblée,
soit exemptée avec une raison écrite. C'est cette contrainte qui a de la valeur,
pas la liste elle-même.

### 4.3 Câblage des variables manquantes (conséquence de la règle)

Cinq variables entrent dans `docker-compose.yml` :

- `CORE_EMBEDDING_PROVIDER`, `CORE_EMBEDDING_API_URL`, `CORE_EMBEDDING_API_KEY`,
  `CORE_EMBEDDING_MODEL` sur `core` **et** `worker` (l'indexation sémantique
  tourne en job) ;
- `CORE_ANALYST_SUBS` sur `core`.

Toutes avec un défaut vide (`${VAR:-}`), donc sans changement de comportement
pour une instance existante, et documentées dans `.env.example` par la même
occasion — ce qui les fait entrer dans la règle du quatrième test.

### 4.4 Sauvegarde (1.3)

`backup.sh` passe de 3 à 5 buckets miroités : ajout de `tileset3d` et
`terrain3d`. Motif, à écrire dans le script : un tileset 3D uploadé est un
objet S3 **jamais extrait et sans autre copie**, dont les métadonnées vivent
dans `BuilderConfig.tileset3d` ; après une restauration sans ce bucket, l'item
réapparaît intact en pointant sur une clé disparue — donc définitivement cassé,
**sans erreur au moment de la restauration**. C'est le pire mode d'échec
possible : silencieux et différé.

`exports` et `appexports` restent exclus, mais **explicitement** : une ligne de
commentaire dans le script et un paragraphe dans le runbook disant que ce sont
des artefacts régénérables (un export PDF ou un bundle d'app se re-demande).
L'exclusion est déclarée dans le test, donc elle survit à une relecture.

Les trois variables de bucket absentes de `.env.example` y entrent, commentées,
en signalant que le compose les fixe en dur — l'opérateur les découvre sans
être invité à les régler.

Le service `backup` du compose reçoit les deux nouvelles variables de bucket.

### 4.5 Images publiées (1.1) et overlay (1.2)

La matrice `build-and-push` passe de 4 à 8 entrées :

| Image | Contexte | Dockerfile |
|---|---|---|
| `geostudio-export-worker` | `./core` | `../deploy/export-worker/Dockerfile` |
| `geostudio-qgis-worker` | `./deploy/qgis-worker` | `Dockerfile` |
| `geostudio-appexport-runtime-builder` | `.` | `deploy/appexport-runtime-builder/Dockerfile` |
| `geostudio-backup` | `./deploy/backup` | `Dockerfile` |

Le motif de chemin de la matrice existante (`file: ${{ matrix.context }}/${{
matrix.dockerfile }}`) accepte tel quel le dockerfile hors contexte de
`export-worker`.

L'overlay substitue les quatre par leur image GHCR, **profils conservés**
(`export`, `etl`, `appexport`) : une capacité désactivée ne doit pas démarrer
davantage après cette vague qu'avant. `backup`, aujourd'hui déclaré uniquement
dans l'overlay avec `build: ./deploy/backup`, y passe en `image:`.

Deux conséquences acceptées explicitement en session (2026-08-20) :

- **Coût CI et registre** — un tag `v*` construira désormais Chromium
  (`export-worker`) et QGIS 3.34 + GRASS (`qgis-worker`), soit plusieurs Gio.
  Le job de release s'allonge nettement. Accepté : l'alternative (compiler sur
  l'hôte de production) est précisément le problème qu'on corrige.
- **Licence** — publier `geostudio-qgis-worker` sur `ghcr.io` est un **acte de
  distribution de QGIS et de GRASS, tous deux sous GPL**. Cela ne contamine
  pas le cœur Apache-2.0 (sidecar dans une image séparée, sans lien de code,
  arbitrage A39 intact), mais l'image publiée doit porter la notice. Aucun
  document du dépôt ne couvre ce cas aujourd'hui : le seul écrit existant est
  l'arbitrage d'**isolation**, pas la **redistribution**. Décision : on publie,
  avec (a) un fichier de licence/notice à l'intérieur de l'image, (b) une note
  dans `docs/` renvoyant aux sources amont de QGIS et aux deux seuls fichiers
  que nous ajoutons par-dessus (`server.py`, `allowlist.txt`), tous deux
  publics dans ce dépôt sous Apache-2.0. L'offre de source est ainsi
  satisfaite par référence, ce qui est la forme usuelle pour une image dérivée
  sans modification de l'amont.

### 4.6 Pins et healthchecks (1.6)

Pinning **au patch pour tous** : `minio/minio` (aujourd'hui sans tag),
`tailscale/tailscale` (aujourd'hui `:latest`), `traefik:v3.0` et
`keycloak:24.0` (aujourd'hui flottants au mineur). Règle unique, sans
exception à justifier ; les mises à jour deviennent des commits explicites,
ce qui est l'objectif.

Contrainte d'implémentation non négociable : **les tags sont résolus en
interrogeant le registre, jamais devinés**. Précédent direct — SP-15d a
découvert que `qgis/qgis:latest` pointait vers un build 4.3.0-master instable ;
un tag inventé qui n'existe pas ne se voit qu'au `docker compose pull`, donc
après la release.

Healthchecks ajoutés : `core` (`GET /health`), `shell`, `pgbouncer`, `martin`,
`titiler`, `worker`, `cdc-worker`. Pour les trois derniers, la sonde ne peut
pas être une requête HTTP — aucun port exposé. Le patron exact est à choisir au
moment du plan, avec une préférence explicite pour une commande qui échoue
aussi quand le worker est **vivant mais bloqué** (I5 nomme ce cas), et non
seulement quand le process est mort ; si aucun patron fiable n'est trouvé, une
sonde de liveness du process est acceptable **à condition** que le rapport de
tâche dise ce qu'elle ne détecte pas.

`depends_on: core: condition: service_healthy` sur `shell` et `export-worker`
uniquement. Pas de chaîne complète : SP-18a a dû *retirer* une dépendance dure
de `worker` parce qu'elle bloquait le démarrage de la stack pour une capacité
désactivée par défaut — le même piège s'applique ici, et une dépendance dure
mal placée transforme un service lent en panne totale.

## 5. Ordre d'exécution

1. `test_deployability.py` en entier (6 tests) — 5 rouges, 1 vert. Constater
   chaque échec et vérifier qu'il échoue **pour la bonne raison**.
2. 1.1 + 1.2 (images + overlay) → verdissent les tests 1 et 2.
3. 4.3 (câblage des 5 variables) → verdit le test 3.
4. 1.3 (buckets + `.env.example` + runbook) → verdit le test 5.
5. 1.6 (pins + healthchecks) → verdit le test 6.
6. `docker compose config` réel, base + overlay + les trois profils, une fois,
   à la main — preuve consignée dans le rapport.

## 6. Validation & preuves de sortie

| Chantier | Preuve |
|---|---|
| 1.1 | `test_every_build_service_has_a_released_image` vert ; la matrice compte 8 entrées |
| 1.2 | `test_prod_overlay_leaves_no_build_directive` vert ; `docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile export --profile etl --profile appexport config` ne contient plus aucun `build:` (exécution manuelle unique, consignée) |
| 1.3 | `test_backup_covers_every_bucket_the_core_uses` vert ; les exclusions `exports`/`appexports` sont écrites dans le script et le runbook |
| 1.5 | les 6 tests verts ; retirer `CORE_TILESET3D_ENABLED` du service `core` rend le test 3 rouge ; ajouter un `os.environ["CORE_NOUVEAU"]` non câblé le rend rouge aussi (les deux vérifiés à la main, consignés) |
| 1.6 | `test_images_are_pinned_to_a_patch_version` vert ; `docker compose config \| grep -c ":latest"` → 0 ; `docker compose ps` montre les nouveaux services `healthy` |

Le test 4 (`substitutions documentées`) est vert dès l'écriture : à signaler
comme garde-fou, pas comme correctif.

## 7. Risques et limites connues

- **La preuve de restauration reste absente.** 1.3 ajoute les buckets au
  périmètre de sauvegarde, mais personne n'aura vu une restauration
  fonctionner avant la vague 2. Un `mc mirror` qui échoue silencieusement sur
  un bucket volumineux, ou une clé S3 restaurée sous un nom différent,
  resteraient invisibles. À dire tel quel dans le CLAUDE.md de clôture.
- **Le garde-fou lit des YAML, il ne démarre rien.** Un compose
  syntaxiquement valide, complet en variables et pinné peut toujours être
  cassé à l'exécution (mauvaise valeur, image inexistante au registre). La
  règle attrape la classe de bug des trois incidents documentés — capacité non
  câblée — pas toutes les pannes de déploiement.
- **Un tag inexistant au registre passe le test 6.** La règle vérifie la
  *forme* du tag, pas son existence. D'où la contrainte de §4.6 (résoudre
  contre le registre), qui reste une discipline humaine, non outillée.
- **Les 8 images ne sont pas testées au démarrage par la CI.** La release les
  construit et les pousse ; rien ne prouve qu'un `docker compose pull` puis
  `up` de l'overlay complet fonctionne. Ce serait une vague à part
  (déploiement de bout en bout sur instance jetable), volontairement non
  ouverte ici.
- **Le pinning au patch crée une dette d'entretien.** Quatre images de plus à
  remonter à la main. C'est le prix assumé du choix ; aucun outil de mise à
  jour automatique (dependabot compose) n'est mis en place dans cette vague.

## 8. Décisions prises en session (2026-08-20)

1. **1.4 renvoyé en vague 2** — la répétition réelle du runbook de
   restauration ne fait pas partie de cette vague ; la preuve de sortie de 1.3
   est reformulée en conséquence (§3, §4.4).
2. **Garde-fou en tests `pytest`** dans `core/tests/test_deployability.py`,
   pas en job CI dédié avec script autonome (§4.1).
3. **Pinning au patch pour tout**, y compris `traefik` et `keycloak`
   (§4.6).
4. **Healthchecks partout, dépendance dure sur `core` seulement** pour `shell`
   et `export-worker` (§4.6).
5. **`geostudio-qgis-worker` est publié**, avec notice GPL dans l'image et note
   de redistribution dans `docs/` (§4.5).
6. **Le coût CI de 8 images est accepté** (§4.5).

# Task 4 — lancement final, attente de santé, idempotence (critère §7-6)

## Ce qui a été implémenté

Ajout de deux fonctions à la fin de `scripts/install.sh` (après `prompt_admin`,
appelées immédiatement) :

- `launch_stack()` : `$COMPOSE up -d` avec les profils sélectionnés (Task 2),
  puis attente jusqu'à 60 s (30 × 2 s) que `core` réponde `401` sur `/me`
  (endpoint authentifié — 401 = "vivant et applique bien l'auth", pas 200),
  puis seed optionnel (`SEED_DEMO=true` → `python -m scripts.seed_demo`,
  erreurs tolérées via `|| true`).
- `print_summary()` : message final (URL publique, admin, rappels backup/age),
  mot pour mot conforme au brief.

**Écart volontaire par rapport au brief, découvert à l'exécution réelle** :
le brief spécifiait `docker compose exec -T core curl -s -o /dev/null -w
'%{http_code}' http://localhost:8200/me`. En testant pour de vrai (voir plus
bas), j'ai constaté que **ni `curl` ni `wget` ne sont présents dans l'image
`core`** (`python:3.12-slim` + `uvicorn`, aucun outil HTTP CLI installé) — la
commande échoue systématiquement avec `exec: "curl": executable file not
found`, ce qui aurait fait échouer la vérification de santé à **chaque**
déploiement réel, pas seulement dans cet environnement de test. J'ai remplacé
l'appel `curl` par un script Python inline (`python3 -c '...'` avec
`urllib.request`), l'interpréteur Python étant garanti présent puisque c'est
lui qui fait tourner `uvicorn`. Comportement fonctionnellement identique
(distingue "erreur HTTP avec code" de "pas encore de connexion" → `000`),
testé et vérifié en conditions réelles (voir ci-dessous). C'est le même type
d'écueil que celui déjà rencontré et documenté par Task 3 pour `kcadm.sh`/
Keycloak (absence de curl/wget dans cette image aussi).

Ajout aussi de `local code="000"` (absent du snippet du brief) — cohérent
avec le style déjà établi dans le fichier (`local existing_id`, `local
admin_temp_password`, `local dns_name=""`, `local authenticated=false` dans
les fonctions précédentes), évite une fuite de variable globale.

Aucun autre ajout — dernière tâche du plan, rien au-delà du périmètre du
brief.

## Stratégie de vérification et sorties réelles

Tailscale/`TS_AUTHKEY` n'existe pas dans cet environnement : `activate_funnel()`
(Task 3, déjà committé, non modifié) échouerait et ferait avorter tout le
script avant d'atteindre `launch_stack`/`print_summary` dans un run
top-à-bas littéral. J'ai donc extrait uniquement les deux fonctions de ce
Task via `awk` depuis le vrai `scripts/install.sh` (copié dans le clone
jetable, pas de duplication manuelle de la logique testée), sourcées dans un
harness (`harness.sh`) dans un clone jetable (`/tmp/geostudio-install-test`,
jamais le dépôt réel), avec `COMPOSE`, `SELECTED_PROFILES=()`, `SEED_DEMO`,
`PUBLIC_HOST=test.example.com`, `ADMIN_EMAIL=test@example.com` positionnées à
la main. `.env` généré pour de vrai via `./scripts/bootstrap-env.sh`.

### Découverte en cours de route : image GHCR `core` obsolète

`docker-compose.prod.yml` (utilisé par `$COMPOSE`) pointe vers des images
publiées `ghcr.io/tlenenao/geostudio-core:latest` etc. Ces images se sont
révélées **publiquement accessibles et téléchargeables** (réseau sortant
fonctionnel dans cet environnement), mais l'image `core` publiée s'est avérée
**périmée/cassée** : `alembic.ini`, le dossier `alembic/` et `scripts/` sont
absents de l'image alors que le `Dockerfile` actuel du dépôt les copie bien
(`COPY alembic.ini ./alembic.ini`, etc.) — dérive entre l'image publiée et le
code source actuel, probablement liée au point déjà noté dans CLAUDE.md
("Tags d'images Docker … à repinner si dérive"). Ceci est **hors périmètre de
cette tâche** (pipeline de publication d'image, pas `install.sh`). Pour
pouvoir vérifier `launch_stack`/`print_summary` malgré ce défaut préexistant
et sans rapport avec mon code, j'ai reconstruit l'image `core` localement
(`docker build -t ghcr.io/tlenenao/geostudio-core:latest ./core` dans le
clone jetable) — Docker Compose utilise alors le tag local en cache au lieu
de re-tirer l'image GHCR cassée. Ceci n'affecte en rien la commande réelle du
script (`$COMPOSE … up -d` reste inchangée) ; seul le contenu de l'image
locale utilisée pour la vérification diffère de l'image GHCR publiée.

### Passe 1 — premier lancement complet (`SEED_DEMO=false`)

```
$ time bash harness.sh
… (création réseau/volumes/conteneurs : postgis, pgbouncer, minio, martin,
   titiler, keycloak, core, worker, cdc-worker, shell, traefik, tunnel,
   backup — 13 services, aucun profil sélectionné) …
Attente de la disponibilité du cœur...
✓ Cœur opérationnel.

═══ GeoStudio est en ligne ═══
URL publique : https://test.example.com/
Admin        : test@example.com

Prochaines étapes :
  - Se connecter avec le compte admin (mot de passe temporaire affiché ci-dessus, à changer).
  - Si une cible de sauvegarde a été configurée : générer une paire de clés
    age (age-keygen) et renseigner BACKUP_AGE_RECIPIENT dans .env, puis
    redémarrer le service backup ('docker compose ... restart backup').
  - Conserver .env et la clé privée age en lieu sûr, hors de cette machine.

real    0m1.681s
```
(Cette passe a été rejouée après la correction curl→python3 ; une première
tentative avec `curl` avait bien échoué comme attendu, avec le message
d'erreur voulu après épuisement des 30 itérations : `✗ Le cœur ne répond pas
comme attendu (code OCI runtime exec failed: … "curl": executable file not
found …) — vérifiez 'docker compose logs core'.` — confirmant que la boucle
d'attente et le message d'échec fonctionnent bien en cas d'échec réel.)

`docker compose ps` : 12 conteneurs `Up`/`Healthy` (postgis, pgbouncer,
minio, martin, titiler, keycloak, core, worker, cdc-worker, shell, traefik,
backup, plus `tunnel` — celui-ci démarre mais son daemon Tailscale échouera à
s'authentifier avec la fausse clé de test, sans bloquer `docker compose up
-d` ni la suite : comportement indépendant de `launch_stack`, propre à
Tailscale).

### Passe 2 — relance immédiate (idempotence, `SEED_DEMO=false`)

```
$ docker compose … ps --format "table {{.Name}}\t{{.Status}}" > ps-before.txt
$ time bash harness.sh
…
Attente de la disponibilité du cœur...
✓ Cœur opérationnel.
[print_summary identique]
real    0m1.667s
$ docker compose … ps --format "table {{.Name}}\t{{.Status}}" > ps-after.txt
$ diff ps-before.txt ps-after.txt
3c3
< geostudio-install-test-cdc-worker-1   Up 13 seconds
---
> geostudio-install-test-cdc-worker-1   Up 15 seconds
13,14c13,14
< geostudio-install-test-tunnel-1       Up 9 seconds
< geostudio-install-test-worker-1       Up 5 seconds
---
> geostudio-install-test-tunnel-1       Up 11 seconds
> geostudio-install-test-worker-1       Up 7 seconds
```
Seule différence : l'âge affiché (2 secondes se sont écoulées). Aucun
conteneur recréé, aucun message "Recreate"/"Created" dans la sortie de la
passe 2 (uniquement "Running"/"Healthy"/"Waiting") — `docker compose up -d`
confirmé idempotent sur une stack déjà démarrée, et la boucle d'attente a
trouvé `/me` répondant `401` dès la première itération (passe en ~1,7 s au
lieu d'attendre jusqu'à 60 s).

### Passe 3 — `SEED_DEMO=true`, premier seed

Après avoir positionné `CORE_ADMIN_SUBS` dans `.env` (simulateur du résultat
de `prompt_admin`, Task 3, non ré-exécuté ici) et recréé le conteneur `core`
pour qu'il le lise :

```
$ time bash harness.sh
…
Attente de la disponibilité du cœur...
✓ Cœur opérationnel.
{"level": "ERROR", … "échec de l'enqueue du job d'embedding … procrastinate.exceptions.AppNotOpen …"}  (×2, incidents + points_interet)
collections créées : ['incidents', 'points_interet']

═══ GeoStudio est en ligne ═══
…
real    0m2.699s
```
Les deux collections de démo (`incidents`, `points_interet` — tables déjà
présentes dans l'image `postgis` de démo) ont bien été créées. Les erreurs
d'enqueue d'embedding (`procrastinate.exceptions.AppNotOpen`) sont **non
bloquantes** (le message applicatif l'indique explicitement : "l'écriture
n'est pas affectée") et préexistantes à cette tâche (comportement de
`app/collections/repository.py`), hors périmètre.

### Passe 4 — `SEED_DEMO=true`, second appel (idempotence du seed)

```
$ time bash harness.sh
…
Attente de la disponibilité du cœur...
✓ Cœur opérationnel.
collections créées : aucune (déjà en place)

═══ GeoStudio est en ligne ═══
…
real    0m2.387s
```
Confirmé : `seed_demo.py` est bien idempotent comme documenté dans son
docstring (`get_collection` vérifié avant toute création) — second appel sans
erreur, sans doublon.

### Nettoyage

`docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v`
exécuté après la série de passes ; image `core` locale reconstruite
supprimée (`docker image rm`) ; clone jetable `/tmp/geostudio-install-test`
supprimé (`rm -rf`).

## Ce qui a pu / n'a pas pu être vérifié de bout en bout

**Vérifié réellement, en conditions Docker/Postgres/Keycloak/core réelles :**
- `launch_stack()` : `up -d` avec profils, boucle d'attente de santé (trouve
  `401` immédiatement sur stack déjà chaude ; testerait bien le polling sur
  60 s si le cœur n'était pas encore prêt — observé lors du premier essai
  raté avec `curl`, où la boucle épuisait ses 30 itérations avant d'échouer
  proprement avec le message d'erreur attendu).
- `print_summary()` : sortie exacte conforme au brief.
- Idempotence de `docker compose up -d` sur une stack déjà démarrée (aucune
  recréation de conteneur, `docker compose ps` inchangé à l'âge près).
- Idempotence de `python -m scripts.seed_demo` (second appel : "aucune (déjà
  en place)", aucune erreur, aucun doublon).
- Non-régression globale core (pytest, lint-imports) et shell (vitest, build)
  — dépôt réel, pas le clone jetable.

**Non vérifiable dans cet environnement, et pourquoi (même classe d'écueil
que Task 3, déjà précédenté en Task 6 de SP-Deploy-a) :**
- Le run **littéral** de bout en bout du Step 2 du brief
  (`INSTALL_YES=1 TS_AUTHKEY=<clé> ./scripts/install.sh` deux fois de suite,
  tel quel) : `activate_funnel()` (code Task 3, non modifié) échoue sans
  compte Tailscale réel, ce qui abandonne le script avant `launch_stack`.
  Contourné par l'extraction ciblée décrite plus haut, qui exerce le code
  réel de ce Task contre une vraie stack Docker.
- L'activation effective du Funnel Tailscale elle-même (hors périmètre de ce
  Task — code déjà revu en Task 3).
- Le comportement de l'image `core` **publiée sur GHCR** telle quelle (elle
  s'est avérée cassée/périmée, problème de pipeline de publication distinct
  d'`install.sh` — signalé mais non corrigé, hors périmètre de cette tâche).

## Fichiers modifiés

- `/home/lenen/projets/geostudio/scripts/install.sh` — ajout de
  `launch_stack()` et `print_summary()` (+ appels), avec la substitution
  curl→python3 documentée ci-dessus.

## Revue personnelle (self-review)

- **Complétude** : les deux fonctions du brief sont présentes, `print_summary`
  mot pour mot ; `launch_stack` fonctionnellement équivalente au brief (seul
  le mécanisme de sonde HTTP diffère, pour une raison de correction vérifiée
  empiriquement, documentée en commentaire dans le script).
- **Qualité** : `local code="000"` ajouté par cohérence avec le style établi
  du fichier (variables d'état de boucle déclarées `local` ailleurs dans le
  même fichier : `local existing_id`, `local admin_temp_password`, `local
  dns_name=""`, `local authenticated=false`). `for p in …` non localisé,
  comme le reste du fichier (`for _ in $(seq …)`, `while IFS= read -r
  profile` ne déclarent pas non plus leur variable de boucle en `local`) —
  cohérent, pas d'incohérence introduite.
- **Discipline** : aucun ajout au-delà du périmètre du brief ; dernière tâche
  du plan, rien laissé en suspens intentionnellement au-delà de la
  substitution curl→python3 (nécessaire : sans elle, le health-check ne
  fonctionnerait jamais en pratique, dans aucun environnement).
- **Incident de staging lors du commit (corrigé)** : `.superpowers/sdd/
  task-2-report.md` était déjà indexé (staged) par un travail antérieur sans
  rapport avec ce Task, avant que je ne lance `git add scripts/install.sh &&
  git commit`. Le commit a englobé ce fichier par erreur (index déjà
  pollué au démarrage de ma session). Corrigé immédiatement après coup en
  restaurant le contenu pré-commit de ce fichier dans l'arbre de travail
  (`git show df7ad40:… > task-2-report.md`), qui redevient une modification
  non indexée identique à l'état d'avant ce Task — je ne l'ai pas commitée
  (pas mon fichier, hors périmètre). Le commit `1b3d7b2` en conserve la trace
  dans son diff historique (2 fichiers listés), mais son effet net réel sur
  l'état actuel du dépôt ne porte que le changement voulu sur
  `scripts/install.sh` (`git diff scripts/install.sh` contre HEAD est vide,
  le fichier committé correspond exactement à l'implémentation décrite ici).

## Suite globale de non-régression (Step 3)

```
$ cd core && uv run pytest
====================== 775 passed, 102 skipped in 46.17s =======================

$ uv run lint-imports
layered architecture KEPT
Contracts: 1 kept, 0 broken.

$ cd ../shell && npm test
 Test Files  87 passed (87)
      Tests  594 passed (594)

$ npm run build
✓ built in 11.42s
```
Tout vert — cette tâche ne touche aucun code applicatif.

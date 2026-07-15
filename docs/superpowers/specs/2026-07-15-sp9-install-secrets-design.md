# SP-9 — Install & secrets : design

> Sous-partie de SP-9 (Durcissement produit public v0.1). Brainstormée le
> 2026-07-15, en même temps que le reste de SP-9 — planifiable et exécutable
> indépendamment, comme `2026-07-13-sp9-gestion-collections-design.md`.

## 1. Contexte et objectif

**Constat, vérifié en lisant `docker-compose.yml`, `.env.example`,
`README.md` et `core/scripts/seed_demo.py` intégralement :**
- Le realm Keycloak **est déjà** auto-provisionné (`command: start-dev
  --import-realm` + volume montant `deploy/keycloak/geostudio-realm.json`) —
  rien à faire ici, contrairement à ce que la formulation de la roadmap
  pourrait laisser penser.
- `.env.example` documente déjà toutes les variables nécessaires, mais avec
  des **valeurs par défaut faibles et devinables**
  (`PG_PASSWORD=ChangezMoiImmediatement!`, `MINIO_PASSWORD=
  MinioSecret_ChangezMoi123`, `KC_PASSWORD=KeycloakAdmin_ChangezMoi!`) — un
  `cp .env.example .env` sans intervention (l'installateur pressé, le cas
  qu'on doit couvrir pour un produit public) démarre une stack avec des mots
  de passe publiés en clair dans le dépôt.
- **Gap réel découvert en lisant `docker-compose.yml`** : le service `core`
  ne lance jamais `alembic upgrade head` — seul le service `worker` applique
  son propre schéma procrastinate (`schema --apply`). Le README documente
  aujourd'hui la migration comme une **étape manuelle séparée** (§"Vérifier
  le mode oidc") : sans elle, `GET /me` échoue silencieusement en base
  Postgres neuve (les tables `tenants`/`users` n'existent pas). Un
  `docker compose up -d` seul, aujourd'hui, ne produit **pas** une
  installation utilisable.
- `core/scripts/seed_demo.py` existe déjà et est idempotent (`Usage :
  DATABASE_URL=… uv run python -m scripts.seed_demo [--owner alice]`) —
  enregistre les tables `incidents`/`points_interet` (déjà créées par
  `sql/init.sql` au premier démarrage de Postgres) comme collections. Il
  n'est référencé nulle part dans un guide d'install pas-à-pas (seulement
  dans `CLAUDE.md` et des specs internes).

**Objectif.** `docker compose up -d` (après un unique script de bootstrap
générant des secrets forts) produit, sans étape manuelle oubliable, une
installation fonctionnelle où `GET /me` répond correctement — et un guide
documente la commande, elle aussi facultative mais explicite, pour peupler
les données de démo.

## 2. Périmètre

**Dans le périmètre v1 :**
- `scripts/bootstrap-env.sh` (nouveau, racine) : si `.env` n'existe pas,
  copie `.env.example` puis remplace `PG_PASSWORD`, `MINIO_PASSWORD`,
  `KC_PASSWORD`, `MARTIN_SECRET` par des valeurs générées
  (`openssl rand -base64 32 | tr -dc 'A-Za-z0-9'`, alphanumériques pur pour
  éviter tout problème d'échappement dans un DSN Postgres — un mot de passe
  contenant `@`/`:`/`/` casserait le parsing de
  `postgresql+psycopg://gis:${PG_PASSWORD}@…`) ; si `.env` existe déjà, ne
  touche à rien et affiche un message (« `.env` existe déjà, rien à faire »)
  — jamais d'écrasement silencieux d'une config existante.
  `ACME_EMAIL`/`DOMAIN` restent à `.env.example` (pas des secrets, pas
  générables — un vrai email/domaine doit être saisi à la main) ;
  `CORE_AUTH_MODE`/`CORE_EMBEDDING_PROVIDER`/etc. restent à leurs défauts
  `mock`/`fake` (pas des secrets non plus).
- `core` (service compose) applique ses migrations **au démarrage du
  conteneur**, avant `uvicorn` — même patron que le `command:` déjà en place
  pour `worker` (`schema --apply && …`) :
  `command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8200"`.
  Idempotent par construction (Alembic ne réapplique jamais une révision déjà
  appliquée) — sûr à chaque redémarrage/redeploy, pas seulement au premier
  boot.
- `README.md`, section « Démarrage rapide » réécrite : `cp .env.example .env`
  remplacé par `./scripts/bootstrap-env.sh`, ajout d'une étape optionnelle
  « peupler les données de démo »
  (`docker compose exec core uv run python -m scripts.seed_demo`, ou
  invocation équivalente documentée en vérifiant la bonne commande depuis un
  conteneur `core` réel — les dépendances `uv`/le venv existent déjà dans
  l'image, cf. `core/Dockerfile`).
- Correction de la dérive documentaire déjà repérée en explorant le repo :
  le README dit encore « 13 specs E2E » (`§Vérifier le mode oidc`), le vrai
  chiffre actuel est 34 — corrigé au passage (mineur, mais faux aujourd'hui).

**Hors périmètre v1 (explicitement différé) :**
- Rotation/gestion de secrets en production (Vault, Docker secrets) — hors
  échelle d'un `docker compose` mono-hôte, pas demandé par la roadmap v0.1.
- Auto-seed au démarrage du compose (`seed_demo.py` appelé automatiquement
  par un service) : **décision** — reste une commande manuelle documentée,
  pas un service compose ni un hook au démarrage de `core`. Un vrai
  déploiement (pas une démo) ne doit jamais voir apparaître des collections
  de données fictives sans l'avoir demandé explicitement ; seule la sous-partie
  « démo lecture seule » (spec séparée) a besoin d'un seed garanti, et elle
  le fait explicitement dans son propre flux, pas ici.
- Rendre `MARTIN_SECRET` réellement utilisé (aujourd'hui présent dans
  `.env.example` — vérifier en tâche s'il est déjà branché dans
  `martin-config.yaml`/le service `martin`, hors scope de savoir ici, mais
  bootstrap-env.sh le génère fort dans tous les cas par cohérence).

## 3. Architecture

### 3.1 `scripts/bootstrap-env.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail
if [ -f .env ]; then
  echo ".env existe déjà — rien à faire. Supprimez-le pour regénérer." >&2
  exit 0
fi
cp .env.example .env
gen() { openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 32; }
for var in PG_PASSWORD MINIO_PASSWORD KC_PASSWORD MARTIN_SECRET; do
  sed -i.bak "s|^${var}=.*|${var}=$(gen)|" .env
done
rm -f .env.bak
echo ".env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public."
```
(script indicatif du niveau de détail attendu — affiné en écrivant le plan ;
`sed -i.bak` portable macOS/Linux, cohérent avec le fait que ce dépôt cible
aussi des contributeurs macOS potentiels).

### 3.2 `docker-compose.yml`, service `core`

Ajout d'un `command:` explicite (aujourd'hui absent, hérité du `CMD` du
Dockerfile) qui enchaîne migration puis serveur — un seul changement, pas de
nouveau service, pas de conteneur d'init séparé (plus simple qu'un pattern
« init container », suffisant à cette échelle).

### 3.3 README

Nouvelle séquence : `git clone` → `./scripts/bootstrap-env.sh` →
`docker compose up -d` → (`docker compose exec core uv run python -m
scripts.seed_demo`, optionnel) → tableau des URLs (inchangé). La section
« Vérifier le mode oidc » perd son étape 1 sur la migration manuelle
(devenue automatique) — simplifiée d'autant.

## 4. Flux et gestion d'erreurs

**Premier lancement (cas nominal) :** `bootstrap-env.sh` génère `.env` →
`docker compose up -d` → `core` attend `pgbouncer` (`depends_on`) → migre →
sert. Un `curl http://localhost:8200/me` (anonyme, mode mock) répond sans
erreur 500 liée à des tables absentes — c'est le test de fumée de cette
sous-partie.

**Relance après un premier lancement réussi :** `bootstrap-env.sh` détecte
`.env` existant, ne fait rien ; les migrations Alembic au démarrage de `core`
sont un no-op (déjà à `head`).

**Échec de migration** (ex. Postgres pas encore prêt malgré `depends_on`) :
comportement actuel d'Alembic (erreur de connexion, conteneur `core` en
`CrashLoopBackOff` côté compose) — acceptable, `depends_on` +
`condition: service_healthy` sur `postgis` (déjà en place pour `keycloak`,
à vérifier/aligner pour `core` en tâche) limite ce risque sans l'éliminer
totalement ; pas de logique de retry applicative à écrire, Docker redémarre
déjà le conteneur (`restart: unless-stopped`).

## 5. Tests

**Manuel / smoke test (pas de suite automatisée nouvelle — c'est de
l'infrastructure, testée en la faisant tourner réellement, comme
`sp9-ci-publique-release`) :**
- `rm -f .env && ./scripts/bootstrap-env.sh` produit un `.env` avec des
  valeurs différentes de `.env.example` pour les 4 secrets, identiques en
  structure (mêmes autres lignes inchangées) — vérifié par diff.
- Relancer le script sur un `.env` existant : sortie explicite, `.env`
  inchangé (checksum identique avant/après).
- `docker compose down -v && docker compose up -d` (stack propre, volume
  Postgres vide) suivi d'un `curl http://localhost:8200/me` : succès sans
  intervention manuelle (c'était l'échec constaté avant cette sous-partie).
- `docker compose exec core uv run python -m scripts.seed_demo` après le
  point précédent : les collections `incidents`/`points_interet`
  apparaissent dans `GET /collections` — preuve que la commande documentée
  fonctionne réellement depuis le conteneur packagé, pas seulement en dev
  local avec `uv` sur l'hôte.

## 6. Critères d'acceptation

- `git clone` + `./scripts/bootstrap-env.sh` + `docker compose up -d`,
  sans aucune autre étape manuelle, donne un `GET /me` fonctionnel.
- Aucun secret faible/devinable ne peut se retrouver dans un `.env` généré
  par le script.
- Le guide d'install documente la commande de seed de démo (facultative,
  explicite).
- `docker compose up -d` relancé sur un environnement déjà migré ne
  régresse ni ne duplique rien (idempotence vérifiée empiriquement).

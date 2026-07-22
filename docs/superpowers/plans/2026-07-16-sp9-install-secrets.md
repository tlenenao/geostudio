# SP-9 — Install & secrets : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `git clone` + `./scripts/bootstrap-env.sh` + `docker compose up -d`, sans aucune autre étape manuelle, produit une installation GeoStudio fonctionnelle (`GET /me` répond, pas de tables absentes) avec des secrets forts, jamais les valeurs faibles de `.env.example`.

**Architecture:** Un script bash générateur de `.env` (jamais d'écrasement silencieux) + le service `core` du compose qui applique ses migrations Alembic à chaque démarrage de conteneur (avant `uvicorn`, idempotent) + un README réécrit qui documente la nouvelle séquence et la commande de seed de démo.

**Tech Stack:** bash, Docker Compose, Alembic (déjà en place), `openssl` (génération de secrets).

## Global Constraints

- Secrets générés avec `openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 32` — alphanumérique pur (un `@`/`:`/`/` casserait le parsing du DSN Postgres `postgresql+psycopg://gis:${PG_PASSWORD}@…`).
- Ne jamais écraser un `.env` existant silencieusement — le script s'arrête avec un message si `.env` est déjà présent.
- Seules 4 variables sont générées : `PG_PASSWORD`, `MINIO_PASSWORD`, `KC_PASSWORD`, `MARTIN_SECRET`. `ACME_EMAIL`/`DOMAIN` (pas des secrets, à saisir à la main) et `CORE_AUTH_MODE`/`CORE_EMBEDDING_PROVIDER`/etc. (pas des secrets) restent aux valeurs de `.env.example`, inchangées.
- La migration automatique du service `core` doit être idempotente et sûre à chaque redémarrage/redeploy, pas seulement au premier boot (Alembic ne réapplique jamais une révision déjà appliquée — propriété déjà garantie par Alembic lui-même).
- Pas de nouvelle suite de tests automatisée : c'est de l'infrastructure, vérifiée en la faisant tourner réellement (même patron que `2026-07-16-sp9-ci-publique-release.md`).
- Hors périmètre (ne pas implémenter) : rotation/Vault/Docker secrets, auto-seed au démarrage d'un service compose, rendre `MARTIN_SECRET` réellement consommé par `martin`.
- Docs et messages en français (code/identifiants en anglais), conformément à `CLAUDE.md`.

---

### Task 1: `scripts/bootstrap-env.sh`

**Files:**
- Create: `scripts/bootstrap-env.sh` (exécutable, racine du dépôt — un nouveau dossier `scripts/` à la racine, distinct de `core/scripts/`)

**Interfaces:**
- Consumes: `.env.example` (racine du dépôt, déjà existant, inchangé par cette tâche).
- Produces: `./scripts/bootstrap-env.sh`, invocable depuis la racine du dépôt sans argument. Toujours un exit code `0` (cas génération et cas déjà-existant). Tâche 3 (README) documente cette invocation exacte.

- [ ] **Step 1: Écrire le script**

Créer `scripts/bootstrap-env.sh` :

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env existe déjà — rien à faire. Supprimez-le pour regénérer." >&2
  exit 0
fi

cp .env.example .env

gen() {
  openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | head -c 32
  echo
}

for var in PG_PASSWORD MINIO_PASSWORD KC_PASSWORD MARTIN_SECRET; do
  value="$(gen)"
  sed -i.bak "s|^${var}=.*|${var}=${value}|" .env
done
rm -f .env.bak

echo ".env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public."
```

Notes :
- `cd "$(dirname "$0")/.."` : rend le script invocable depuis n'importe quel répertoire courant (pas seulement la racine du dépôt), tout en opérant toujours sur le `.env`/`.env.example` de la racine.
- `sed -i.bak` (avec suffixe de sauvegarde) : portable macOS/Linux (le `-i` nu de GNU sed et celui de BSD sed sur macOS ont une syntaxe incompatible ; `-i.bak` fonctionne identiquement sur les deux) — le `.bak` est supprimé juste après.
- `gen()` ajoute un retour à la ligne (`echo`) après la valeur générée : nécessaire pour que la substitution `value="$(gen)"` capture proprement la sortie sans effet de bord sur `sed`.

- [ ] **Step 2: Rendre le script exécutable**

```bash
chmod +x scripts/bootstrap-env.sh
```

- [ ] **Step 3: Vérifier le cas nominal (génération fraîche)**

Depuis la racine du dépôt (vérifier au préalable qu'aucun `.env` n'existe déjà — sur ce dépôt à ce stade, il n'y en a pas, `.env` est gitignoré) :

```bash
rm -f .env
./scripts/bootstrap-env.sh
```

Expected stdout : `.env généré avec des secrets forts. Éditez ACME_EMAIL/DOMAIN si besoin d'un déploiement public.`
Expected exit code : `0`

```bash
diff .env.example .env
```

Expected : exactement 4 blocs de diff (un par variable générée — `PG_PASSWORD`, `MINIO_PASSWORD`, `KC_PASSWORD`, `MARTIN_SECRET`), chaque ligne générée alphanumérique de 32 caractères, toutes les autres lignes strictement identiques (vérifié en exécutant ce script réellement pendant l'écriture de ce plan — comportement confirmé).

- [ ] **Step 4: Vérifier le cas idempotent (`.env` déjà présent)**

```bash
cp .env .env.snapshot
./scripts/bootstrap-env.sh
```

Expected stdout (sur stderr) : `.env existe déjà — rien à faire. Supprimez-le pour regénérer.`
Expected exit code : `0`

```bash
diff .env .env.snapshot && echo IDENTIQUE
```

Expected : `IDENTIQUE` — aucune modification de `.env` au second passage.

- [ ] **Step 5: Nettoyer les artefacts de test**

```bash
rm -f .env .env.snapshot
```

(`.env` est gitignoré — cette étape est une hygiène de dépôt, pas une nécessité de sécurité ; la Task 3 régénérera son propre `.env` pour son test de bout en bout.)

- [ ] **Step 6: Commit**

```bash
git add scripts/bootstrap-env.sh
git commit -m "feat: script de bootstrap .env avec secrets forts générés"
```

---

### Task 2: migration automatique du service `core`

**Files:**
- Modify: `core/Dockerfile:19-22`
- Modify: `docker-compose.yml:105-106` (service `core`)

**Interfaces:**
- Consumes: rien de nouveau des tâches précédentes.
- Produces: l'image `core` contient désormais `/app/alembic/`, `/app/alembic.ini`, `/app/scripts/` (importable comme `scripts.seed_demo` via `python -m scripts.seed_demo` — consommé par Task 3, README) ; le service compose `core` exécute `alembic upgrade head` avant `uvicorn` à chaque démarrage/redémarrage de conteneur.

**Contexte vérifié en lisant le code (pas une supposition) :**
- `core/Dockerfile` ne copie aujourd'hui que `COPY app ./app` — ni `alembic/`, ni `alembic.ini`, ni `scripts/` ne sont présents dans l'image construite. Lancer `alembic upgrade head` dans le conteneur échouerait aujourd'hui (`alembic.ini` introuvable), et `python -m scripts.seed_demo` échouerait aussi (module absent) — les deux doivent être copiés.
- `core/alembic/env.py:22` lit `os.environ["DATABASE_URL"]`, déjà présent dans l'environnement du service `core` du compose (`postgresql+psycopg://gis:${PG_PASSWORD}@pgbouncer:6432/gis`) — aucune variable supplémentaire à ajouter.
- Le service `worker` (même image `./core`) invoque déjà `python -m procrastinate …` sans `uv run` (commentaire du compose : le script `procrastinate` du PATH ne met pas le cwd sur `sys.path`, seul `-m` le fait) — l'image n'est **pas** gérée en mode projet `uv` (le `Dockerfile` fait `uv pip install --system`, pas `uv sync`) : toute commande dans ce conteneur doit être un appel `python`/`alembic` direct, jamais `uv run …`. C'est pour ça que la commande de migration ci-dessous est `alembic upgrade head`, pas `uv run alembic upgrade head`.
- `core/.dockerignore` exclut `tests/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.venv/` — n'exclut ni `alembic/` ni `scripts/`, rien à ajuster là.
- `pgbouncer` a déjà `depends_on: postgis: condition: service_healthy` (docker-compose.yml:50-52) — le service `core` (qui dépend de `pgbouncer`) hérite donc transitivement d'un Postgres déjà prêt avant que `pgbouncer` lui-même démarre ; aucun changement de `depends_on` n'est nécessaire pour `core`. Un échec de migration malgré tout (ex. `pgbouncer` pas encore accepté de connexions) fait crasher le conteneur `core`, que `restart: unless-stopped` (déjà en place) relance — comportement accepté explicitement par la spec, aucune logique de retry applicative à écrire.

- [ ] **Step 1: Copier `alembic/`, `alembic.ini`, `scripts/` dans l'image**

Modifier `core/Dockerfile` — remplacer :

```dockerfile
COPY app ./app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

par :

```dockerfile
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

(`CMD` reste inchangé — c'est le fallback si le compose ne fournit pas de `command:` ; utilisé tel quel par tout `docker run` direct de cette image hors compose.)

- [ ] **Step 2: Construire l'image et vérifier la présence des fichiers copiés**

```bash
docker build -t geostudio-core-test ./core
docker run --rm geostudio-core-test sh -c "ls alembic.ini scripts/seed_demo.py app/main.py"
```

Expected : les trois chemins s'affichent sans erreur (`ls` réussit, exit code `0`) — preuve que les trois `COPY` ajoutés produisent bien les fichiers attendus au bon endroit (`/app`, le `WORKDIR` du Dockerfile).

- [ ] **Step 3: Enchaîner migration puis serveur dans le service `core` du compose**

Modifier `docker-compose.yml` — dans le service `core` (actuellement) :

```yaml
  core:
    build: ./core
    environment:
```

remplacer par :

```yaml
  core:
    build: ./core
    # Applique les migrations Alembic à chaque démarrage du conteneur, avant
    # de servir — idempotent (Alembic ne réapplique jamais une révision déjà
    # appliquée), même patron que le `command:` du service `worker` plus bas
    # (`schema --apply && …`). `alembic upgrade head`, pas `uv run alembic
    # upgrade head` : cette image n'est pas gérée en mode projet uv (cf.
    # commentaire du service `worker`).
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8200"
    environment:
```

- [ ] **Step 4: Valider la syntaxe du compose**

`docker compose config` a besoin d'un `.env` pour interpoler les variables
(`${PG_PASSWORD}`, etc.) — le générer avec le script de Task 1 (déjà commité,
no-op si un `.env` existe déjà), valider, puis nettoyer :

```bash
./scripts/bootstrap-env.sh
docker compose config >/dev/null && echo "compose config OK"
rm -f .env
```

Expected : `compose config OK` — confirme que le YAML modifié reste valide.

- [ ] **Step 5: Nettoyer l'image de test**

```bash
docker rmi geostudio-core-test
```

- [ ] **Step 6: Commit**

```bash
git add core/Dockerfile docker-compose.yml
git commit -m "fix(core): appliquer les migrations Alembic au démarrage du conteneur"
```

---

### Task 3: README — nouvelle séquence d'install + test de bout en bout

**Files:**
- Modify: `README.md` (section « Démarrage rapide (dev) », section « Vérifier le mode oidc réel »)

**Interfaces:**
- Consumes : `scripts/bootstrap-env.sh` (Task 1), migration automatique de `core` (Task 2), `core/scripts/seed_demo.py` (déjà existant, inchangé).
- Produces : rien consommé par une tâche suivante — c'est la tâche finale, qui valide aussi les deux précédentes en conditions réelles.

**Contexte vérifié en lisant le code (pas une supposition) :** `core/scripts/seed_demo.py:main()` lève `SystemExit("aucun admin : définir CORE_ADMIN_SUBS ou passer --owner")` si le tenant par défaut n'a encore aucun admin et qu'aucun `--owner` n'est passé (`core/scripts/seed_demo.py:_owner`). Sur une stack fraîchement démarrée (`docker compose down -v` puis `up -d`), **aucun utilisateur n'existe encore** — `GET /me` en mode `mock` ne crée `mockuser` (admin, `bootstrap_admin=True` inconditionnel en mode mock — `core/app/auth/dependency.py:46-56`) qu'à la **première requête authentifiée** (`Authorization: Bearer …`, n'importe quelle valeur en mode mock). Un `curl` anonyme vers `/me` (le test de fumée de la spec) ne suffit donc **pas** à amorcer un admin : il faut soit ouvrir le shell une fois (qui envoie un bearer mock automatiquement), soit un appel authentifié explicite, avant de lancer `seed_demo` — sans quoi la commande documentée échouerait sur une install vraiment neuve. Documenté explicitement ci-dessous pour ne pas reproduire ce piège dans le README.

- [ ] **Step 1: Réécrire la section « Démarrage rapide (dev) »**

Remplacer (README.md, section actuelle) :

```markdown
## Démarrage rapide (dev)

Prérequis : Docker 24+, Node 20+, [uv](https://docs.astral.sh/uv/) (Python).

```bash
cp .env.example .env       # renseigner les mots de passe
docker compose up -d       # stack complète
```

| Service | URL |
|---|---|
| Shell (front) | http://localhost:8300 |
| Cœur (API) | http://localhost:8200 |
| Martin (tuiles MVT) | http://localhost:3000 |
| Keycloak | http://localhost:8180 |
| MinIO console | http://localhost:9001 |
```

par :

```markdown
## Démarrage rapide (dev)

Prérequis : Docker 24+, Node 20+, [uv](https://docs.astral.sh/uv/) (Python).

```bash
./scripts/bootstrap-env.sh   # génère .env avec des secrets forts (no-op si .env existe déjà)
docker compose up -d         # stack complète — migrations du cœur appliquées automatiquement
```

| Service | URL |
|---|---|
| Shell (front) | http://localhost:8300 |
| Cœur (API) | http://localhost:8200 |
| Martin (tuiles MVT) | http://localhost:3000 |
| Keycloak | http://localhost:8180 |
| MinIO console | http://localhost:9001 |

Pour peupler des données de démo (collections `incidents`/`points_interet`,
publiques, éditables — utile pour explorer le catalogue et le builder sans
importer ses propres données) : ouvrir http://localhost:8300 une fois en
mode `mock` (par défaut — promeut automatiquement l'utilisateur `mockuser`
admin dès la première requête authentifiée), puis :

```bash
docker compose exec core python -m scripts.seed_demo
```

Commande idempotente — relançable sans effet si les collections existent déjà.
```

- [ ] **Step 2: Simplifier la section « Vérifier le mode oidc réel »**

Remplacer l'étape 1 actuelle :

```markdown
1. `docker compose up -d` (stack complète, y compris `keycloak` avec le realm
   `geostudio` importé automatiquement — voir `docker compose ps keycloak`
   pour confirmer `healthy`), puis appliquer les migrations du cœur :
   `cd core && DATABASE_URL=postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis uv run alembic upgrade head`.
   Sans cette étape, `GET /me` échoue même avec un token Keycloak valide —
   `get_current_user` écrit dans les tables `tenants`/`users`, absentes tant
   que les migrations n'ont pas tourné sur une base Postgres neuve
   (`init_db()` ne les crée qu'en SQLite, jamais en Postgres).
```

par :

```markdown
1. `docker compose up -d` (stack complète, y compris `keycloak` avec le realm
   `geostudio` importé automatiquement — voir `docker compose ps keycloak`
   pour confirmer `healthy` ; `core` applique ses migrations Alembic
   automatiquement à chaque démarrage de conteneur, aucune étape manuelle
   requise).
```

Les étapes 2 à 5 qui suivent restent inchangées (mêmes numéros).

- [ ] **Step 3: Corriger le nombre de specs E2E obsolète**

Remplacer, dans la même section :

```markdown
développement courant et pour les 13 specs E2E — aucun accès réseau à
```

par :

```markdown
développement courant et pour les 36 specs E2E — aucun accès réseau à
```

(36 tests Playwright dans 26 fichiers `shell/e2e/*.spec.ts` — vérifié avec `cd shell && npx playwright test --list` pendant l'écriture de ce plan ; c'est la même convention de comptage « specs E2E » = nombre de tests, pas de fichiers, déjà utilisée dans `CLAUDE.md`, ex. « 36/36 specs E2E ».)

- [ ] **Step 4: Test de bout en bout — installation vraiment neuve**

Depuis la racine du dépôt, sur une stack et un volume Postgres propres :

```bash
docker compose down -v
rm -f .env
./scripts/bootstrap-env.sh
docker compose up -d
```

Attendre que les services critiques soient prêts (`postgis`/`keycloak` ont un
healthcheck) :

```bash
docker compose ps postgis keycloak core
```

Expected : `postgis` et `keycloak` en `healthy`, `core` en `Up` (pas de
redémarrage en boucle — `docker compose logs core` ne doit montrer aucune
trace de `Traceback`/`CrashLoopBackOff`).

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8200/me
```

Expected : `401` (pas `500`) — la requête anonyme atteint bien
`get_or_create_default_tenant`, qui touche la table `tenants` ; un `500`
signifierait que les migrations n'ont pas tourné (test de fumée de la spec,
§4/§6).

```bash
curl -s -H 'Authorization: Bearer x' http://localhost:8200/me
```

Expected : `200`, corps JSON avec `"username":"mockuser"` et
`"isAdmin":true` — amorce l'admin nécessaire à `seed_demo` (mode mock,
n'importe quelle valeur de bearer token).

```bash
docker compose exec core python -m scripts.seed_demo
```

Expected stdout : `collections créées : ['incidents', 'points_interet']`
(les deux tables de démo créées par `sql/init.sql` au premier démarrage de
Postgres, enregistrées comme collections par ce run).

```bash
docker compose exec core python -m scripts.seed_demo
```

Relancée une seconde fois, expected stdout :
`collections créées : aucune (déjà en place)` — preuve d'idempotence.

Vérifier aussi l'idempotence de la migration elle-même sur un environnement
déjà migré (critère d'acceptation §6 de la spec) :

```bash
docker compose restart core
docker compose logs core --tail 30
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8200/me
```

Expected : les logs ne montrent aucune erreur Alembic (la migration est un
no-op, déjà à `head`), `uvicorn` redémarre normalement, et le `curl` renvoie
de nouveau `401` — aucune régression, aucune duplication.

```bash
docker compose down
```

(sans `-v` cette fois — pas d'obligation de détruire le volume après le
test ; laisser l'environnement de dev tel quel pour la suite de la session.)

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: nouvelle séquence d'install (bootstrap-env.sh, migrations auto, seed de démo)"
```

# SP-Deploy-a — Stack prod (dogfood) : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `docker-compose.prod.yml` — une surcouche du compose existant qui fait tourner GeoStudio en dogfood réel (images GHCR, tunnel sortant `tailscale funnel`, aucun port ouvert, TLS terminé au bord du tunnel), avec un nom d'hôte public (`GEOSTUDIO_PUBLIC_HOST`) qui irrigue Keycloak/cœur/shell/Traefik depuis une seule variable, et sans les 2 bloqueurs connus (`worker` en boucle, volume `pg-data` vierge cassé).

**Architecture:** Un fichier d'override compose appliqué par-dessus `docker-compose.yml` (`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`). Traefik reste le routeur interne unique (plus d'ACME/Let's Encrypt — le TLS est terminé par `tailscale funnel`, sidecar en `network_mode: service:traefik`) ; trois routes `Host(${GEOSTUDIO_PUBLIC_HOST})` : `/api`→cœur (inchangé), `/auth`→Keycloak (nouveau, `KC_HTTP_RELATIVE_PATH=/auth`), `/tiles`→Martin (nouveau, strip-prefix), catch-all→shell. Le realm Keycloak (fichier JSON statique importé au boot) est rendu par un `sed` d'entrée de conteneur substituant l'unique littéral `http://localhost:8300` par `https://${GEOSTUDIO_PUBLIC_HOST}` — pas de duplication de fichier. Le shell, construit une fois et poussé sur GHCR, ne peut plus recevoir sa config OIDC/API via les `ARG` de build (bloqueur d'architecture pour le critère « bascule d'hôte sans reconstruction ») : un script d'entrée nginx génère `env-config.js` par `envsubst` à **chaque démarrage de conteneur**, lu par `loadConfig()` en plus (et en priorité sur) les valeurs bakées au build.

**Tech Stack:** Docker Compose (override file), Traefik v3 (déjà en place), Keycloak 24 (`KC_HOSTNAME`/`KC_HTTP_RELATIVE_PATH`/`KC_PROXY_HEADERS`), `tailscale/tailscale` (image officielle, mode userspace), nginx (image `shell`, mécanisme `docker-entrypoint.d`), `defusedxml`/SQLAlchemy déjà en place côté cœur, Vitest/Playwright (shell), pytest (`@pytest.mark.postgis`, cœur).

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md`.
- **`GEOSTUDIO_PUBLIC_HOST` = source de vérité unique** (spec §3.1) : changer cette seule variable dans `.env` + redémarrer les services concernés doit suffire — jamais de reconstruction d'image, jamais d'édition d'un deuxième fichier. C'est le critère d'acceptation §7-4, testé réellement en Task 6.
- **Traefik en prod n'utilise plus ACME/Let's Encrypt** (spec §3.2) : le TLS est terminé au bord du tunnel (`tailscale funnel`), Traefik ne sert que du HTTP interne (`entrypoints.web`, port 80, jamais publié directement — atteint uniquement via le sidecar tunnel en `network_mode: service:traefik`).
- **Aucun port hôte publié en prod** (D4) : toute section `ports:` d'un service déjà présent dans `docker-compose.yml` doit être vidée (`ports: []`) dans l'override, sauf le service `tunnel` lui-même qui n'en publie aucun non plus (le funnel sort via le réseau Tailscale, pas via un port Docker).
- **Le `worker` (`schema --apply && worker`) NE DOIT PLUS boucler** (bloqueur 1, spec §3.4-1) : `apply_schema()` de procrastinate n'est pas idempotent (`CREATE TYPE` échoue au second appel) — `core/tests/conftest.py::pg_engine_with_procrastinate_schema` documente déjà ce fait et la garde `has_table()` qui le contourne ; le même patron doit remplacer `schema --apply` dans le `command:` du service `worker`.
- **Démarrage à froid sur volume `pg-data` vierge** (bloqueur 2, spec §3.4-2, critère §7-1) : vérifié réellement (`docker compose down -v` puis `up -d`), pas asséré — `core` applique déjà `alembic upgrade head` à chaque démarrage (SP-9-install), donc aucun nouveau code n'est attendu ici, seulement une vérification qui devient un garde-fou de non-régression documenté.
- **Ne pas construire** : inscription publique, HA/réplication/PITR, YunoHost/Coolify/CasaOS/boutons cloud/managé, code ETL SP-17 (spec §9) — hors périmètre de ce sous-plan comme des trois autres.
- **`titiler` reste hors périmètre de ce sous-plan** (pas de route Traefik/prod) — seul le chemin `/api` (cœur), `/auth` (Keycloak), `/tiles` (Martin, nécessaire au rendu carte) et catch-all (shell) sont routés publiquement ; l'imagerie raster via titiler peut être traitée dans un chantier dédié si un besoin réel émerge.
- **En-tête SPDX** `# SPDX-License-Identifier: Apache-2.0` en première ligne de tout nouveau fichier `core/app/**`, `core/scripts/**` et `core/tests/**` ; `// SPDX-License-Identifier: Apache-2.0` pour tout nouveau `shell/src/**`.
- **Commandes de test.** Core : `cd core && uv run pytest` (SQLite, always-run) ; tests `@pytest.mark.postgis` : `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest -m postgis` contre un PostGIS+pgvector réel. Shell : `cd shell && npm test` (Vitest) ; `npm run build` (tsc + vite). Lint imports : `cd core && uv run lint-imports`. Pas de nouvelle suite E2E Playwright pour ce sous-plan : c'est de l'infrastructure compose, vérifiée en la faisant tourner réellement (même patron que `2026-07-16-sp9-install-secrets.md`), sauf pour le fix `worker` (Task 1, testable en pytest) et le mécanisme de config runtime du shell (Task 4, testable en Vitest).
- **Docs et messages en français** (code/identifiants en anglais), conformément à `CLAUDE.md`.

---

### Task 1 : fixer la boucle de redémarrage du `worker` (bloqueur 1)

**Files:**
- Create: `core/scripts/ensure_procrastinate_schema.py`
- Create: `core/tests/test_ensure_procrastinate_schema.py`
- Modify: `docker-compose.yml:162-164` (service `worker`, base compose — ce fix bénéficie au dev comme au prod, pas seulement à `docker-compose.prod.yml`)

**Interfaces:**
- Consumes: `app.jobs.app` (module existant, inchangé) ; fixture `pg_engine` de `core/tests/conftest.py` (existante).
- Produces: `scripts.ensure_procrastinate_schema.schema_is_applied(conninfo: str) -> bool`, `scripts.ensure_procrastinate_schema.main() -> None` — invocable via `python -m scripts.ensure_procrastinate_schema` (lit `DATABASE_URL` dans l'environnement, même variable que le reste du service `worker`).

**Contexte vérifié en lisant le code :**
- `core/tests/conftest.py::pg_engine_with_procrastinate_schema` documente déjà exactement ce bug : *"`apply_schema()` n'est PAS idempotente — un second appel sur une base où le schéma existe déjà lève (`CREATE TYPE` échoue)"* — et le contourne avec une garde `sa_inspect(pg_engine).has_table("procrastinate_jobs")`. Ce script réutilise la même garde, en dehors de pytest.
- `core/scripts/__init__.py` existe déjà (le module `scripts` est importable via `-m`, patron déjà utilisé par `python -m scripts.seed_demo`, documenté dans `docs/superpowers/plans/2026-07-16-sp9-install-secrets.md`).
- `core/Dockerfile` copie déjà `COPY scripts ./scripts` (fait en SP-9-install) — **aucune modification du Dockerfile n'est nécessaire**, le nouveau script sera automatiquement présent dans l'image `core`/`worker` (même image, `build: ./core`).
- `core/app/jobs.py` définit `app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=_conninfo()), ...)` — le script ci-dessous n'importe **pas** `app.jobs.app` (ça déclencherait tout l'`import_paths` et l'enregistrement des tâches métier, inutile ici) ; il construit sa propre `procrastinate.App` minimale, seulement pour appeler `schema_manager.apply_schema()`, exactement comme le fait déjà `pg_engine_with_procrastinate_schema`.

- [ ] **Step 1: Écrire le test (rouge)**

Créer `core/tests/test_ensure_procrastinate_schema.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import os

import pytest

from scripts.ensure_procrastinate_schema import main, schema_is_applied


@pytest.mark.postgis
def test_running_main_twice_never_raises(pg_engine, monkeypatch):
    """Régression du bloqueur SP-Deploy §3.4-1 : avant ce fix, appeler
    `apply_schema()` une seconde fois sur une base où le schéma existe déjà
    levait (`CREATE TYPE` échoue), ce qui faisait boucler le service
    `worker` en redémarrage (`schema --apply && worker`, relancé en entier
    par `restart: unless-stopped` à chaque crash). `main()` doit être
    rejouable sans exception, quel que soit l'état de départ."""
    monkeypatch.setenv("DATABASE_URL", os.environ["CORE_TEST_DATABASE_URL"])

    main()
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    assert schema_is_applied(conninfo)

    main()  # deuxième appel — ne doit PAS lever


@pytest.mark.postgis
def test_schema_is_applied_reflects_real_state(pg_engine):
    conninfo = os.environ["CORE_TEST_DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    # pg_engine (session-scope) peut déjà avoir le schéma appliqué par un
    # autre test de la suite (pg_engine_with_procrastinate_schema) — on
    # vérifie seulement la cohérence du prédicat, pas un état "avant/après"
    # isolé (la base de test est partagée, comme pour cette fixture sœur).
    assert schema_is_applied(conninfo) in (True, False)
```

- [ ] **Step 2: Vérifier que le test échoue (module absent)**

```bash
cd core && uv run pytest tests/test_ensure_procrastinate_schema.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'scripts.ensure_procrastinate_schema'` (ou `ImportError` équivalent) — sans `CORE_TEST_DATABASE_URL`, les deux tests sont de toute façon skippés (`pg_engine` lève `pytest.skip`), mais l'échec de collection (import cassé) doit apparaître avant même le skip.

- [ ] **Step 3: Écrire l'implémentation**

Créer `core/scripts/ensure_procrastinate_schema.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Applique le schéma procrastinate (table `procrastinate_jobs` et
dépendances) une seule fois. `SchemaManager.apply_schema()` n'est PAS
idempotente (`CREATE TYPE` échoue au second appel sur une base où le schéma
existe déjà) — ce qui faisait boucler le service `worker` en redémarrage
sous `docker-compose.yml` (`schema --apply && worker`, relancé en entier
par `restart: unless-stopped` à chaque crash, cf. CLAUDE.md « suivis non
bloquants »). Ce script se substitue à `procrastinate schema --apply` dans
le `command:` du worker : il vérifie d'abord si le schéma est déjà là
(`has_table`) et ne rappelle `apply_schema()` que s'il est absent — même
garde que `core/tests/conftest.py::pg_engine_with_procrastinate_schema`."""
import os
import sys

import procrastinate
from sqlalchemy import create_engine
from sqlalchemy import inspect as sa_inspect


def schema_is_applied(conninfo: str) -> bool:
    engine = create_engine(conninfo)
    try:
        return sa_inspect(engine).has_table("procrastinate_jobs")
    finally:
        engine.dispose()


def main() -> None:
    database_url = os.environ["DATABASE_URL"].replace(
        "postgresql+psycopg://", "postgresql://"
    )
    if schema_is_applied(database_url):
        print("procrastinate: schéma déjà appliqué, rien à faire.")
        return
    app = procrastinate.App(
        connector=procrastinate.PsycopgConnector(conninfo=database_url)
    )
    with app.open():
        app.schema_manager.apply_schema()
    print("procrastinate: schéma appliqué.")


if __name__ == "__main__":
    main()
    sys.exit(0)
```

- [ ] **Step 4: Lancer les tests (nécessite un vrai PostGIS)**

```bash
cd core && CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5432/gis \
  uv run pytest tests/test_ensure_procrastinate_schema.py -v -m postgis
```

Expected: `2 passed`. Si aucun PostGIS n'est disponible localement, démarrer temporairement celui du compose (`docker compose up -d postgis`, DSN `postgresql+psycopg://gis:${PG_PASSWORD}@localhost:5432/gis` — le port `5432` n'est pas publié par défaut dans `docker-compose.yml` : ajouter ponctuellement `docker compose exec postgis psql ...` ou publier le port le temps du test, puis le retirer — ne pas laisser un `ports:` supplémentaire trainer dans le compose commité).

- [ ] **Step 5: Suite complète + lint (non-régression)**

```bash
cd core && uv run pytest && uv run lint-imports
```

Expected: tous verts (nouveau fichier `core/scripts/ensure_procrastinate_schema.py` n'importe que `procrastinate`/`sqlalchemy`, des libs tierces hors contrat de frontières — `lint-imports` reste 1 kept / 0 broken).

- [ ] **Step 6: Brancher le script dans le `command:` du service `worker`**

Modifier `docker-compose.yml` — remplacer :

```yaml
    command: >
      sh -c "python -m procrastinate --app app.jobs.app schema --apply &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc"
```

par :

```yaml
    command: >
      sh -c "python -m scripts.ensure_procrastinate_schema &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc"
```

- [ ] **Step 7: Valider la syntaxe du compose**

```bash
./scripts/bootstrap-env.sh
docker compose config >/dev/null && echo "compose config OK"
rm -f .env
```

- [ ] **Step 8: Vérifier réellement l'absence de boucle (bout-en-bout)**

```bash
docker compose up -d postgis pgbouncer minio
docker compose up -d worker
sleep 5
docker compose ps worker
```

Expected: `worker` en `Up` (pas de colonne `Restarting`).

```bash
docker compose restart worker
sleep 5
docker compose logs worker --tail 20
docker compose ps worker
```

Expected : aucune trace `Traceback`/`DuplicateObject`/`CREATE TYPE` dans les logs, `worker` de nouveau `Up` — preuve que le second passage (schéma déjà appliqué) ne relève plus l'erreur qui causait la boucle.

```bash
docker compose down
```

- [ ] **Step 9: Commit**

```bash
git add core/scripts/ensure_procrastinate_schema.py core/tests/test_ensure_procrastinate_schema.py docker-compose.yml
git commit -m "fix(core): worker — schéma procrastinate idempotent (fin de la boucle de redémarrage)"
```

---

### Task 2 : `docker-compose.prod.yml` — squelette (images GHCR, restart, Traefik sans ACME)

**Files:**
- Create: `docker-compose.prod.yml`
- Modify: `.env.example` (nouvelle section « Déploiement prod »)

**Interfaces:**
- Consumes: `docker-compose.yml` (base, inchangé par cette tâche) ; images `ghcr.io/tlenenao/geostudio-{core,shell,postgis}` déjà publiées par `.github/workflows/release.yml` sur tag `vX.Y.Z`.
- Produces: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` valide ; variable `GEOSTUDIO_VERSION` (défaut `latest`) pilotant le tag des 3 images ; base pour les Tasks 3/5 qui étendent ce même fichier.

**Contexte vérifié en lisant le code :**
- Seuls `core`, `shell`, `postgis` sont construits/poussés par `release.yml` (matrice `build-and-push`) — `pgbouncer`/`minio`/`martin`/`titiler`/`keycloak` restent les images upstream déjà épinglées dans `docker-compose.yml`, **inchangées** par cet override.
- `docker-compose.yml` service `traefik` (fin de fichier) a pour `command:` : `--providers.docker=true`, `--providers.docker.exposedbydefault=false`, `--entrypoints.web.address=:80`, `--entrypoints.websecure.address=:443`, 3 lignes `--certificatesresolvers.letsencrypt...`, et `ports: ["80:80", "443:443"]`, `volumes: [.../docker.sock:ro, ./certs:/certs]` — `command`/`ports`/`volumes` sont des champs **liste** : un override qui les redéfinit les **remplace entièrement** (pas de fusion), donc il faut réécrire la version prod complète ici, pas seulement la différence.
- Tous les `labels:` Traefik des services `core`/`shell` (mêmes docker-compose.yml) sont aussi en forme liste — remplacés en entier dans la Task 3 (host + entrypoint changent tous les deux, sans quoi la fusion partielle laisserait `entrypoints=websecure` cohabiter avec une route `web`).

- [ ] **Step 1: Ajouter la section prod à `.env.example`**

Ajouter à la fin de `.env.example` :

```bash
# ─── Déploiement prod (SP-Deploy, docker-compose.prod.yml) ────
# Nom d'hôte public unique — source de vérité pour Keycloak (issuer,
# redirect_uri), le cœur (OIDC), le shell (API/tuiles) et Traefik (routage).
# Changer cette seule ligne + redémarrer les services concernés (jamais de
# `docker compose build`) suffit pour basculer d'un hôte à l'autre — ex.
# `machine.tailnet.ts.net` → `geostudio.tondomaine.fr`.
GEOSTUDIO_PUBLIC_HOST=changez-moi.exemple.ts.net
# Tag des images ghcr.io/tlenenao/geostudio-{core,shell,postgis} à déployer.
GEOSTUDIO_VERSION=latest
```

- [ ] **Step 2: Créer `docker-compose.prod.yml` — squelette Traefik + images + restart**

Créer `docker-compose.prod.yml` :

```yaml
# Surcouche prod (SP-Deploy) — appliquée par-dessus docker-compose.yml :
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# Différences avec le compose de dev : images depuis GHCR (au lieu de
# `build:`), tunnel sortant (aucun port hôte publié), Traefik sans ACME (le
# TLS est terminé au bord du tunnel — cf. service `tunnel`, Task 5), nom
# d'hôte public unique `GEOSTUDIO_PUBLIC_HOST` (cf. Task 3).
services:

  postgis:
    restart: unless-stopped

  pgbouncer:
    restart: unless-stopped

  minio:
    restart: unless-stopped
    ports: []

  martin:
    restart: unless-stopped
    ports: []

  titiler:
    restart: unless-stopped
    ports: []

  keycloak:
    restart: unless-stopped
    ports: []

  core:
    image: ghcr.io/tlenenao/geostudio-core:${GEOSTUDIO_VERSION:-latest}
    ports: []

  # worker/cdc-worker sont la MÊME image que core (docker-compose.yml:
  # `build: ./core` pour les trois, processus séparés par `command:`) —
  # release.yml ne construit que core/shell/postgis (matrice
  # build-and-push), donc ces deux services réutilisent geostudio-core.
  worker:
    image: ghcr.io/tlenenao/geostudio-core:${GEOSTUDIO_VERSION:-latest}

  cdc-worker:
    image: ghcr.io/tlenenao/geostudio-core:${GEOSTUDIO_VERSION:-latest}

  shell:
    image: ghcr.io/tlenenao/geostudio-shell:${GEOSTUDIO_VERSION:-latest}
    ports: []

  traefik:
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
    ports: []
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

Notes :
- `worker`/`cdc-worker` pointent vers `geostudio-core` (pas des images dédiées) : le `command:` de chacun, déjà défini dans `docker-compose.yml`, reste hérité tel quel, l'override ne touchant que `image:`.
- `traefik` perd son entrypoint `websecure` et ses 3 flags `--certificatesresolvers.letsencrypt...` : plus d'ACME en prod (TLS terminé par le tunnel, Task 5) — et perd le volume `./certs:/certs` (plus utile sans ACME).
- Tous les `ports: []` : aucun port hôte publié — seul le sidecar `tunnel` (Task 5) rendra la stack joignable depuis l'extérieur.

- [ ] **Step 3: Valider la syntaxe (sans `GEOSTUDIO_PUBLIC_HOST` défini pour l'instant — Task 3 l'introduit)**

```bash
./scripts/bootstrap-env.sh
echo "GEOSTUDIO_PUBLIC_HOST=test.ts.net" >> .env
echo "GEOSTUDIO_VERSION=latest" >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "compose prod OK"
rm -f .env
```

Expected: `compose prod OK`. (`GEOSTUDIO_PUBLIC_HOST` n'est encore utilisée nulle part dans ce fichier — la Task 3 l'introduit dans les `environment:`/`labels:` — cette étape ne valide donc que la syntaxe YAML + le remplacement des images/ports/command, pas encore l'interpolation de la variable.)

- [ ] **Step 4: Commit**

```bash
git add docker-compose.prod.yml .env.example
git commit -m "feat(deploy): squelette docker-compose.prod.yml (images GHCR, Traefik sans ACME)"
```

---

### Task 3 : `GEOSTUDIO_PUBLIC_HOST` — source de vérité unique (Keycloak, cœur, shell, Traefik, Martin)

**Files:**
- Modify: `docker-compose.prod.yml` (services `keycloak`, `core`, `shell`, ajout `martin`)

**Interfaces:**
- Consumes: `deploy/keycloak/geostudio-realm.json` (existant, **non modifié** — un `sed` d'entrée de conteneur en fait une copie rendue, jamais le fichier source) ; `CORE_OIDC_ISSUER`/`CORE_OIDC_JWKS_URL`/`CORE_BASE_URL` (lus par `core/app/auth/dependency.py:43-45`, `core/app/main.py:42`, vérifiés en lisant le code).
- Produces: le service `shell` reçoit désormais des variables d'environnement `VITE_*` **au runtime du conteneur** (pas au build) — consommées par le mécanisme de Task 4, qui doit suivre immédiatement pour que ces valeurs aient un effet (sans Task 4, ces `environment:` sont sans effet : l'image GHCR a déjà ses `VITE_*` bakés au build par les `ARG` du Dockerfile).

**Contexte vérifié en lisant le code :**
- `deploy/keycloak/geostudio-realm.json:701-703` — le client `geostudio-shell` a `"redirectUris": ["http://localhost:8300/", "http://localhost:8300/*"]`. `grep -c "localhost:8300" deploy/keycloak/geostudio-realm.json` confirme **exactement 2 occurrences**, toutes les deux dans ce bloc — un `sed` global du littéral `http://localhost:8300` est donc sûr et n'affecte aucune autre valeur du fichier (les autres `rootUrl`/`baseUrl` utilisent le placeholder Keycloak natif `${authBaseUrl}`, non touché).
- L'image `quay.io/keycloak/keycloak:24.0` a pour `ENTRYPOINT` `["/opt/keycloak/bin/kc.sh"]` et `CMD` vide (vérifié avec `docker image inspect`) — `docker-compose.yml` ne fournit donc que les arguments de `kc.sh` via `command: start-dev --import-realm`. Pour intercaler un rendu `sed` avant le démarrage, il faut redéfinir `entrypoint:` en `["sh", "-c"]` (le `command:` devient alors le script shell complet, terminé par `exec kc.sh ...`).
- `/opt/keycloak/data` (dans l'image) est un répertoire **inscriptible** (le volume nommé `keycloak-data` y est déjà monté par `docker-compose.yml`) ; `/opt/keycloak/data/import/` n'existe pas par défaut (vérifié : `ls` échoue dessus dans un conteneur neuf) — il n'existe en dev que parce que `docker-compose.yml` y bind-monte directement le fichier JSON (Docker crée les répertoires parents d'un bind-mount de fichier). En prod, le fichier source est bind-monté à un **autre** chemin (`import-src/`, lecture seule) et le rendu `sed` écrit sa sortie dans `import/` (à créer via `mkdir -p`), sur le volume nommé — jamais d'écriture dans un bind-mount `:ro`.
- `sed` (GNU sed 4.8) est présent dans l'image Keycloak (vérifié : `docker run --entrypoint sh quay.io/keycloak/keycloak:24.0 -c "sed --version"`).
- Keycloak 24 : `KC_HOSTNAME` accepte une URL complète (`https://host`), `KC_HTTP_RELATIVE_PATH` doit commencer par `/`, `KC_PROXY_HEADERS=xforwarded` fait confiance aux en-têtes `X-Forwarded-*` que Traefik ajoute déjà par défaut en tant que reverse proxy Docker (doc officielle Keycloak « Using a reverse proxy », vérifiée le 2026-07-24).
- `core/app/auth/dependency.py:43` : `issuer = os.environ["CORE_OIDC_ISSUER"]` — doit correspondre **exactement** au claim `iss` émis par Keycloak, donc à `KC_HOSTNAME` + `KC_HTTP_RELATIVE_PATH` + `/realms/geostudio` = `https://${GEOSTUDIO_PUBLIC_HOST}/auth/realms/geostudio`.
- `core/app/auth/dependency.py:44-45` : `CORE_OIDC_JWKS_URL` a un repli sur `{issuer}/protocol/openid-connect/certs` si absent — mais ce repli résoudrait vers l'URL **publique**, un aller-retour inutile et fragile via le tunnel depuis l'intérieur du réseau Docker ; comme en dev, on le fixe explicitement à l'URL interne `http://keycloak:8080/auth/realms/geostudio/protocol/openid-connect/certs`.
- `shell/src/config.ts` (base, inchangé par cette tâche — Task 4 le modifie) attend `VITE_CORE_URL`/`VITE_OIDC_AUTHORITY`/`VITE_OIDC_CLIENT_ID`/`VITE_OIDC_REDIRECT_URI`/`VITE_AUTH_MODE`.
- `shell/src/config.ts` a aussi un champ `martinUrl` (`VITE_MARTIN_URL`, optionnel, `?? ""`) — nécessaire pour que MapLibre charge les tuiles vectorielles Martin depuis le navigateur (pas via le cœur) ; sans route Traefik publique vers Martin, la carte resterait cassée en prod bien que « hors périmètre explicite » de la liste §3.1 de la spec — ajouté ici par cohérence fonctionnelle minimale (même schéma `/prefix` que `/api`), `titiler` restant volontairement de côté (cf. Global Constraints).

- [ ] **Step 1: Route Traefik + config Keycloak dans `docker-compose.prod.yml`**

Remplacer le bloc `keycloak:` du fichier créé en Task 2 :

```yaml
  keycloak:
    restart: unless-stopped
    ports: []
```

par :

```yaml
  keycloak:
    restart: unless-stopped
    ports: []
    environment:
      GEOSTUDIO_PUBLIC_HOST: ${GEOSTUDIO_PUBLIC_HOST}
      KC_HOSTNAME: https://${GEOSTUDIO_PUBLIC_HOST}
      KC_HTTP_RELATIVE_PATH: /auth
      KC_PROXY_HEADERS: xforwarded
    entrypoint: ["sh", "-c"]
    command:
      - >
        mkdir -p /opt/keycloak/data/import &&
        sed 's#http://localhost:8300#https://'"$$GEOSTUDIO_PUBLIC_HOST"'#g'
        /opt/keycloak/data/import-src/geostudio-realm.json
        > /opt/keycloak/data/import/geostudio-realm.json &&
        exec /opt/keycloak/bin/kc.sh start --http-enabled=true --import-realm
    volumes:
      - ./deploy/keycloak/geostudio-realm.json:/opt/keycloak/data/import-src/geostudio-realm.json:ro
    labels:
      - traefik.enable=true
      - traefik.http.routers.keycloak.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/auth`)
      - traefik.http.routers.keycloak.entrypoints=web
      - traefik.http.routers.keycloak.priority=20
      - traefik.http.services.keycloak.loadbalancer.server.port=8080
```

Notes :
- `$$GEOSTUDIO_PUBLIC_HOST` (double `$`) dans le `command:` : Docker Compose interpole lui-même les `${...}` du YAML — `$$` échappe pour que ce soit le **shell du conteneur**, pas Compose, qui résolve la variable au moment où `sh -c` s'exécute (elle est déjà passée au conteneur via `environment: GEOSTUDIO_PUBLIC_HOST: ${GEOSTUDIO_PUBLIC_HOST}` ci-dessus — Compose, lui, l'interpole normalement avec un seul `$` puisqu'elle apparaît dans un bloc `environment:`, pas dans le `command:`).
- `priority=20` : supérieure à celle du cœur (`10`, PathPrefix `/api`) et de la future route Martin (à définir ci-dessous) pour que `/auth` soit matché avant tout fallback plus générique — comme `core`/`shell` le sont déjà l'un par rapport à l'autre dans `docker-compose.yml`.

- [ ] **Step 2: Route Traefik + config Martin**

Ajouter au fichier (nouveau bloc, Martin n'a pas encore de `labels:` en dev) :

```yaml
  martin:
    restart: unless-stopped
    ports: []
    labels:
      - traefik.enable=true
      - traefik.http.routers.martin.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/tiles`)
      - traefik.http.routers.martin.entrypoints=web
      - traefik.http.routers.martin.priority=15
      - traefik.http.routers.martin.middlewares=strip-tiles@docker
      - traefik.http.services.martin.loadbalancer.server.port=3000
      - traefik.http.middlewares.strip-tiles.stripprefix.prefixes=/tiles
```

(Remplace le bloc `martin:` déjà présent depuis la Task 2, qui n'avait que `restart:`/`ports: []`.)

- [ ] **Step 3: Config OIDC du cœur, remplacer le bloc `core:`**

```yaml
  core:
    image: ghcr.io/tlenenao/geostudio-core:${GEOSTUDIO_VERSION:-latest}
    ports: []
    environment:
      CORE_AUTH_MODE: oidc
      CORE_OIDC_ISSUER: https://${GEOSTUDIO_PUBLIC_HOST}/auth/realms/geostudio
      CORE_OIDC_JWKS_URL: http://keycloak:8080/auth/realms/geostudio/protocol/openid-connect/certs
      CORE_BASE_URL: https://${GEOSTUDIO_PUBLIC_HOST}/api
    labels:
      - traefik.enable=true
      - traefik.http.routers.core.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/api`)
      - traefik.http.routers.core.entrypoints=web
      - traefik.http.routers.core.priority=10
      - traefik.http.routers.core.middlewares=security-headers@docker,rate-limit@docker,strip-api@docker
      - traefik.http.services.core.loadbalancer.server.port=8200
      - traefik.http.middlewares.strip-api.stripprefix.prefixes=/api
      - traefik.http.middlewares.security-headers.headers.stsSeconds=31536000
      - traefik.http.middlewares.security-headers.headers.contentTypeNosniff=true
      - traefik.http.middlewares.security-headers.headers.frameDeny=true
      - traefik.http.middlewares.security-headers.headers.referrerPolicy=strict-origin-when-cross-origin
      - traefik.http.middlewares.rate-limit.ratelimit.average=100
      - traefik.http.middlewares.rate-limit.ratelimit.burst=200
```

(Labels recopiés en entier depuis `docker-compose.yml:137-151`, avec `Host(`${DOMAIN}`)`→`Host(`${GEOSTUDIO_PUBLIC_HOST}`)` et `entrypoints=websecure`+`tls.certresolver=letsencrypt` retirés — remplacement complet nécessaire, `labels:` étant liste-type.)

- [ ] **Step 4: Config runtime du shell, remplacer le bloc `shell:`**

```yaml
  shell:
    image: ghcr.io/tlenenao/geostudio-shell:${GEOSTUDIO_VERSION:-latest}
    ports: []
    environment:
      VITE_CORE_URL: https://${GEOSTUDIO_PUBLIC_HOST}/api
      VITE_MARTIN_URL: https://${GEOSTUDIO_PUBLIC_HOST}/tiles
      VITE_OIDC_AUTHORITY: https://${GEOSTUDIO_PUBLIC_HOST}/auth/realms/geostudio
      VITE_OIDC_CLIENT_ID: geostudio-shell
      VITE_OIDC_REDIRECT_URI: https://${GEOSTUDIO_PUBLIC_HOST}/
      VITE_AUTH_MODE: oidc
    labels:
      - traefik.enable=true
      - traefik.http.routers.shell.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`)
      - traefik.http.routers.shell.entrypoints=web
      - traefik.http.routers.shell.priority=1
      - traefik.http.routers.shell.middlewares=security-headers@docker,rate-limit@docker
      - traefik.http.services.shell.loadbalancer.server.port=8300
```

**Ces `environment:` sont sans effet tant que la Task 4 n'est pas faite** — le shell GHCR a ses `VITE_*` bakés au build par les `ARG` du `Dockerfile` ; documenté ici, résolu par la tâche suivante.

- [ ] **Step 5: Valider la syntaxe complète**

```bash
./scripts/bootstrap-env.sh
{ echo "GEOSTUDIO_PUBLIC_HOST=test.ts.net"; echo "GEOSTUDIO_VERSION=latest"; } >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml config \
  | grep -A2 "CORE_OIDC_ISSUER\|KC_HOSTNAME\|VITE_CORE_URL"
```

Expected : les trois valeurs affichent bien `test.ts.net` interpolé (`https://test.ts.net/auth/realms/geostudio`, etc.), pas de littéral `${GEOSTUDIO_PUBLIC_HOST}` restant.

```bash
rm -f .env
```

- [ ] **Step 6: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat(deploy): GEOSTUDIO_PUBLIC_HOST — source de vérité unique (Keycloak, cœur, shell, Martin, Traefik)"
```

---

### Task 4 : configuration runtime du shell (`env-config.js`) — bascule d'hôte sans reconstruction

**Files:**
- Create: `shell/env-config.template.js`
- Create: `shell/docker-entrypoint.d/40-render-runtime-config.sh`
- Modify: `shell/Dockerfile`
- Modify: `shell/index.html`
- Modify: `shell/src/config.ts`
- Modify: `shell/src/config.test.ts`
- Modify: `shell/src/App.tsx:12`

**Interfaces:**
- Consumes: rien de nouveau des tâches précédentes côté code (les `environment:` de Task 3 sur le service `shell`).
- Produces: `loadConfig(env, runtimeEnv?) -> AppConfig` (nouveau second paramètre optionnel) — signature étendue, tout appelant existant (`App.tsx`) doit être mis à jour dans la même tâche.

**Contexte vérifié en lisant le code :**
- `shell/src/App.tsx:12` : `const config = loadConfig(import.meta.env as unknown as Record<string, string | undefined>);` — **seul** appelant de `loadConfig` hors tests (`grep -rn "loadConfig(" shell/src` confirmé).
- `shell/Dockerfile` bake les 4 `VITE_*` OIDC/API en `ARG`/`ENV` **au build** (`RUN npm run build` les lit via `import.meta.env`, Vite les inline dans le bundle JS) — c'est irréversible après coup sans ce mécanisme : une image GHCR construite une fois ne peut jamais changer d'hôte public sans rebuild, ce que le critère d'acceptation §7-4 de la spec interdit explicitement.
- `nginx:1.27-alpine` (image finale du `Dockerfile` shell) exécute automatiquement, avant de démarrer nginx, tout script exécutable placé dans `/docker-entrypoint.d/*.sh` (mécanisme du point d'entrée officiel de l'image, vérifié : `docker run --entrypoint sh nginx:1.27-alpine -c "ls /docker-entrypoint.d/"` liste déjà 4 scripts `.sh`/`.envsh` numérotés, exécutés dans l'ordre alphabétique) — et fournit `envsubst` (`gettext-runtime`, vérifié `which envsubst` dans l'image).
- `shell/nginx.conf` sert `root /usr/share/nginx/html` — un fichier `env-config.js` déposé là est donc servi tel quel à `/env-config.js`.

- [ ] **Step 1: Écrire le test (rouge) — `loadConfig` avec override runtime**

Modifier `shell/src/config.test.ts`, ajouter à la fin du fichier :

```ts
test("runtime env overrides build-time env when present and substituted", () => {
  const cfg = loadConfig(base, {
    VITE_CORE_URL: "https://prod.example",
    VITE_OIDC_AUTHORITY: "https://prod.example/auth/realms/geostudio",
  });
  expect(cfg.coreUrl).toBe("https://prod.example");
  expect(cfg.oidcAuthority).toBe("https://prod.example/auth/realms/geostudio");
  // Non fourni par le runtime env : repli sur la valeur build-time.
  expect(cfg.oidcClientId).toBe("shell");
});

test("runtime env with un-substituted envsubst placeholder falls back to build-time", () => {
  const cfg = loadConfig(base, { VITE_CORE_URL: "${VITE_CORE_URL}" });
  expect(cfg.coreUrl).toBe("https://core.test");
});

test("absent runtime env behaves exactly like before (undefined second arg)", () => {
  const cfg = loadConfig(base);
  expect(cfg.coreUrl).toBe("https://core.test");
});
```

- [ ] **Step 2: Vérifier que le test échoue**

```bash
cd shell && npm test -- config.test.ts 2>&1 | tail -20
```

Expected: échec TypeScript/runtime — `loadConfig` n'accepte encore qu'un seul paramètre (le second argument des deux premiers nouveaux tests est simplement ignoré aujourd'hui, donc `cfg.coreUrl` vaudrait `"https://core.test"` au lieu de `"https://prod.example"` attendu — le premier nouveau test échoue sur l'assertion, pas sur une erreur de compilation).

- [ ] **Step 3: Étendre `loadConfig`**

Remplacer tout `shell/src/config.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
export type AppConfig = {
  coreUrl: string;
  martinUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  authMode: "oidc" | "mock";
};

function mergeRuntimeEnv(
  env: Record<string, string | undefined>,
  runtimeEnv: Record<string, string | undefined> | undefined,
): Record<string, string | undefined> {
  if (!runtimeEnv) return env;
  const merged = { ...env };
  for (const [key, value] of Object.entries(runtimeEnv)) {
    // envsubst laisse "${VAR}" tel quel quand VAR n'était pas définie au
    // démarrage du conteneur (ou en dev, où /env-config.js n'existe pas et
    // ce paramètre vaut undefined de toute façon) — ne jamais laisser un
    // placeholder non substitué écraser une vraie valeur de build.
    if (value !== undefined && !value.startsWith("${")) {
      merged[key] = value;
    }
  }
  return merged;
}

export function loadConfig(
  env: Record<string, string | undefined>,
  runtimeEnv?: Record<string, string | undefined>,
): AppConfig {
  const merged = mergeRuntimeEnv(env, runtimeEnv);
  const authMode = merged.VITE_AUTH_MODE === "mock" ? "mock" : "oidc";

  const required: Record<string, string | undefined> = {
    VITE_CORE_URL: merged.VITE_CORE_URL,
  };
  if (authMode === "oidc") {
    required.VITE_OIDC_AUTHORITY = merged.VITE_OIDC_AUTHORITY;
    required.VITE_OIDC_CLIENT_ID = merged.VITE_OIDC_CLIENT_ID;
    required.VITE_OIDC_REDIRECT_URI = merged.VITE_OIDC_REDIRECT_URI;
  }

  const missing = Object.entries(required)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}`);
  }

  return {
    coreUrl: merged.VITE_CORE_URL!,
    martinUrl: merged.VITE_MARTIN_URL ?? "",
    oidcAuthority: merged.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: merged.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: merged.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}
```

- [ ] **Step 4: Lancer les tests (vert)**

```bash
cd shell && npm test -- config.test.ts
```

Expected: tous les tests passent, y compris les 3 anciens (signature rétrocompatible, second paramètre optionnel).

- [ ] **Step 5: Brancher le runtime env dans `App.tsx`**

Modifier `shell/src/App.tsx:12`, remplacer :

```ts
const config = loadConfig(import.meta.env as unknown as Record<string, string | undefined>);
```

par :

```ts
const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
```

- [ ] **Step 6: Template `env-config.js`**

Créer `shell/env-config.template.js` :

```js
window.__GEOSTUDIO_ENV__ = {
  VITE_CORE_URL: "${VITE_CORE_URL}",
  VITE_MARTIN_URL: "${VITE_MARTIN_URL}",
  VITE_OIDC_AUTHORITY: "${VITE_OIDC_AUTHORITY}",
  VITE_OIDC_CLIENT_ID: "${VITE_OIDC_CLIENT_ID}",
  VITE_OIDC_REDIRECT_URI: "${VITE_OIDC_REDIRECT_URI}",
  VITE_AUTH_MODE: "${VITE_AUTH_MODE}",
};
```

- [ ] **Step 7: Script d'entrée nginx**

Créer `shell/docker-entrypoint.d/40-render-runtime-config.sh` :

```sh
#!/bin/sh
set -eu
envsubst '${VITE_CORE_URL} ${VITE_MARTIN_URL} ${VITE_OIDC_AUTHORITY} ${VITE_OIDC_CLIENT_ID} ${VITE_OIDC_REDIRECT_URI} ${VITE_AUTH_MODE}' \
  < /usr/share/nginx/html/env-config.template.js \
  > /usr/share/nginx/html/env-config.js
```

(Liste explicite de variables passée à `envsubst` — même précaution que le script `20-envsubst-on-templates.sh` déjà présent dans l'image de base, pour ne substituer que ces 6 identifiants et ne jamais toucher un `${...}` accidentel ailleurs.)

```bash
chmod +x shell/docker-entrypoint.d/40-render-runtime-config.sh
```

- [ ] **Step 8: Charger `env-config.js` avant le bundle**

Modifier `shell/index.html`, remplacer :

```html
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
```

par :

```html
    <div id="root"></div>
    <script src="/env-config.js"></script>
    <script type="module" src="/src/main.tsx"></script>
```

(En dev — `vite dev`, Vitest, Playwright — `/env-config.js` n'existe pas : le navigateur ignore silencieusement l'échec de chargement du `<script>` non-module, `window.__GEOSTUDIO_ENV__` reste `undefined`, `loadConfig` se comporte exactement comme avant cette tâche.)

- [ ] **Step 9: Copier le template + le script dans l'image**

Modifier `shell/Dockerfile`, remplacer :

```dockerfile
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8300
```

par :

```dockerfile
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY env-config.template.js /usr/share/nginx/html/env-config.template.js
COPY docker-entrypoint.d/40-render-runtime-config.sh /docker-entrypoint.d/40-render-runtime-config.sh
EXPOSE 8300
```

(`chmod +x` déjà appliqué au fichier source en Step 7 — préservé par `COPY`, aucun `RUN chmod` supplémentaire nécessaire.)

- [ ] **Step 10: Construire et vérifier réellement le rendu**

```bash
docker build -t geostudio-shell-test ./shell
docker run --rm -e VITE_CORE_URL=https://demo.example/api \
  -e VITE_MARTIN_URL=https://demo.example/tiles \
  -e VITE_OIDC_AUTHORITY=https://demo.example/auth/realms/geostudio \
  -e VITE_OIDC_CLIENT_ID=geostudio-shell \
  -e VITE_OIDC_REDIRECT_URI=https://demo.example/ \
  -e VITE_AUTH_MODE=oidc \
  geostudio-shell-test sh -c "cat /usr/share/nginx/html/env-config.js" &
sleep 1 && docker stop $(docker ps -lq) >/dev/null 2>&1
```

Expected (dans les logs capturés avant l'arrêt) :

```js
window.__GEOSTUDIO_ENV__ = {
  VITE_CORE_URL: "https://demo.example/api",
  VITE_MARTIN_URL: "https://demo.example/tiles",
  VITE_OIDC_AUTHORITY: "https://demo.example/auth/realms/geostudio",
  VITE_OIDC_CLIENT_ID: "geostudio-shell",
  VITE_OIDC_REDIRECT_URI: "https://demo.example/",
  VITE_AUTH_MODE: "oidc",
};
```

(Plus simplement, sans arrière-plan : `docker run --rm -e VITE_CORE_URL=https://demo.example/api -e VITE_MARTIN_URL=x -e VITE_OIDC_AUTHORITY=x -e VITE_OIDC_CLIENT_ID=x -e VITE_OIDC_REDIRECT_URI=x -e VITE_AUTH_MODE=oidc --entrypoint sh geostudio-shell-test -c "/docker-entrypoint.d/40-render-runtime-config.sh && cat /usr/share/nginx/html/env-config.js"` — invoque le script directement sans lancer nginx, plus rapide à vérifier.)

```bash
docker rmi geostudio-shell-test
```

- [ ] **Step 11: Suite complète shell**

```bash
cd shell && npm test && npm run build
```

Expected: tous verts — `npm run build` confirme que `index.html`/`config.ts` modifiés restent valides TypeScript/Vite.

- [ ] **Step 12: Commit**

```bash
git add shell/env-config.template.js shell/docker-entrypoint.d/40-render-runtime-config.sh \
        shell/Dockerfile shell/index.html shell/src/config.ts shell/src/config.test.ts shell/src/App.tsx
git commit -m "feat(shell): configuration runtime (env-config.js) — bascule d'hôte sans reconstruction d'image"
```

---

### Task 5 : service `tunnel` (`tailscale funnel`)

**Files:**
- Modify: `docker-compose.prod.yml` (ajout service `tunnel`, ajustement `traefik`)
- Modify: `.env.example` (variable `TS_AUTHKEY`)

**Interfaces:**
- Consumes: `traefik` (service existant, `network_mode: service:traefik` partage son espace réseau — `127.0.0.1:80` depuis le conteneur `tunnel` atteint directement le port 80 de `traefik`).
- Produces: URL publique HTTPS `https://<TS_HOSTNAME>.<tailnet>.ts.net` (ou domaine propre une fois `tailscale funnel` reconfiguré côté compte Tailscale — hors périmètre code, D5 documenté comme piste de migration).

**Contexte vérifié (image officielle, documentation Tailscale consultée le 2026-07-24) :**
- Image `tailscale/tailscale` (image officielle) : `TS_AUTHKEY` (clé d'auth non-interactive du tailnet), `TS_STATE_DIR` (répertoire d'état — **doit persister** entre redémarrages, sans quoi le conteneur réapparaît comme un nouveau nœud à chaque `docker compose up`), `TS_HOSTNAME` (nom du nœud sur le tailnet). `TS_USERSPACE` vaut `true` par défaut (réseau en mode userspace, fonctionne partout, aucune capacité Linux ni périphérique `/dev/net/tun` requis) — suffisant ici car on ne fait que du reverse-proxy HTTP applicatif (`tailscale funnel <port>`), pas de routage réseau bas niveau.
- `tailscale funnel <port>` (forme de base documentée) proxifie le trafic Funnel public vers `http://127.0.0.1:<port>` — **un port local**, pas une URL `host:port` arbitraire. D'où `network_mode: service:traefik` sur le conteneur `tunnel` : il partage l'espace réseau de `traefik`, donc `127.0.0.1:80` **est** le port 80 de Traefik.
- Un service en `network_mode: service:X` ne peut pas définir ses propres `networks:`/`ports:` (hérités de `X`) — Compose lève une erreur de configuration si on essaie ; ne pas ajouter `networks: [gis-net]` ni `ports:` sur le service `tunnel`.

- [ ] **Step 1: Ajouter `TS_AUTHKEY` à `.env.example`**

Ajouter à la section « Déploiement prod » de `.env.example` (créée en Task 2) :

```bash
# Clé d'authentification Tailscale non-interactive (générée dans la console
# admin Tailscale, https://login.tailscale.com/admin/settings/keys — clé
# réutilisable, à courte durée de vie recommandée). Vide par défaut : le
# service `tunnel` ne démarre pas sans elle (voir installeur, SP-Deploy-c).
TS_AUTHKEY=
```

- [ ] **Step 2: Ajouter le service `tunnel` et ajuster `traefik`**

Ajouter à `docker-compose.prod.yml` (nouveau bloc, en toute fin de fichier) :

```yaml
  tunnel:
    image: tailscale/tailscale:latest
    restart: unless-stopped
    network_mode: service:traefik
    environment:
      TS_AUTHKEY: ${TS_AUTHKEY}
      TS_STATE_DIR: /var/lib/tailscale
      TS_HOSTNAME: geostudio
    volumes:
      - tailscale-state:/var/lib/tailscale
    depends_on:
      traefik:
        condition: service_started
```

Ajouter également, tout en haut du fichier (avant `services:`, section `volumes:` — `docker-compose.prod.yml` n'en a pas encore, `docker-compose.yml` en a une propre pour `pg-data`/`minio-data`/`keycloak-data` qui reste inchangée et se fusionne avec celle-ci) :

```yaml
volumes:
  tailscale-state:
```

- [ ] **Step 3: Activer `funnel` au premier démarrage**

`tailscale funnel` n'est pas déclenché automatiquement par les variables d'environnement ci-dessus (celles-ci ne font que joindre le tailnet, via `tailscale up` interne à l'image) — une seule commande, à lancer une fois après le premier démarrage du service (le nœud garde cette configuration tant que `TS_STATE_DIR` persiste, donc pas nécessaire à chaque redémarrage) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec tunnel tailscale funnel --bg 80
```

Documenté ici et repris tel quel par l'installeur (SP-Deploy-c, Task « Bootstrap & lancement ») — ne PAS l'automatiser dans le `command:` du service (idempotent en soi côté Tailscale, mais un service compose qui se termine après une commande one-shot n'est pas le patron `restart: unless-stopped` voulu ici : le conteneur doit rester vivant pour maintenir la connexion tailnet).

- [ ] **Step 4: Valider la syntaxe**

```bash
./scripts/bootstrap-env.sh
{ echo "GEOSTUDIO_PUBLIC_HOST=test.ts.net"; echo "GEOSTUDIO_VERSION=latest"; echo "TS_AUTHKEY=tskey-test-000"; } >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml config >/dev/null && echo "compose prod OK"
rm -f .env
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.prod.yml .env.example
git commit -m "feat(deploy): service tunnel (tailscale funnel) — accès public sans port ouvert"
```

---

### Task 6 : validation bout-en-bout (bloqueur 2 + critères d'acceptation §7-1 à §7-4)

**Files:** aucun (vérification pure — pas de nouveau code)

**Interfaces:** consomme l'ensemble des Tasks 1 à 5.

Cette tâche exécute réellement les critères §7 de la spec qui ne nécessitent pas encore le service `backup` (SP-Deploy-b) ni l'installeur (SP-Deploy-c). Elle requiert un vrai compte Tailscale (une clé `TS_AUTHKEY` valide) — si indisponible au moment de l'exécution, les Steps 1-3 (sans `tunnel`) restent exécutables en local via port-forward manuel (`docker compose port traefik 80` après avoir temporairement republié le port pour le seul test), documenté en note à chaque étape concernée.

- [ ] **Step 1: Démarrage à froid sur volume vierge (critère §7-1, bloqueur 2)**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v
./scripts/bootstrap-env.sh
{ echo "GEOSTUDIO_PUBLIC_HOST=localtest.me"; echo "GEOSTUDIO_VERSION=latest"; echo "TS_AUTHKEY="; } >> .env
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d postgis pgbouncer minio keycloak core shell martin traefik
sleep 15
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

Expected : `postgis`/`keycloak` `healthy`, `core`/`shell`/`martin`/`traefik` `Up` (pas de `Restarting`).

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec core \
  curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8200/me
```

Expected : `401` (pas `500`) — migrations Alembic appliquées avec succès sur volume `pg-data` vierge (confirme que le bloqueur 2 n'est **pas** reproductible sur un volume neuf avec le code actuel : `alembic upgrade head` tourne à chaque boot depuis SP-9-install).

- [ ] **Step 2: Survie au redémarrage (critère §7-2, bloqueur 1)**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart
sleep 15
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs worker --tail 20
```

Expected : tous les services `Up`, `worker` ne boucle pas (aucune trace `Traceback` dans ses logs — confirme Task 1 en conditions compose complètes, pas seulement isolé).

- [ ] **Step 3: Bascule d'hôte sans reconstruction (critère §7-4)**

```bash
sed -i.bak 's/^GEOSTUDIO_PUBLIC_HOST=.*/GEOSTUDIO_PUBLIC_HOST=nouveau-host.ts.net/' .env
rm -f .env.bak
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-build core keycloak shell
sleep 10
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec shell \
  sh -c "cat /usr/share/nginx/html/env-config.js | grep nouveau-host"
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec core \
  env | grep CORE_OIDC_ISSUER
```

Expected : `env-config.js` du shell contient `nouveau-host.ts.net` (rendu par le script d'entrée au (re)démarrage du conteneur, **sans** `docker compose build`), `CORE_OIDC_ISSUER` du cœur reflète le nouvel hôte — confirme que changer `GEOSTUDIO_PUBLIC_HOST` + redémarrer suffit, aucune image reconstruite (`--no-build` passé explicitement pour le prouver).

- [ ] **Step 4: OIDC bout-en-bout (critère §7-3) — si `TS_AUTHKEY` disponible**

Avec une vraie clé Tailscale renseignée dans `.env` et le service `tunnel` démarré (`docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d tunnel`, puis `tailscale funnel --bg 80` une fois, cf. Task 5 Step 3) : ouvrir `https://<TS_HOSTNAME>.<tailnet>.ts.net/` dans un navigateur, se connecter via Keycloak (créer un premier utilisateur admin dans la console Keycloak à `/auth/admin/` au besoin), écrire un item (ex. créer une carte depuis le builder), rafraîchir la page, confirmer que l'item est bien relu. Documenter le résultat dans le message de commit final de ce sous-plan (pas de test automatisé possible pour un flux OIDC humain réel).

- [ ] **Step 5: Non-régression (critère §7-7)**

```bash
cd core && uv run pytest && uv run lint-imports
cd ../shell && npm test && npm run build
docker compose -f docker-compose.yml -f docker-compose.prod.yml down
rm -f .env
```

Expected : tous verts — aucune suite existante cassée par ce sous-plan.

- [ ] **Step 6: Commit (documentation du résultat de validation)**

Si tout est vert, aucun code à committer ici (vérification pure) — reporter le résultat dans le message de fin de plan / PR. Si un écart est trouvé, ouvrir une Task corrective avant de considérer SP-Deploy-a terminé.

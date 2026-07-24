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


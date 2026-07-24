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


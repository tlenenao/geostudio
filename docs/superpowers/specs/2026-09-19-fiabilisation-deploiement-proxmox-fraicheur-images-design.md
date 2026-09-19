# Fiabilisation du déploiement Proxmox + fraîcheur des images publiées — design

## 0. Cadrage

Déclencheur : premier déploiement réel de GeoStudio sur le Proxmox du
mainteneur (2026-09-19, `deploy/proxmox/`), suivi bout en bout en session
interactive. C'est le tout premier déploiement réel sur cette cible depuis
que le module existe (SP-Deploy-e) — jamais rejoué depuis le correctif du
chemin de playbook partagé (2026-09-17, cf. `### Livré` CLAUDE.md,
« Provisioning OCI »). Neuf défauts réels trouvés, dont quatre déjà corrigés
et poussés sur `dev` en cours de session, cinq non corrigés à ce jour.

Ce document sépare deux familles :

1. **Bugs ponctuels de scripts/config** (§1) — chacun a une cause locale et
   un correctif local, indépendants les uns des autres.
2. **Un problème systémique** (§2) — les images publiées sous le tag
   `v0.1.0` sur `ghcr.io/tlenenao/geostudio-*` ne sont plus synchronisées
   avec le code source de `dev`/`main`, et rien ne le détecte. C'est la
   partie « faire en sorte que les packages soient toujours à jour et
   adapté » de la demande.

Hors périmètre de ce document : exécuter les correctifs de §2 (nécessite un
plan séparé, arbitrages produit à trancher d'abord, cf. §2.4) ; réparer la
2ᵉ NVMe/RAM du poste hôte (matériel, déjà traité en session, sans rapport
avec le dépôt) ; réécrire `deploy/keycloak/geostudio-realm.json` au-delà du
strict nécessaire pour fermer §1.6.

## 1. Bugs ponctuels — constat vérifié

### 1.1 — CORRIGÉ (`ee16a3de`) : `install.sh` vérifiait `/me` au lieu de `/v1/me`

SP-57b (déjà dans `### Livré`) a fait passer toutes les routes du cœur sous
`/v1/`. `scripts/install.sh::launch_stack()` sondait encore
`http://localhost:8200/me`, recevant un 404 permanent au lieu du 401 attendu
→ l'installeur échouait systématiquement à « Le cœur ne répond pas comme
attendu ». Corrigé : `http://localhost:8200/v1/me`.

### 1.2 — CORRIGÉ (`12eafe42`) : VM Proxmox provisionnée sans CPU hôte

`deploy/proxmox/terraform/main.tf` ne fixait pas `cpu.type` → Proxmox
retombe sur son défaut (`qemu64`, vérifié via `tofu plan` réel), qui
n'expose pas x86-64-v2 (SSE4.2/POPCNT). Keycloak et MinIO (images
`quay.io/keycloak/keycloak:24.0.5`, `quay.io/minio/minio:RELEASE.2025-…`)
l'exigent au démarrage et boucle-crashent (`Fatal glibc error: CPU does not
support x86-64-v2`). Corrigé : nouvelle variable `cpu_type` (défaut
`"host"`, acceptable ici — nœud Proxmox unique, pas de cluster/migration à
vif).

### 1.3 — CORRIGÉ (`3f17eb4b`) : Traefik v3.0.4 incompatible avec un Docker Engine récent

Le client Docker interne de `traefik:v3.0.4` (juillet 2024) demande l'API
`1.24`. Un Docker Engine installé aujourd'hui via `get.docker.com` (API
`1.56` vérifiée sur la VM) refuse tout client sous `1.40` (« client version
1.24 is too old ») — le provider Docker de Traefik échoue en boucle,
**aucun** routage par label ne fonctionne (pas seulement un service : tous).
Vérifié qu'aucun flag/variable d'environnement ne permet de forcer la
version demandée (`traefik --help-all` réel, pas de `apiVersion` documenté ;
`DOCKER_API_VERSION` positionné et ignoré en pratique). Corrigé par bump
vers `v3.7.13` (testé de bout en bout sur le déploiement réel : provider
Docker fonctionnel, `--providers.file`/ACME/entrypoints inchangés).

**Suivi non fermé** : aucun mécanisme n'empêche de reproduire ce type de
dérive pour `traefik` (ou toute autre image tierce dont l'API/le protocole
qu'elle consomme évolue chez le fournisseur amont) — cf. §2.

### 1.4 — CORRIGÉ (`b2b52e65`) : `KC_HOSTNAME` contenait un schéma `https://`

Vérifié contre `kc.sh start --help-all` réel (image
`quay.io/keycloak/keycloak:24.0.5`) : `--hostname`/`KC_HOSTNAME` attend un
nom d'hôte nu ; c'est `--hostname-url`/`KC_HOSTNAME_URL` qui veut
« scheme, host, port and path ». `docker-compose.prod.yml` positionnait
`KC_HOSTNAME: https://${GEOSTUDIO_PUBLIC_HOST}` → Keycloak reconstruisait
ses URLs frontend en préfixant un second `https://` par-dessus, cassant
toute redirection OIDC (`https://https//geostudio.tailc68a0c.ts.net/...`,
constaté en se connectant réellement). Corrigé : `KC_HOSTNAME:
${GEOSTUDIO_PUBLIC_HOST}` (le schéma HTTPS est déjà déduit via
`KC_PROXY_HEADERS=xforwarded`).

### 1.5 — NON CORRIGÉ : le realm Keycloak n'est importé qu'une seule fois, jamais réactualisé

`docker-compose.yml::keycloak` lance `start-dev --import-realm` ; Keycloak
n'importe un realm que s'il n'existe pas déjà en base (comportement par
défaut, vérifié empiriquement : après le premier import, une réexécution
avec un `geostudio-realm.json` différent ne change rien au realm vivant).
Or `docker-compose.prod.yml::keycloak::command` régénère ce fichier à
**chaque** lancement d'`install.sh` via un `sed` qui y injecte
`GEOSTUDIO_PUBLIC_HOST` — un mécanisme qui suppose implicitement un
réimport à chaque fois.

Constat concret : le tout premier import de cette session s'est produit
alors que `GEOSTUDIO_PUBLIC_HOST` était encore vide (une tentative
antérieure, avant la découverte Tailscale Funnel) → le client
`geostudio-shell` a été créé avec `redirectUris: ["https:///", "https:///*"]`
(hôte vide). Tous les correctifs suivants de `GEOSTUDIO_PUBLIC_HOST`
(§1.4, découverte Funnel) ont continué à produire un fichier d'import
correct — jamais consommé, puisque le realm existait déjà. Résultat en
clair : `Invalid parameter: redirect_uri` à chaque tentative de connexion,
corrigé en session par un `kcadm.sh update clients/<id> -s
redirectUris=[...]` **manuel, non reproductible**.

Ce défaut touchera **tout** changement futur de `GEOSTUDIO_PUBLIC_HOST`
(nouveau tailnet, domaine personnalisé, migration de machine) : silencieux,
aucun message d'erreur au moment du changement, seulement au moment de la
connexion suivante.

**Piste de correctif** (à trancher dans un plan séparé) : faire jouer à
`install.sh` un `kcadm.sh update` idempotent des `redirectUris`/`webOrigins`
du client `geostudio-shell` (et de tout autre champ dérivé de
`GEOSTUDIO_PUBLIC_HOST` dans le realm) à **chaque** lancement, après
authentification admin déjà en place (§ pattern existant,
`launch_stack()`), plutôt que de compter sur le réimport de fichier.

### 1.6 — NON CORRIGÉ : volume `csp-dynamic-conf` créé root, worker non-root ne peut pas y écrire

`app/security/jobs.py::refresh_csp_dynamic_conf_task` (worker, uid 1001,
cf. commentaire `core/Dockerfile` sur l'uid fixe SP-26) écrit
périodiquement (cron `*/5 * * * *`) dans le volume nommé
`csp-dynamic-conf`, partagé avec `traefik` (root) via
`--providers.file.directory=/csp-dynamic`. Le volume Docker nommé est
peuplé au premier conteneur qui l'utilise ; sur ce déploiement, c'est
`traefik` (root) qui l'a créé en premier → `PermissionError: [Errno 13]
Permission denied: '/csp-dynamic/dynamic-conf.yml'` à chaque exécution de
la tâche, constaté dans les logs `worker` réels. Corrigé en session par un
`chown -R 1001:1001` **manuel sur le point de montage hôte du volume**, non
reproductible et non porté par le dépôt.

Le résultat pratique sans ce correctif manuel : la CSP dynamique
(SP-48/GAP-72) ne se met jamais à jour après le tout premier calcul raté —
sur cette instance, elle n'existait simplement pas tant que le fichier
n'a pas été écrit à la main, et **Traefik refusait alors de charger
n'importe quel routeur `@docker`** (`middleware "csp-dynamic@file" does not
exist` — GAP sur tous les routeurs qui la référencent, pas seulement sur
la CSP elle-même).

**Piste de correctif** (à trancher) : soit fixer la propriété du volume à
la création via un pas d'installation (`install.sh` : un
`docker run --rm -v csp-dynamic-conf:/x busybox chown 1001:1001 /x` avant
le premier `up`, idempotent), soit garantir l'ordre de création
(`depends_on` ne suffit pas ici, ce n'est pas un ordre de démarrage mais un
ordre de première écriture sur un volume partagé), soit changer le modèle
(fichier généré dans un volume dédié au worker, monté en lecture seule côté
Traefik avec des permissions moins restrictives dès la création).

### 1.7 — NON CORRIGÉ : `core`/`worker` exportent vers un collecteur OTel absent

`docker-compose.yml` configure l'export OTLP HTTP inconditionnellement vers
`otel-lgtm` (profil compose `observability`, non démarré par défaut, ni sur
ce déploiement). Résultat constaté : `core` et `worker` retentent l'export
en boucle indéfiniment (`Failed to resolve 'otel-lgtm'`, plusieurs lignes
par minute), sans jamais abandonner. Pas fatal (n'empêche aucune requête
applicative de répondre) mais bruit de log permanent sur toute instance qui
n'active pas le profil `observability` — gêne réelle pour le diagnostic (a
noyé les vraies erreurs `404` du §2 pendant l'investigation de cette
session).

**Piste de correctif** : lire l'activation du profil `observability` dans
`install.sh` et ne positionner l'endpoint OTLP (`OTEL_EXPORTER_OTLP_ENDPOINT`
ou équivalent) que si le profil est réellement démarré ; sinon désactiver
l'export au lieu de le laisser retenter indéfiniment contre un hôte qui
n'existe pas.

## 2. Problème systémique — les images `v0.1.0` publiées divergent du code source

### 2.1 Constat vérifié

Trois images sur les neuf publiées se sont révélées **fonctionnellement
cassées** par rapport à l'état actuel de `dev`, alors que leur code source
correspondant contient déjà le correctif :

- **`geostudio-core:v0.1.0`** : plante au démarrage
  (`ModuleNotFoundError: No module named 'mcp.server.fastmcp'` — le SDK
  `mcp` installé dans l'image est en 2.x, où `FastMCP` a été renommé
  `MCPServer`), alors que `core/pyproject.toml` contient déjà
  `"mcp>=1.12,<2.0"` sur `dev`. Rebuild local depuis `./core` (le
  `Dockerfile` du dépôt, tel quel) → image saine, aucun autre changement.
- **`geostudio-titiler`** : le package **n'existe pas du tout** sur GHCR
  (confirmé par requête anonyme au registre — `404`, pas un problème de
  visibilité). `deploy/titiler/Dockerfile` a été ajouté par le portage
  arm64 (2026-09-15, postérieur à la release v0.1.0) et déclaré dans la
  matrice `release.yml`, mais aucune exécution de ce workflow depuis son
  ajout n'a construit+publié cette image.
- **`geostudio-shell:v0.1.0`** : le bundle JS appelle les routes **sans**
  préfixe `/v1/` (`GET /items`, `/me`, `/instance` → 404 constatés en
  conditions réelles, catalogue de l'app inutilisable après connexion),
  alors que `shell/src/api/base.ts:187` préfixe déjà systématiquement
  `${opts.coreUrl}/v1` sur `dev`. Même classe de bug que §1.1, mais figée
  dans un artefact binaire déjà publié — impossible à corriger par un
  simple redéploiement du realm ou de la config, il faut republier l'image.

Aucune vérification (CI ou manuelle) ne compare le contenu d'une image déjà
publiée sous un tag donné au commit source dont elle prétend provenir. Le
tag `v0.1.0` a donc dérivé en usages incohérents : `postgis` (rebuild
multi-arch de septembre, sain — vérifié par pull direct + usage réel dans
cette session), `core`/`shell` (jamais rebuild depuis la release initiale
de fin août, cassés par des changements ultérieurs de leurs dépendances/API
respectives), `titiler` (jamais construit du tout sous ce nom).

### 2.2 Cause racine

`v0.1.0` est traité comme un tag de release classique (censé être figé une
fois publié) mais le dépôt continue d'évoluer dessous sans jamais retaguer
ni republier systématiquement. Deux sous-causes distinctes :

1. **Dérive de dépendances non gelées** (`core`) : `pyproject.toml`/`uv.lock`
   évoluent sur `dev` après la release, mais l'image `v0.1.0` déjà publiée
   ne rebuild jamais — normal pour un tag figé, **sauf** que ce même tag
   sert aussi de cible « production actuelle » pour tout nouveau
   déploiement (`docker-compose.prod.yml` réclame `${GEOSTUDIO_VERSION:-latest}`,
   `.env` fixe `GEOSTUDIO_VERSION=v0.1.0`) — un nouveau déploiement obtient
   donc un artefact vieux de plusieurs semaines, potentiellement déjà
   incompatible avec le realm/schema/API que le reste du système (Keycloak,
   la base, les autres images) attend **aujourd'hui**.
2. **Publication partielle/oubliée** (`titiler`) : une image ajoutée à la
   matrice de build après la dernière exécution de `release.yml` pour ce
   tag ne sera jamais publiée tant qu'aucune nouvelle release n'est
   déclenchée — pas d'alerte, pas de porte CI qui vérifie que « toutes les
   images de la matrice existent sous le tag courant ».

### 2.3 Décision retenue : reconstruire sur chaque merge, pas sur chaque CI

Reconstruire les 9 images à **chaque exécution de CI** (chaque push, chaque
PR) serait du gaspillage pur : la CI tourne sur des branches de travail et
des commits qui ne seront jamais mergés, ça inonderait le registre d'images
orphelines pour rien. Vérifié contre le fichier réel :
`.github/workflows/release.yml` ne se déclenche **que** sur `push: tags:`
(aucun déclencheur `branches:`) — c'est précisément ce qui a laissé
`titiler` sans jamais être construit : rien ne rebuild entre deux tags.

Décision : un déclencheur **sur merge vers `main` uniquement** (pas sur
chaque CI, pas sur `dev` — branche de travail quotidienne, cf. CLAUDE.md ;
un rebuild des 9 images à chaque commit de la journée serait un coût
disproportionné pour un gain nul, puisque seule la promotion vers `main`
compte comme un état publiable), qui reconstruit les 9 images sous un tag
mouvant `edge` — distinct du déclenchement par tag existant, qui reste
pour les vraies releases versionnées (`v0.1.0`, `v0.1.1`…). Les déploiements de
dogfooding/auto-hébergement (`deploy/proxmox`, `deploy/oci` —
`GEOSTUDIO_VERSION` dans `.env`) pointent alors sur `edge`, toujours
synchro avec le code, plutôt que sur `v0.1.0`, qui dérive comme constaté en
§2.1. `v0.1.0` reste un instantané figé pour les tiers, jamais réutilisé
pour retester le dépôt lui-même.

À combiner avec une **porte CI de complétude** : indépendamment du
tagging, une vérification qui échoue si une image de la matrice
`release.yml` n'existe pas sous le tag courant — aurait détecté le cas
`titiler` immédiatement plutôt qu'en plein déploiement réel.

### 2.4 Hors périmètre de ce document

- L'écriture du workflow CI lui-même (déclencheur de merge, tag `edge`,
  porte de complétude — décidés en §2.3, à implémenter dans un plan séparé).
- La republication effective de `geostudio-core`/`geostudio-shell`/
  `geostudio-titiler` sous `v0.1.0` ou un nouveau tag (nécessite un accès
  en écriture au registre GHCR que cette session n'avait pas — `gh` était
  authentifié sans le scope `write:packages`).
- Un audit systématique des 6 autres images de la matrice pour vérifier
  qu'elles ne souffrent pas du même défaut (seules `postgis`, `core`,
  `shell`, `titiler` ont été vérifiées en conditions réelles dans cette
  session ; `worker`/`cdc-worker` partagent l'image `core` donc sont
  couvertes par le même constat).

## 3. Résumé — ce qui reste à faire

| # | Défaut | État | Action requise |
|---|---|---|---|
| 1.1 | `install.sh` route `/me` | Corrigé, poussé (`ee16a3de`) | — |
| 1.2 | CPU `qemu64` par défaut | Corrigé, poussé (`12eafe42`) | — |
| 1.3 | Traefik v3.0.4 incompatible | Corrigé, poussé (`3f17eb4b`) | — |
| 1.4 | `KC_HOSTNAME` avec schéma | Corrigé, poussé (`b2b52e65`) | — |
| 1.5 | Realm importé une seule fois | Ouvert | Plan : `kcadm.sh update` idempotent dans `install.sh` |
| 1.6 | Volume CSP root vs uid 1001 | Ouvert (contourné à la main sur cette VM) | Plan : fixer la propriété du volume à l'installation |
| 1.7 | Spam OTel sans profil `observability` | Ouvert | Plan : conditionner l'endpoint OTLP au profil actif |
| 2 | Images `v0.1.0` divergentes du source | Ouvert, 3/9 images confirmées cassées | Décidé (§2.3) : tag `edge` reconstruit sur merge vers `main` seulement + porte de complétude CI — plan d'exécution écrit (`docs/superpowers/plans/2026-09-19-fiabilisation-deploiement-proxmox-fraicheur-images.md`) |

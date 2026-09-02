# URLs cohérentes derrière Traefik pour les outils d'infrastructure

> Brainstorm du 2026-09-01. Ne fait partie d'aucune vague du plan d'action
> `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` ni de la feuille
> de route SP — chantier infra autonome, sans numéro SP.

## 1. Contexte & objectif

Traefik route déjà `shell` (`/`) et `core` (`/api`, préfixe retiré) de façon
propre, et l'overlay prod ajoute Keycloak (`/auth`). Mais quatre briques
restent sur des ports hôte ad hoc, sans aucune route Traefik :

| Service | Accès actuel (dev) | Accès actuel (prod) |
|---|---|---|
| Martin | `:3010` (host) | aucun (`ports: !reset []`, décision SP-24 : Martin se connecte en propriétaire de table, hors RLS) |
| Titiler | `:8000` (host) | aucun (`ports: !reset []`) |
| MinIO (console) | `:9001` (host) | aucun (`ports: !reset []`) |
| Grafana/otel-lgtm | `:3001` (host, profil `observability`) | aucun (profil non repris dans l'overlay prod) |

Objectif : donner à Martin/Titiler/Grafana une URL cohérente avec l'existant
(`/admin/<outil>`, même domaine `${GEOSTUDIO_PUBLIC_HOST}`/`${DOMAIN}`),
accessible aux seuls utilisateurs admin, avec un lien depuis l'espace
Administration du shell — sans revenir sur la décision de sécurité SP-24
(Martin ne redevient pas accessible en RLS-bypass à qui a juste l'URL).

**MinIO est traité différemment** (décision de session, après vérification
empirique §5 : sa console est une SPA sans aucun support de sous-chemin,
confirmé en lisant `--help` de l'image réelle — ni flag ni variable
d'environnement). Elle reste accessible exactement comme aujourd'hui
(`:9001`, dev uniquement, aucune protection ajoutée), mais le shell affiche
quand même un lien vers elle dans le même panneau, explicitement marqué
comme non protégé par ce garde-fou — cohérence de *découverte* (un seul
endroit où trouver les quatre outils), pas cohérence d'*URL* ni de
protection pour celui-ci.

## 2. Périmètre

Dans le périmètre :
- Nouveau module `core/app/admin_tools/` (launch + verify, cf. §3).
- Nouvelle variable `CORE_ADMIN_TOOLS_TOKEN_SECRET` (HMAC, même convention
  que `CORE_EXPORT_TOKEN_SECRET`) et `CORE_ADMIN_TOOLS_ENABLED` (défaut
  `false`, même convention que `CORE_TILESET3D_ENABLED`).
- Labels Traefik sur `martin`, `titiler`, `otel-lgtm` dans
  `docker-compose.yml` (base, dev) **et** leur `labels: !override`
  correspondant dans `docker-compose.prod.yml` — même besoin que
  `core`/`shell`/`keycloak`, qui divergent déjà entre les deux fichiers
  (`entrypoints=websecure`+ACME en dev vs `entrypoints=web` sans
  certresolver en prod, TLS géré par le tunnel Tailscale). Décision de
  session : même mécanisme d'auth dans les deux environnements, mais la
  config Traefik elle-même n'est pas un copier-coller brut de l'un à
  l'autre — cf. §4.2.
- Configuration de sous-chemin par outil, chacune vérifiée contre l'image
  réelle (§5) : `--base-path` (Martin), `TITILER_API_ROOT_PATH` (Titiler),
  `GF_SERVER_ROOT_URL`/`GF_SERVER_SERVE_FROM_SUB_PATH` (Grafana).
- Section « Outils d'infrastructure » dans l'espace Administration du shell
  (zone déjà gardée par `RequireRole role="admin"`, patron SP-30j) : trois
  boutons protégés (Martin/Titiler/Grafana) + un lien simple non protégé
  (MinIO, cf. §6).

Hors périmètre, explicitement :
- **Console MinIO sous `/admin/minio`** — impossible (§5, vérifié contre
  l'image réelle). Reste sur son port hôte actuel, non protégée par ce
  garde-fou ; seul son lien de découverte dans l'UI est dans le périmètre.
- **Retirer les ports hôte actuels** (`3010`, `8000`, `9001`, `3001`). Ils
  restent, pour le debug local direct non protégé — `/admin/*` est une voie
  d'accès supplémentaire, pas un remplacement.
- **Réexposer Martin sans passer par le cœur** pour les tuiles applicatives.
  Le flux normal des tuiles vectorielles d'une collection reste
  `GET /collections/{id}/tiles/{z}/{x}/{y}.mvt` (RLS + `can()`, SP-24).
  `/admin/martin` sert un usage différent : connexion directe d'un outil
  desktop (QGIS) par un admin, en toute connaissance de cause du bypass RLS.
- **oauth2-proxy / traefik-forward-auth** ou tout gatekeeper OIDC externe —
  écarté en session : dupliquerait la logique admin déjà dans le cœur
  (`user.is_admin`, alimenté par `CORE_ADMIN_SUBS`) dans un second
  composant, deux sources de vérité à garder synchrones.
- **Sous-domaines** (`martin.${DOMAIN}`) — écarté : `GEOSTUDIO_PUBLIC_HOST`
  peut être un nom Tailscale (`machine.tailnet.ts.net`), dont l'opérateur ne
  contrôle pas les sous-domaines. Le schéma doit fonctionner identiquement
  que l'hôte soit un nom Tailscale ou un vrai domaine.
- **Keycloak lui-même** : son admin console (`/auth/admin`) est déjà
  protégée par Keycloak, pas concernée par ce gate.

## 3. Mécanisme d'authentification

Contrainte de départ : le cœur n'a aujourd'hui aucune session cookie — l'API
est un Bearer JWT stateless, validé par `get_current_user`
(`core/app/auth/dependency.py`). Une navigation directe du navigateur vers
`/admin/martin` ne porte donc aucune preuve d'identité (un `forwardAuth` qui
« lirait juste un cookie » n'aurait rien à lire). Le mécanisme retenu
introduit une session courte, bootstrap par un jeton signé à usage unique —
même patron que `CORE_EXPORT_TOKEN_SECRET` (SP-17a).

### 3.1 Flux

1. Le shell (déjà authentifié, JWT en mémoire) appelle
   `POST /admin-tools/launch/{tool}` (`tool` ∈ `martin|titiler|grafana` —
   MinIO n'a pas de flux `launch`, cf. §1/§6).
   Dépendance : `user: User = Depends(get_current_user)`, puis un
   `_require_admin(user)` local au module (même style que
   `harvest/routes.py`/`collections/routes.py` : `if not user.is_admin: raise
   HTTPException(403, ...)` — pas de dépendance partagée, cohérent avec la
   duplication déjà présente ailleurs dans le dépôt).
2. Réponse : `{"url": "https://<host>/admin-tools/session/martin?_at=<jeton>"}`.
   Le jeton est un HMAC (`CORE_ADMIN_TOOLS_TOKEN_SECRET`) sur
   `{sub, tool, exp}`, `exp` = maintenant + 60s.
3. Le shell ouvre cette URL dans un nouvel onglet.
4. `GET /admin-tools/session/{tool}?_at=<jeton>` (endpoint **non** protégé
   par le `forwardAuth` — c'est lui qui pose la session) : vérifie
   signature + expiration + que `tool` du jeton correspond au `{tool}` de
   l'URL, pose un cookie `gs_admin_session` (valeur signée `{sub, exp}`,
   `exp` = maintenant + 30 min) avec les attributs `HttpOnly; Secure;
   SameSite=Strict; Path=/admin`, puis répond `302` vers
   `https://<host>/admin/{tool}/`.
5. Le navigateur suit la redirection avec le cookie posé. Traefik route vers
   le service réel via le middleware `admin-auth@docker`
   (`forwardauth.address=http://core:8200/admin-tools/verify`) : le header
   `Cookie` de la requête originale est transmis par défaut par `forwardAuth`
   à l'adresse d'auth (comportement Traefik standard, à confirmer contre la
   version `v3.0.4` déployée). `GET /admin-tools/verify` revalide le cookie
   (signature + expiration) et répond `200` ou `403` — aucune réponse
   `Set-Cookie` à ce stade, seulement à l'étape 4.
6. Tant que le cookie est valide (30 min), toute requête suivante vers
   `/admin/*` passe par la même vérification, sans repasser par le jeton
   à usage unique.

### 3.2 Pourquoi pas de header d'identité forwardé aux outils

Martin/Titiler/Grafana n'ont pas de notion d'utilisateur GeoStudio — ce sont
des outils à identifiants partagés. `admin-tools/verify` n'a donc rien à
transmettre en aval au-delà de l'autorisation (200/403) ; pas de
`authResponseHeaders` à configurer côté Traefik pour ce besoin.

### 3.3 Mode mock (dev)

`CORE_AUTH_MODE=mock` promeut déjà `bootstrap_admin=True` (cf.
`core/app/auth/dependency.py:23`) — aucune branche spéciale à écrire, le
flux ci-dessus fonctionne à l'identique.

## 4. Arborescence d'URL

```
https://<host>/                        → shell                    [existant]
https://<host>/api/...                 → core                     [existant]
https://<host>/auth/...                → Keycloak                 [existant, prod]
https://<host>/admin-tools/launch/...  → core (nouveau, JSON, JWT Bearer)
https://<host>/admin-tools/session/... → core (nouveau, bootstrap cookie)
https://<host>/admin-tools/verify      → core (nouveau, forwardAuth uniquement)
https://<host>/admin/martin/...        → Martin                   [nouveau, gate cookie]
https://<host>/admin/titiler/...       → Titiler                  [nouveau, gate cookie]
https://<host>/admin/grafana/...       → Grafana/otel-lgtm         [nouveau, gate cookie, profil observability]
```

`<host>` = `${DOMAIN}` (dev, `docker-compose.yml`) ou
`${GEOSTUDIO_PUBLIC_HOST}` (prod, overlay). MinIO reste sur son port hôte
actuel (`:9001`), hors de cette arborescence (§1).

### 4.1 Labels Traefik (patron, à répéter pour les 3 outils — chacun avec sa
propre configuration de sous-chemin, vérifiée §5)

```yaml
labels:
  - traefik.enable=true
  - traefik.http.routers.martin.rule=Host(`${DOMAIN}`) && PathPrefix(`/admin/martin`)
  - traefik.http.routers.martin.entrypoints=websecure
  - traefik.http.routers.martin.tls.certresolver=letsencrypt
  - traefik.http.routers.martin.priority=15
  - traefik.http.routers.martin.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker,strip-admin-martin@docker
  - traefik.http.middlewares.strip-admin-martin.stripprefix.prefixes=/admin/martin
  - traefik.http.services.martin.loadbalancer.server.port=3000
```

Martin connaît son propre préfixe (`command: --config /config.yaml
--base-path /admin/martin`, flag confirmé contre l'image réelle, §5) — le
TileJSON qu'il sert inclut donc déjà `/admin/martin` dans ses URLs de
tuiles, cohérent avec le `stripprefix` ci-dessus (Traefik retire le
préfixe avant de transmettre à Martin, qui le réintroduit lui-même dans ses
réponses).

Titiler suit le même schéma mais via une variable d'environnement plutôt
qu'un flag CLI : `TITILER_API_ROOT_PATH=/admin/titiler` (confirmé dans le
code de l'image — `FastAPI(root_path=api_settings.root_path)`, avec une
réécriture explicite des URLs de tuiles quand `root_path` est non vide).

Grafana (`otel-lgtm`) : `GF_SERVER_ROOT_URL=https://<host>/admin/grafana/`
et `GF_SERVER_SERVE_FROM_SUB_PATH=true` — **rejoué en conteneur réel dans
cette session** (`docker run grafana/otel-lgtm:0.11.4` avec ces deux
variables) : `GET /admin/grafana/login` → 200, `GET /admin/grafana/api/health`
→ `{"database":"ok",...}`, `GET /login` (sans préfixe) → 301. Confirme que
Grafana, avec `SERVE_FROM_SUB_PATH=true`, attend le préfixe **conservé** —
**à l'inverse de Martin/Titiler** : son routeur Traefik ne doit **pas**
avoir de `stripprefix` dans sa chaîne de middlewares (juste
`admin-auth@docker,security-headers@docker,rate-limit@docker`).

Le middleware `admin-auth` n'est déclaré qu'une fois (sur l'un des trois
services, réutilisé via `@docker` par les deux autres — patron déjà utilisé
par `security-headers`/`rate-limit` entre `core` et `shell`) :

```yaml
  - traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/admin-tools/verify
```

Priorité `15` : au-dessus du catch-all `shell` (1), en dessous de rien
d'existant sur ces chemins (aucun overlap avec `/api` ou `/auth`) — choisie
par cohérence d'échelle avec les priorités déjà en place (1, 10, 20).

### 4.2 Overlay prod (`docker-compose.prod.yml`)

Même schéma d'URL et même middleware `admin-auth`, mais les 3 services
reçoivent un `labels: !override` (comme `core`/`shell`/`keycloak` déjà dans
ce fichier) qui remplace `entrypoints=websecure` + `tls.certresolver=
letsencrypt` par `entrypoints=web` seul — pas d'ACME dans cet overlay, le
TLS est terminé au bord du tunnel Tailscale (`traefik.command` de l'overlay
n'a même pas de `--certificatesresolvers...`). Sans ce `!override`, la
fusion Compose additive laisserait les labels du fichier de base tels quels
et Traefik chercherait un certresolver `letsencrypt` qui n'existe plus dans
cet overlay — même piège que celui déjà corrigé pour `build:` (cf. l'en-tête
de `docker-compose.prod.yml`).

## 5. Risques connus — vérifiés empiriquement contre les images réelles

Piège n°3 du dépôt (« le texte d'un plan est régulièrement faux sur les
interfaces tierces ») s'applique directement ici. Vérifié en session,
contre les images réellement épinglées par ce dépôt (`docker run --help`,
lecture du code embarqué) — pas contre leur documentation générique :

- **Martin `ghcr.io/maplibre/martin:v0.18.0`** — a un flag CLI
  `--base-path <BASE_PATH>` (« Set TileJSON URL path prefix »), confirmé via
  `docker run ... martin --help`. Combinable avec `--config /config.yaml`
  (aucune exclusivité observée entre les deux flags).
- **Titiler `ghcr.io/developmentseed/titiler:0.18.4`** — son `app`
  FastAPI est construit avec `root_path=api_settings.root_path`, lu depuis
  `TITILER_API_ROOT_PATH` (`pydantic_settings`, `env_prefix="TITILER_API_"`,
  confirmé en lisant `titiler.application.settings`/`.main` dans l'image) ;
  le code réécrit explicitement les URLs de tuiles quand `root_path` est
  renseigné.
- **Grafana 12.0.1** (confirmé `grafana --version` dans l'image
  `grafana/otel-lgtm:0.11.4`) — `GF_SERVER_ROOT_URL` +
  `GF_SERVER_SERVE_FROM_SUB_PATH=true` **rejoué en conteneur réel** dans
  cette session (`docker run` direct, sans provisioning ni Traefik) :
  `/admin/grafana/login` → 200, `/admin/grafana/api/health` → sain, `/login`
  sans préfixe → 301. Confirme aussi que ce mode attend le préfixe
  **conservé** par le proxy, contrairement à Martin/Titiler (cf. §4.1) — pas
  rejoué avec le provisioning complet de ce dépôt (dashboards/alerting),
  seulement le mécanisme de sous-chemin lui-même.
- **Console MinIO `minio/minio:RELEASE.2025-09-07T16-13-09Z`** —
  **aucun** flag ni variable d'environnement de sous-chemin dans
  `minio --help` / `minio server --help` (sortie complète inspectée). La
  console est une SPA qui suppose être servie à la racine (assets en
  chemin absolu `/static/...`) — confirmé impossible, pas seulement
  « à vérifier ». D'où sa sortie du périmètre `/admin/*` (§1/§2).
- **`forwardauth` / transmission du header `Cookie`** : comportement par
  défaut de Traefik (le serveur d'auth reçoit les en-têtes de la requête
  originale, dont `Cookie`) — non rejoué contre une instance Traefik
  `v3.0.4` réelle dans cette session ; à confirmer par un test d'intégration
  concret (curl avec/sans cookie contre `/admin/martin` une fois la stack
  levée), pas supposé acquis avant cette vérification.

## 6. UI shell

Nouvelle page `AdminInfrastructurePage` (route `/admin/infrastructure`,
sibling de `/admin/extensions`/`/admin/collections`/`/admin/harvest`, même
`RequireRole role="admin"`, SP-30j) — pas un panneau ajouté à une page
existante : les trois pages admin actuelles n'ont aujourd'hui aucune
navigation croisée entre elles (vérifié, lacune préexistante, hors
périmètre de correction ici), donc un lien simple depuis
`AdminExtensionsPage` (déjà la page d'atterrissage du domaine « Admin »,
`DOMAIN_PATHS.admin`) suffit à la rendre découvrable sans reconstruire ce
qui manque pour les deux autres.

Contenu, quatre entrées dans le panneau :
- **Martin, Titiler, Grafana** — bouton qui appelle
  `POST /admin-tools/launch/{tool}` puis ouvre l'URL retournée
  (`window.open`, nouvel onglet). Masqué (remplacé par un message) si
  `CORE_ADMIN_TOOLS_ENABLED` est faux (`instanceQuery.data?.
  adminToolsEnabled`, même patron que `copilotEnabled` sur
  `AppBuilderPage`).
- **MinIO** — lien simple (`<a>`, pas de `launch`), construit côté client
  (`${window.location.protocol}//${window.location.hostname}:9001`),
  explicitement annoté « accès direct, non protégé par ce garde-fou,
  fonctionne seulement si le port 9001 est exposé sur cet hôte » — honnête
  sur le fait qu'il ne bénéficie d'aucune des garanties des trois autres.

## 7. Tests

- Core : tests unitaires du module `admin_tools` — jeton de lancement
  valide/expiré/mauvais `tool`/mauvaise signature, cookie de session
  valide/expiré/absent, 403 pour un non-admin sur `launch`.
  `CORE_ADMIN_TOOLS_ENABLED=false` → routeur non monté (même patron de test
  que `CORE_TILESET3D_ENABLED`, `test_tileset3d_enabled_flag.py`).
  `adminToolsEnabled` ajouté à `GET /instance` et `GET /me`, couvert par le
  test de parité paramétré existant (`test_auth_me_capabilities.py`,
  `_CAPABILITY_PROBES`).
- Pas de test E2E Playwright prévu contre les outils tiers eux-mêmes (hors
  périmètre de contrôle du dépôt) — seul le bouton de lancement côté shell
  (appel `launch`, ouverture d'onglet) est testable en Vitest avec
  `window.open` mocké.
- Vérification manuelle obligatoire une fois le `docker-compose.yml`
  modifié : `docker compose up`, `curl` direct contre `/admin-tools/verify`
  avec et sans cookie (confirme le comportement `forwardAuth` réel, §5),
  puis connexion admin dans le shell et clic sur chacun des trois boutons
  pour confirmer l'affichage correct sous son sous-chemin.

## 8. Questions ouvertes pour la suite (pas bloquantes pour ce design)

- Faut-il révoquer une session `gs_admin_session` à la déconnexion du shell
  (logout OIDC) ? Non traité ici — la session admin expire seule au bout de
  30 min, aucun mécanisme de révocation immédiate n'est proposé.
- Faut-il journaliser (audit_log) l'ouverture d'un outil d'infrastructure ?
  Cohérent avec la doctrine `audit_log` du projet, mais pas creusé dans ce
  brainstorm — à trancher au moment d'écrire le plan.

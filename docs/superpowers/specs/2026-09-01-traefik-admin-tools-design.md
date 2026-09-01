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

Objectif : donner à ces quatre outils une URL cohérente avec l'existant
(`/admin/<outil>`, même domaine `${GEOSTUDIO_PUBLIC_HOST}`/`${DOMAIN}`),
accessible aux seuls utilisateurs admin, avec un lien depuis l'espace
Administration du shell — sans revenir sur la décision de sécurité SP-24
(Martin ne redevient pas accessible en RLS-bypass à qui a juste l'URL).

## 2. Périmètre

Dans le périmètre :
- Nouveau module `core/app/admin_tools/` (launch + verify, cf. §3).
- Nouvelle variable `CORE_ADMIN_TOOLS_TOKEN_SECRET` (HMAC, même convention
  que `CORE_EXPORT_TOKEN_SECRET`) et `CORE_ADMIN_TOOLS_ENABLED` (défaut
  `false`, même convention que `CORE_TILESET3D_ENABLED`).
- Labels Traefik sur `martin`, `titiler`, `minio`, `otel-lgtm` dans
  `docker-compose.yml` (base, dev) **et** leur `labels: !override`
  correspondant dans `docker-compose.prod.yml` — même besoin que
  `core`/`shell`/`keycloak`, qui divergent déjà entre les deux fichiers
  (`entrypoints=websecure`+ACME en dev vs `entrypoints=web` sans
  certresolver en prod, TLS géré par le tunnel Tailscale). Décision de
  session : même mécanisme d'auth dans les deux environnements, mais la
  config Traefik elle-même n'est pas un copier-coller brut de l'un à
  l'autre — cf. §4.2.
- Section « Outils d'infrastructure » dans l'espace Administration du shell
  (zone déjà gardée par `RequireRole role="admin"`, patron SP-30j).
- Vérification empirique, par outil, du support d'un sous-chemin (cf. §5,
  risques) — piège n°3 du dépôt : jamais conclure depuis la doc/mémoire.

Hors périmètre, explicitement :
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
   `POST /admin-tools/launch/{tool}` (`tool` ∈ `martin|titiler|minio|grafana`).
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

Martin/Titiler/MinIO/Grafana n'ont pas de notion d'utilisateur GeoStudio —
ce sont des outils à identifiants partagés. `admin-tools/verify` n'a donc
rien à transmettre en aval au-delà de l'autorisation (200/403) ; pas de
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
https://<host>/admin/minio/...         → console MinIO             [nouveau, gate cookie]
https://<host>/admin/grafana/...       → Grafana/otel-lgtm         [nouveau, gate cookie, profil observability]
```

`<host>` = `${DOMAIN}` (dev, `docker-compose.yml`) ou
`${GEOSTUDIO_PUBLIC_HOST}` (prod, overlay).

### 4.1 Labels Traefik (patron, à répéter pour les 4 outils)

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

Le middleware `admin-auth` n'est déclaré qu'une fois (sur l'un des quatre
services, réutilisé via `@docker` par les trois autres — patron déjà utilisé
par `security-headers`/`rate-limit` entre `core` et `shell`) :

```yaml
  - traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/admin-tools/verify
```

Priorité `15` : au-dessus du catch-all `shell` (1), en dessous de rien
d'existant sur ces chemins (aucun overlap avec `/api` ou `/auth`) — choisie
par cohérence d'échelle avec les priorités déjà en place (1, 10, 20).

### 4.2 Overlay prod (`docker-compose.prod.yml`)

Même schéma d'URL et même middleware `admin-auth`, mais les 4 services
reçoivent un `labels: !override` (comme `core`/`shell`/`keycloak` déjà dans
ce fichier) qui remplace `entrypoints=websecure` + `tls.certresolver=
letsencrypt` par `entrypoints=web` seul — pas d'ACME dans cet overlay, le
TLS est terminé au bord du tunnel Tailscale (`traefik.command` de l'overlay
n'a même pas de `--certificatesresolvers...`). Sans ce `!override`, la
fusion Compose additive laisserait les labels du fichier de base tels quels
et Traefik chercherait un certresolver `letsencrypt` qui n'existe plus dans
cet overlay — même piège que celui déjà corrigé pour `build:` (cf. l'en-tête
de `docker-compose.prod.yml`).

## 5. Risques connus — à vérifier empiriquement avant le plan d'implémentation

Piège n°3 du dépôt (« le texte d'un plan est régulièrement faux sur les
interfaces tierces ») s'applique directement ici : aucune des lignes
suivantes ne doit être crue sans test contre l'image réelle.

- **Martin (`ghcr.io/maplibre/martin:v0.18.0`)** : le TileJSON qu'il sert
  contient des URLs de tuiles absolues. Servi derrière un `stripprefix`, ces
  URLs internes pourraient ne pas inclure `/admin/martin`, cassant un client
  (QGIS) qui suit le catalogue plutôt que de construire l'URL lui-même. À
  tester : Martin a-t-il un flag de base-path, ou un header
  `X-Rewrite-URL`/équivalent ?
- **Console MinIO** : son support d'un sous-chemin dépend de la version et
  de variables spécifiques (`MINIO_BROWSER_REDIRECT_URL` ou équivalent) — à
  vérifier contre l'image épinglée du dépôt, pas contre la doc générique
  MinIO (qui couvre plusieurs générations de la console).
- **Grafana** (`grafana/otel-lgtm:0.11.4`, image composite) : le support
  natif (`GF_SERVER_ROOT_URL`, `GF_SERVER_SERVE_FROM_SUB_PATH=true`) est
  documenté pour Grafana seul — à revérifier contre cette image précise
  (elle empile aussi Prometheus/Loki/Tempo/le collecteur OTel, potentiellement
  avec son propre reverse-proxy interne).
- **Titiler** : vérifier si un `root_path` Uvicorn/Starlette est nécessaire
  pour que `/docs` et les liens de son catalogue restent cohérents sous
  `/admin/titiler`.
- **`forwardauth.trustForwardHeader` / transmission du header `Cookie`** :
  comportement par défaut de Traefik `v3.0.4` à confirmer contre une
  instance réelle plutôt que contre la documentation Traefik (déjà vue
  fautive une fois sur ce dépôt pour un autre outil tiers, cf. piège n°3).

Aucun de ces points ne remet en cause le design ; ils déterminent seulement
si chaque outil a besoin d'une variable d'environnement supplémentaire (déjà
anticipée dans le patron ci-dessus, à instancier au cas par cas) ou d'un
`stripprefix` remplacé par une réécriture plus fine.

## 6. UI shell

Nouvelle section « Outils d'infrastructure » dans l'espace Administration
existant (même route protégée que `AdminExtensionsPage`/
`CollectionsAdminPage`/`HarvestSourcesAdminPage`, `RequireRole
role="admin"`, SP-30j). Quatre boutons (Martin, Titiler, MinIO, Grafana),
chacun :
1. Appelle `POST /admin-tools/launch/{tool}`.
2. Ouvre l'URL retournée (`window.open`, nouvel onglet).

Pas de nouvelle page — un panneau de plus dans le triptyque admin déjà en
place, cohérent avec le reste de SP-30.

## 7. Tests

- Core : tests unitaires du module `admin_tools` — jeton valide/expiré/
  mauvais `tool`/mauvaise signature, cookie valide/expiré/absent, 403 pour
  un non-admin sur `launch`. `CORE_ADMIN_TOOLS_ENABLED=false` → routeur non
  monté (même patron de test que `CORE_TILESET3D_ENABLED`).
- Pas de test E2E Playwright prévu contre les outils tiers eux-mêmes (hors
  périmètre de contrôle du dépôt) — seul le bouton de lancement côté shell
  (appel `launch`, ouverture d'onglet) est testable en Vitest avec
  `window.open` mocké.
- Vérification manuelle obligatoire, par outil, une fois le
  `docker-compose.yml` modifié : `docker compose up`, se connecter comme
  admin, cliquer chaque bouton, confirmer que l'outil s'affiche
  correctement sous son sous-chemin (cf. §5).

## 8. Questions ouvertes pour la suite (pas bloquantes pour ce design)

- Faut-il révoquer une session `gs_admin_session` à la déconnexion du shell
  (logout OIDC) ? Non traité ici — la session admin expire seule au bout de
  30 min, aucun mécanisme de révocation immédiate n'est proposé.
- Faut-il journaliser (audit_log) l'ouverture d'un outil d'infrastructure ?
  Cohérent avec la doctrine `audit_log` du projet, mais pas creusé dans ce
  brainstorm — à trancher au moment d'écrire le plan.

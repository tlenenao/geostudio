# Durcissement avant v0.1 publique (SP-26)

> Vague 3 du plan d'action `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`
> (§4, lignes 361-373 ; séquencement recommandé §6, point 6, juste après le
> lot Carte SP-24/SP-25). Spec écrite le 2026-08-23, après vérification de
> l'état réel du dépôt — 7 des 8 chantiers de la vague sont encore ouverts.

## 1. Contexte & objectif

Le lot Carte (SP-24 popup + tuiles interrogeables, SP-25 symbologie) est clos.
Le séquencement recommandé du plan d'action place ensuite la vague 3 :
« durcissement avant v0.1 publique », explicitement avant toute exposition
publique du produit (instance de démo M6, portail public).

La vague 3 compte 8 chantiers dans le document source. Vérification à l'état
actuel du dépôt (2026-08-23), contre le code plutôt que contre le document
(daté du 2026-08-20, donc antérieur à SP-21→SP-25) :

| # | Chantier | État vérifié |
|---|---|---|
| 3.1 | Interdire `CORE_AUTH_MODE=mock` hors développement (C6) | **Ouvert** — `auth/dependency.py` n'a aucune garde d'environnement |
| 3.2 | Clé maître au démarrage (I10) | **Déjà fait** — `main.py:101` appelle `secrets_crypto.load_master_key()` sans condition dans `create_app()`, `crypto.py` lève `KeyError`/`RuntimeError` fail-fast. Le document source (I10) est stale sur ce point. |
| 3.3 | CSP, Permissions-Policy, compression (I3) | **Ouvert** — aucun header de sécurité, ni Traefik ni `shell/nginx.conf` |
| 3.4 | Rate limiting différencié (I4) | **Ouvert** — seul le plafond Traefik uniforme 100/200 existe |
| 3.5 | Format d'erreur unique + arrêt propre + garde de rendu (ARC-04, I11, I12) | **Ouvert** — pas de handler d'exception global, pas de handler `SIGTERM` sur `cdc-worker`, un seul `ErrorBoundary` (par widget, `WidgetHost.tsx`) |
| 3.6 | Conteneurs non-root (SEC-02) | **Ouvert** — aucune des 8 Dockerfile n'a de directive `USER` |
| 3.7 | Notifier les alertes SLO (I9) | **Ouvert** — `rules.yaml` n'a ni `contactPoints:` ni `policies:` |
| 3.8 | E2E sur OIDC réel (I13) | **Ouvert** — les 108 specs E2E tournent toutes en `VITE_AUTH_MODE=mock` |

**3.2 est retiré du périmètre de cette spec** : déjà livré, rien à faire.
Les 7 chantiers restants sont couverts ici sous un seul SP (précédent SP-22 :
7 chantiers statiques en une spec, exécution subagent-driven-development,
revue par tâche systématique).

Objectif de sortie : les 7 preuves de sortie du plan sont atteintes, sans
baisse des compteurs de test de référence (core 1878 passed/5 skipped,
shell 161 fichiers/1461 tests, E2E 108 passed/4 skipped, couverture core
≥93%/seuil 85, shell ≥89,64%/seuil 88, `test_deployability.py` 31/31,
`pre-commit run --all-files` 5/5).

## 2. Périmètre

Les 7 chantiers, numérotés comme dans le plan d'action pour la traçabilité.
3.5 est scindé en trois sous-parties (format d'erreur, arrêt propre,
ErrorBoundary) car ce sont trois mécanismes indépendants qui ne partagent que
leur numéro de ligne dans le document source.

**Hors périmètre, explicitement** :

- **Isolation des extensions tierces par CSP** (allowlist dynamique
  d'origines pour `script-src`) — décidé en session : la CSP de ce SP durcit
  XSS/exfiltration, pas l'isolation d'un widget tiers de confiance admin.
  Reste un manque connu, non traité ici.
- **Rate limiting multi-process/multi-réplique** — l'implémentation retenue
  (compteur en mémoire par process) ne survit pas à un futur déploiement à
  plusieurs répliques de `core`. Documenté comme limite assumée, pas un
  correctif à part.
- **Email SMTP pour les notifications SLO** — webhook seul (décision de
  session). Un canal email réutiliserait `GF_SMTP_*` (config native Grafana),
  pas le coffre de secrets applicatif (Grafana ne le lit pas) — hors
  périmètre.
- **`docker-compose.prod.yml` pour `postgis` non-root** si le runtime
  officiel Postgres s'avère incompatible avec un `USER` forcé dans notre
  Dockerfile dérivé (cf. §3.6) — documenté comme déjà-conforme ou comme
  suivi non bloquant selon ce que la vérification empirique montre, pas
  forcé en aveugle.
- **Rate limiting sur `/harvest`, `/export`, `/app-exports` différencié par
  format/taille de payload** — la granularité retenue est par route et par
  utilisateur, pas par contenu de la requête.
- Toute correction fonctionnelle trouvée en passant hors des fichiers déjà
  touchés : notée en suivi non bloquant, pas corrigée ici (précédent
  constant du dépôt).

## 3. Mécanisme, par chantier

### 3.1 — Interdire le mode mock hors développement (C6)

`core/app/auth/dependency.py` : nouvelle garde appelée depuis
`create_app()` (`core/app/main.py`), juste après l'appel existant à
`secrets_crypto.load_master_key()` — même emplacement, même style
fail-fast :

```python
def _reject_mock_outside_development() -> None:
    if _mock_mode() and os.environ.get("CORE_ENV") != "development":
        raise RuntimeError(
            "CORE_AUTH_MODE=mock requires CORE_ENV=development"
        )
```

`docker-compose.yml` (base/dev) : `CORE_ENV: ${CORE_ENV:-development}` sur
`core`/`worker`/`cdc-worker`. `docker-compose.prod.yml` force déjà
`CORE_AUTH_MODE: oidc` sans indirection par variable — vérifié, aucun
changement nécessaire côté prod pour l'auth mode. Cette garde est un filet
de sécurité pour tout déploiement du fichier de base seul, sans l'overlay
prod (le scénario que C6 décrit).

`.env.example` : documenter `CORE_ENV` à côté de `CORE_AUTH_MODE`.

Suite de tests core (fixtures `conftest.py`) : `CORE_ENV=development` ajouté
partout où `CORE_AUTH_MODE=mock` l'est déjà, même convention.

### 3.2 — CSP, Permissions-Policy, compression (I3)

Deux points d'application indépendants, les deux existent en prod :

1. **Traefik** (`docker-compose.prod.yml`, labels du middleware déjà
   utilisé pour `rate-limit`) : nouveau middleware `headers` avec
   `Content-Security-Policy`, `Permissions-Policy`, `X-Content-Type-Options:
   nosniff`, `compress: true`.
2. **`shell/nginx.conf`** : mêmes en-têtes via `add_header`, plus `gzip on`
   — ce chemin sert aussi bien le conteneur `shell` en dev que tout export
   statique/autoporté (SP-18a/c) qui ne passe jamais par Traefik.

Directives CSP (valeurs de départ, affinées empiriquement pendant
l'implémentation — cf. §5) :

| Directive | Valeur | Raison |
|---|---|---|
| `default-src` | `'self'` | Base restrictive |
| `script-src` | `'self'` | Décision de session : pas d'allowlist dynamique d'extensions (hors périmètre §2) |
| `style-src` | `'self' 'unsafe-inline'` | MapLibre GL JS injecte des styles inline pour le rendu canvas — à confirmer/resserrer empiriquement |
| `connect-src` | `'self'` + origine cœur + origine Keycloak | Appels API, tuiles MVT, refresh OIDC |
| `img-src` | `'self' data: blob:` + origine cœur | Vignettes, tuiles raster, thumbnails |
| `worker-src` | `'self' blob:` | Web workers MapLibre/deck.gl |
| `frame-src` | Origine Keycloak | Iframe de silent SSO (`signinSilent`, SP-20) |
| `object-src` | `'none'` | Aucun usage de plugin |

`Permissions-Policy` : désactive `camera`, `microphone`, `payment`, `usb` —
audit rapide du shell pour confirmer qu'aucun de ces usages n'existe
(recherche `navigator.mediaDevices`/`geolocation` avant de blinder
`geolocation` aussi).

Rollout : `Content-Security-Policy-Report-Only` d'abord pendant
l'implémentation (vérification manuelle sur builder, éditeur de carte,
widget carte, une extension tierce active), bascule en `Content-Security-
Policy` (enforcing) avant la tâche de clôture — la preuve de sortie exige
un header enforcing, pas report-only.

### 3.3 — Rate limiting différencié (I4)

Nouveau module `core/app/ratelimit/` (bas de la pile, pas de dépendance
entrante d'un autre module métier — comparable à `app.analytics.egress`
dans son rôle transverse). Compteur glissant en mémoire process, clé
`(user.oidc_sub, route_group)`, pas de nouvelle dépendance infra (Redis
explicitement écarté par le plan §5).

Dépendance FastAPI appliquée aux 6 routes nommées par le plan :
`/analytics/sql`, `/mcp`, `/copilot/turn`, `/export`, `/app-exports`,
`/harvest`. Budgets distincts par groupe de coût réel (chiffres proposés,
affinés en tâche) :

| Groupe | Routes | Budget proposé |
|---|---|---|
| Sandbox SQL | `/analytics/sql` | 10 / min |
| LLM | `/mcp`, `/copilot/turn` | 20 / min |
| Jobs asynchrones | `/export`, `/app-exports` | 15 / min |
| Egress externe | `/harvest` | 10 / min |

Dépassement → 429 avec `Retry-After` et corps RFC 7807 (§3.4). Limite
assumée et documentée : compteur en mémoire, ne tient pas au-delà d'un seul
process `core` (cohérent avec l'absence actuelle de `--workers`, C2/vague 0
déjà close sur ce point précis).

### 3.4 — Format d'erreur unique RFC 7807 (ARC-04)

Handler d'exception global dans `core/app/main.py` (`app.exception_handler`
sur `HTTPException` et sur `Exception` non gérée), `Content-Type:
application/problem+json`, corps `{type, title, status, detail}`.

**Décision de compatibilité, tranchée en session** : le shell lit
aujourd'hui `data?.detail` comme une chaîne (`typeof data?.detail ===
"string"`) ou comme un objet imbriqué `data?.detail?.errors`
(`FeatureValidationError`, `SqlQueryError`, `itemClient.ts:236,290`). RFC
7807 veut `detail` en chaîne simple. Les erreurs structurées migrent donc
vers un membre d'extension `errors` au premier niveau, à côté de
`type`/`title`/`status`/`detail` — **changement cassant assumé et scopé** :
2 sites d'appel dans `itemClient.ts` (`data?.detail?.errors` →
`data?.errors`), OpenAPI + types TS régénérés. `detail` continue de porter
un message humain pour tous les autres cas (`HTTPException(detail=...)`
existant, ~40 sites, comportement inchangé).

### 3.5 — Arrêt propre `cdc-worker` (I11)

`core/app/cdc/main.py` : handler `signal.signal(signal.SIGTERM, ...)`
positionnant un flag vérifié dans la boucle de consommation du slot de
réplication logique — le batch en cours et le feedback LSN se terminent
avant sortie, pas d'arrêt en plein milieu d'un flush. Le worker
procrastinate a déjà un mécanisme équivalent ailleurs dans le dépôt ; ce
chantier ne le duplique pas, il comble le seul point qui en manque
(`cdc-worker` tourne en dehors de procrastinate, boucle main() dédiée).

### 3.6 — `ErrorBoundary` applicatif (I12)

Un `ErrorBoundary` React au niveau racine de l'app (`shell/src/App.tsx` ou
équivalent, sous le routeur), distinct de celui déjà existant par widget
dans `WidgetHost.tsx`. Capture les exceptions de rendu du chrome
builder/pages/panels — aujourd'hui un écran blanc — et affiche un repli
lisible (pas de tentative de "reprendre" l'état, juste un message +
rechargement).

### 3.7 — Conteneurs non-root (SEC-02)

`USER` ajouté à `core`, `deploy/export-worker`,
`deploy/appexport-runtime-builder`, `deploy/appexport-standalone` (étage
python), `deploy/qgis-worker`, `deploy/backup`, `shell` (7 des 8 Dockerfile
— cf. `postgis` ci-dessous).

**Risque concret identifié et à traiter, pas une formalité** :
`core/Dockerfile:24` installe les extensions DuckDB (`httpfs`, `spatial`,
`h3`) une fois au build, dans `~/.duckdb/extensions` — le commentaire du
fichier est explicite : « le même répertoire d'extensions est réutilisé »
entre build et exécution, précisément pour éviter un `INSTALL` réseau à
l'exécution (`app/analytics/duckdb_conn.py` appelle `INSTALL`/`LOAD` à
chaque connexion, en s'attendant à un cache local déjà rempli). Passer à un
utilisateur non-root sans y toucher change `$HOME` entre le build (root) et
l'exécution (nouvel utilisateur) → DuckDB ne retrouve plus les extensions
→ tentative de téléchargement réseau à l'exécution → échec en déploiement
sans egress, régression du design SP-11b/SP-15c documenté dans le fichier
lui-même. Fix retenu : `ENV HOME=/opt/duckdb-home` (chemin dédié, pas
`/root`) posé **avant** l'étape d'installation des extensions dans le
Dockerfile (donc utilisé au build) **et** conservé à l'exécution, répertoire
`chmod` lisible par le nouvel utilisateur (l'écriture n'est nécessaire
qu'au build, en root). Vérifié en tâche par un `docker run --rm <image>`
non-root qui appelle réellement `open_connection`/`open_spatial_connection`
sans egress réseau disponible (offline check, pas seulement `id -u`).
Même vérification pour `worker` (même image que `core`) et `export-worker`
si celui-ci charge aussi DuckDB (à confirmer en tâche — `grep` initial ne
l'a pas listé parmi les consommateurs mais partage l'image `core`).

`shell` (nginx) : `nginx:1.27-alpine` écoute sur 8300, déjà un port non
privilégié (>1024) — donc pas besoin de changer de port pour passer
non-root, seul un `USER` explicite + permissions d'écriture ajustées pour
les répertoires que nginx doit pouvoir écrire à l'exécution (`/var/cache/
nginx`, `/var/run`) sont nécessaires. À vérifier en tâche contre l'image
réelle plutôt que supposé.

`postgis` : **vérification requise avant toute action**, pas un ajout
systématique. Les images Postgres officielles démarrent en root pour
corriger les permissions du volume `PGDATA` (`chown`) puis se relancent
elles-mêmes via `gosu`/`su-exec` sous l'utilisateur `postgres` — forcer
`USER postgres` dans notre Dockerfile dérivé casserait potentiellement ce
mécanisme d'auto-drop. La tâche vérifie par un conteneur réel
(`docker run --rm <image> id` après démarrage, pas seulement lecture du
Dockerfile de base) : si confirmé déjà non-root à l'exécution malgré
l'absence de directive `USER`, documenté comme déjà-conforme ; sinon,
traité comme les 7 autres.

Preuve de sortie : `docker run --rm <image> id -u` ≠ 0 sur les images
concernées ; un `POST .../aggregate` (chemin DuckDB) et une ingestion
GeoPackage (chemin QGIS pour `qgis-worker` si `CORE_TEST_QGIS_WORKER_URL`
est disponible, sinon vérification statique documentée comme telle —
précédent SP-15d, ne pas prétendre à plus que ce qui est réellement
exécuté) fonctionnent toujours.

### 3.8 — Notifier les alertes SLO (I9)

Nouveau fichier de provisioning Grafana
`deploy/observability/grafana/provisioning/alerting/contactpoints.yaml` :
un contact point `webhook`, URL portée par une nouvelle variable
d'environnement (`GRAFANA_ALERT_WEBHOOK_URL`, documentée dans
`.env.example`, vide par défaut = pas de notification tant que
l'opérateur ne la renseigne pas — pas un défaut qui pointe vers un service
inexistant). Fichier `policies.yaml` compagnon : route le dossier `SLO`
vers ce contact point (politique par défaut ou route nommée
`match: {folder: SLO}`).

Mécanisme d'interpolation de la variable dans le YAML de provisioning à
confirmer en tâche contre la version de Grafana réellement pinnée
(SP-21) : substitution native `${VAR}` si supportée par cette version, sinon
étape `envsubst` dans l'entrypoint du service `grafana`
(`docker-compose.yml`) avant que Grafana ne lise le répertoire de
provisioning.

Preuve de sortie : réutilise la règle `test-alert-do-not-keep-in-prod`
déjà présente dans `rules.yaml` pour cet usage exact (son commentaire le
dit explicitement) — `isPaused: false` temporairement, observation d'une
notification webhook réellement reçue, `isPaused: true` restauré. Pas une
simulation : preuve de bout en bout comme les autres SP du dépôt l'exigent.

### 3.9 — E2E sur OIDC réel (I13)

Nouveau job CI (`shell-e2e-oidc` ou équivalent, `.github/workflows/ci.yml`),
distinct du job `shell` existant (qui reste en mock, 108 specs). Services :
`postgis`, `keycloak` (import `deploy/keycloak/geostudio-realm.json`, déjà
utilisé par `docker-compose.yml` en dev — pas de nouveau realm à créer),
`core` avec `CORE_AUTH_MODE=oidc` + `CORE_OIDC_ISSUER` pointant le Keycloak
du job. Shell buildé avec `VITE_AUTH_MODE=oidc`.

Une spec Playwright dédiée (`shell/e2e/auth-oidc.spec.ts`), hors du run
`npm run e2e` par défaut (nouveau script `npm run e2e:oidc` ou garde par
variable d'environnement, précédent des marqueurs
`@pytest.mark.postgis`/`qgis`/`playwright` côté core). Couvre, dans l'ordre
du plan : connexion (redirection Keycloak → retour avec session valide),
rafraîchissement de jeton, expiration (jeton expiré → déconnexion forcée),
déconnexion. Réutilise le patron `signinSilent` déjà éprouvé par
`useMcpToken` (SP-20) pour la partie rafraîchissement, cette fois observé
en conditions réelles — referme explicitement le suivi non bloquant SP-20
« aucun bout-en-bout navigateur+iframe+Keycloak n'a pu être produit ».

**Exigence de preuve, pas de best-effort** : contrairement aux tests
`@pytest.mark.qgis` de SP-15d (jamais exécutés pour de vrai à ce jour), ce
job doit tourner et passer réellement en CI avant la clôture de ce SP —
précédent explicite SP-17a Task 6 (skip vérifié dans les deux sens).

## 4. Décisions prises en session (2026-08-23)

1. **CSP `script-src` reste permissif** (`'self'`, pas d'allowlist
   dynamique d'origines d'extension) — le gain visé est XSS/exfiltration,
   pas l'isolation d'un widget tiers. Isolation par extension : hors
   périmètre, non planifiée.
2. **Rate limiting en mémoire process, par utilisateur** — pas de nouvelle
   dépendance infra, limite multi-process assumée et documentée plutôt que
   résolue.
3. **Notifications SLO : webhook générique seulement**, pas d'email SMTP.
   Système Grafana Alerting (`rules.yaml`), explicitement distinct du
   produit `AlertRule` (SP-16b) — vérifié, ce sont deux mécanismes séparés
   qui partagent juste le mot « alerte ».
4. **RFC 7807 : `errors` en membre d'extension top-level**, pas imbriqué
   sous `detail` — changement cassant scopé à 2 sites d'appel shell +
   régénération OpenAPI/TS, documenté explicitement plutôt que découvert en
   revue.
5. **`postgis` non forcé non-root a priori** — vérification empirique
   d'abord (le mécanisme `gosu` du runtime Postgres officiel pourrait
   dépendre de démarrer root), décision de traitement (déjà-conforme vs.
   suivi non bloquant vs. changement) prise en tâche contre le
   comportement réel du conteneur.
6. **DuckDB + non-root sur `core`/`worker`** : `HOME` fixé à un répertoire
   dédié (`/opt/duckdb-home`), cohérent entre étape de build (root, qui
   installe les extensions) et exécution (utilisateur non-root, lecture
   seule) — pas de nouvel `INSTALL` réseau à l'exécution, préserve le
   design SP-11b/SP-15c documenté dans `core/Dockerfile`.

## 5. Ordre d'exécution recommandé

Les 7 chantiers sont largement indépendants (fichiers disjoints, aucune
dépendance de données entre eux). Ordre proposé, du risque de régression le
plus élevé au plus faible, pour que les tâches les plus susceptibles de
révéler un problème d'intégration passent tôt :

1. **3.7 — Conteneurs non-root** (le risque DuckDB/`postgis` est le plus
   susceptible de faire dérailler le reste s'il révèle un problème
   d'architecture plus profond que prévu).
2. **3.1 — Interdire le mode mock hors dev** (petit, indépendant, sert de
   échauffement).
3. **3.4 — Format d'erreur RFC 7807** (touche un contrat existant côté
   shell — le faire avant 3.3/tout ce qui pourrait vouloir réutiliser le
   nouveau format d'erreur pour les 429 de rate limiting).
4. **3.3 — Rate limiting différencié** (dépend du format d'erreur de
   l'étape précédente pour ses réponses 429).
5. **3.5 — Arrêt propre `cdc-worker`** (isolé, aucune dépendance).
6. **3.6 — `ErrorBoundary` applicatif** (isolé, shell seul).
7. **3.2 — CSP/Permissions-Policy/compression** (bénéficie d'être fait
   après que toutes les nouvelles surfaces shell/API du SP existent, pour
   n'avoir qu'une seule passe de vérification manuelle empirique).
8. **3.8 — Notifications SLO** (isolé, infra Grafana seule).
9. **3.9 — E2E OIDC réel** (en dernier — la preuve la plus longue à obtenir,
   et elle peut exercer indirectement 3.1/3.4 en conditions réelles OIDC,
   donc bénéficie de venir après leur implémentation).

Puis revue finale de branche, fixes, re-revue — précédent constant du
dépôt.

## 6. Validation & preuves de sortie

Reprend les preuves de sortie du plan d'action, par chantier :

| # | Preuve de sortie |
|---|---|
| 3.1 | Test : `CORE_AUTH_MODE=mock` sans `CORE_ENV=development` → refus de démarrage (`create_app()` lève) |
| 3.2 | Test manuel + E2E `Report-Only` puis enforcing : un widget tiers légitime charge encore ; `curl -H 'Accept-Encoding: gzip'` renvoie du contenu compressé sur `shell` et via Traefik |
| 3.3 | Test : un 4ᵉ `POST /analytics/sql` en moins d'une minute → 429 avec `Retry-After`, un `GET /health` concurrent passe |
| 3.4 | Test : une exception non gérée renvoie `application/problem+json` conforme |
| 3.5 | Test : `SIGTERM` sur `cdc-worker` referme proprement (flush LSN observé avant sortie) |
| 3.6 | `docker run <image> id -u` ≠ 0 sur les images concernées ; `POST .../aggregate` fonctionne toujours hors ligne (pas de tentative réseau DuckDB) |
| 3.7 | La règle `test-alert-do-not-keep-in-prod` délivre réellement une notification webhook observée |
| 3.8 | La spec `auth-oidc.spec.ts` passe en CI avec un service Keycloak réel — exécution prouvée, pas seulement écrite |

Preuves de non-régression, mesurées à la clôture (mêmes commandes que les
SP précédents) : core `uv run pytest` (PostGIS réel), `ruff check`/`format
--check`/`mypy --strict` (4 modules)/`lint-imports` ; shell `npm run
lint`/`format:check`/`test`/`build`/`e2e` (108 specs mock, référence
inchangée, + la nouvelle spec OIDC dans son job dédié) ; couverture core et
shell aux seuils versionnés ; `test_deployability.py` (31/31, ce SP
n'ajoute a priori pas de nouvelle variable d'environnement non câblée, sauf
`CORE_ENV` et `GRAFANA_ALERT_WEBHOOK_URL` — à câbler dans `.env.example`
**et** dans au moins un service pour que la 8ᵉ règle du garde-fou reste
verte) ; `uvx pre-commit run --all-files` 5/5 ; OpenAPI/types TS
régénérés et synchronisés (attendu non-vide cette fois, contrairement aux
capacités derrière un flag désactivé en CI : le handler d'erreur global et
`ratelimit` sont montés inconditionnellement).

## 7. Risques et limites connues

- **CSP calibrée empiriquement, pas garantie complète à l'écriture de cette
  spec** : MapLibre GL JS/deck.gl peuvent exiger des directives non listées
  en §3.2 (ex. `style-src` avec un nonce plutôt que `'unsafe-inline'`). La
  tâche correspondante inclut une vérification manuelle des 4 surfaces
  citées avant de passer en enforcing.
- **Rate limiting en mémoire ne survit pas à un `core` multi-réplique** —
  limite assumée, documentée en suivi non bloquant si ce SP se ferme avant
  qu'un besoin de scale-out réel n'émerge.
- **`postgis` non-root potentiellement hors périmètre** selon ce que la
  vérification empirique du chantier 3.6 montre — pas un échec du SP si
  documenté avec sa raison, précédent CLAUDE.md (licences bloquées avec
  raison écrite).
- **Mécanisme d'interpolation de variable dans le provisioning Grafana
  (3.7) non confirmé à l'écriture** — dépend de la version pinnée
  (SP-21), résolu en tâche.
- **E2E OIDC (3.8) est le chantier le plus susceptible de découvrir un
  problème d'intégration Keycloak non anticipé** (réalisme du realm
  importé en CI vs. dev, timing des jetons courts pour tester
  l'expiration sans ralentir la CI) — placé en dernier dans l'ordre
  d'exécution (§5) précisément pour cette raison.

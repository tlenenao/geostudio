# SP-57b — Contrat d'API `/v1/`, ADR, guide de contribution : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les volets 5.3 (contrat d'API `/v1/`), 5.4 (ADR) et 5.5
(guide de contribution) de GAP-14. Les volets 5.4/5.5 sont rapides et sans
risque (docs pures) ; le volet 5.3 est le cœur du risque de ce plan — un
préfixe de version qui semble mécanique en surface mais qui recoupe des
chemins bruts hors routage FastAPI (rate-limit, CORS, garde lecture-seule),
des URLs absolues construites côté Python, des labels Traefik, et ~120
occurrences de mocks de test à mettre à jour (cf. spec §1.3-1.5).

**Architecture:** 8 tâches, dans l'ordre de risque croissant défini par la
spec §6 : ADR (Task 1), contribution (Task 2), puis le contrat `/v1/` en
5 tâches (routeur FastAPI, chemins bruts, infra Traefik, shell, migration
des tests), puis clôture (Task 8).

**Tech Stack:** Python/FastAPI (cœur), TypeScript/React (shell), Traefik +
Docker Compose (infra), Markdown (ADR/contribution).

**Document source :**
`docs/superpowers/specs/2026-09-06-sp57b-api-v1-adr-contribution-design.md`
(§2 API v1, §3 ADR, §4 contribution, §5 risques).

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche qui touche du code (Tasks 3-7)
  pose son test avant l'implémentation. Les tâches purement documentaires
  (1, 2) n'ont pas de test au sens classique — leur "filet" est une
  vérification de contenu (liens valides, gabarits bien formés).
- **Aucune compatibilité ascendante** (spec §2.6) : migration directe vers
  `/v1`, pas de double montage. Toute route qui répond encore sur son
  ancien chemin non préfixé après la Task 3 est un bug à corriger, pas un
  filet de sécurité à garder.
- **`/health` et `/mcp` ne bougent jamais** — tout test qui les concerne
  (healthcheck Docker, découverte OAuth MCP) doit continuer de cibler le
  chemin non préfixé. C'est un point de vigilance explicite à chaque tâche
  qui touche `main.py`/`limiter.py`/`docker-compose.yml`.
- **Suite complète rejouée à la fin de chaque tâche qui touche une route
  partagée** (piège CLAUDE.md n°6) : `cd core && uv run pytest`,
  `cd shell && npm run test`. `npm run e2e` en fin de Tasks 6, 7 et à la
  clôture.
- **Tout filet de test ajouté est vérifié par falsification** (piège
  CLAUDE.md n°10) — Tasks 4, 6.
- **Régénérer la spec OpenAPI + types TS** (piège CLAUDE.md n°1) dès la
  Task 3 (diff **non vide** attendu — chaque route change de chemin,
  contrairement à un ajout de champ isolé).
- **Piège CLAUDE.md n°4 (revue de branche)** : à la clôture, vérifier que
  `/health`, `/mcp`, ET une route normale (`/v1/items`) répondent tous
  correctement sur une stack réelle — pas seulement que les tests unitaires
  passent isolément.
- **Vérifier chaque fichier avant de le modifier** — en particulier les 13
  fichiers `CORE_BASE_URL`/`base_url` de la Task 4 : certains (le loopback
  MCP) ne doivent PAS changer, vérifier au cas par cas plutôt que
  d'appliquer un remplacement aveugle.

---

## Task 1 : `docs/adr/` — template, index, 11 ADR rétroactifs (GAP-14 5.4)

**Files:**
- Create: `docs/adr/README.md`, `docs/adr/0001-moteur-autorisation-can.md`,
  `docs/adr/0002-groupes-geres-par-le-coeur.md`,
  `docs/adr/0003-rls-postgis-differee.md`,
  `docs/adr/0004-ogc-api-features-ecriture.md`,
  `docs/adr/0005-procrastinate-file-jobs.md`,
  `docs/adr/0006-cel-langage-expressions.md`,
  `docs/adr/0007-web-components-lit-sdk.md`,
  `docs/adr/0008-structure-depot-core.md`,
  `docs/adr/0009-tenant-id-audit-log-partout.md`,
  `docs/adr/0010-client-ts-genere-openapi.md`,
  `docs/adr/0011-sortie-geonode-superset-redis.md`

- [ ] **Step 1 : vérifier la numérotation et le contenu source de chaque
  arbitrage avant d'écrire**

```bash
grep -n "^### A1 \|^### A2 \|^### A3 \|^### A4 \|^### A5 \|^### A8 \|^### A10 \|^### A11 \|^### A14 " \
  docs/vision/2026-07-04-feuille-de-route-geostudio.md
```

Relire chaque section citée en entier (pas seulement son titre) avant de la
résumer dans l'ADR correspondant — ne pas paraphraser de mémoire.

- [ ] **Step 2 : écrire `docs/adr/README.md`**

Index (tableau numéro/titre/statut) + processus (quand écrire un ADR,
format MADR-lite : Contexte/Décision/Conséquences, statut
acceptée/remplacée, ligne `Source :` vers l'arbitrage `Axx` d'origine quand
il existe).

- [ ] **Step 3 : écrire les 11 ADR**

Un fichier par décision de la spec §3.2, chacun avec sa ligne `Source :`
pointant vers la section exacte du document vision (ou vers `CLAUDE.md`
« Décisions figées » pour les deux qui n'ont pas d'`Axx` dédié — ADR-0009 et
ADR-0011). Ne pas dupliquer le tableau d'options complet du document source
— un résumé de 3-6 lignes en `## Contexte` suffit, avec le pointeur pour le
détail.

- [ ] **Step 4 : vérifier les liens**

```bash
for f in docs/adr/*.md; do grep -o 'docs/vision/[a-zA-Z0-9./-]*\.md\|CLAUDE\.md' "$f"; done \
  | sort -u | while read -r ref; do test -f "$ref" && echo "OK: $ref" || echo "MANQUANT: $ref"; done
```

- [ ] **Step 5 : commit**

```bash
git add docs/adr/
git commit -m "$(cat <<'EOF'
docs: crée docs/adr/ (11 ADR rétroactifs + processus)

Ferme GAP-14 volet 5.4 : format MADR-lite, chaque ADR pointe vers
l'arbitrage Axx ou la décision figée CLAUDE.md dont il est extrait,
sans dupliquer le tableau d'options complet du document source.
EOF
)"
```

---

## Task 2 : gabarits GitHub + `SECURITY.md` (GAP-14 5.5)

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`,
  `.github/ISSUE_TEMPLATE/feature_request.md`,
  `.github/PULL_REQUEST_TEMPLATE.md`, `SECURITY.md`
- Modify: `README.md` (lien vers `SECURITY.md`, à côté de la ligne
  `CONTRIBUTING.md` existante)

- [ ] **Step 1 : relire `CONTRIBUTING.md` en entier avant d'écrire les
  gabarits**

```bash
cat CONTRIBUTING.md
```

Les gabarits doivent structurer ce que `CONTRIBUTING.md` demande déjà en
prose (§« Reporting a bug or proposing a feature », §« Pull request
process ») — pas introduire une exigence nouvelle et divergente.

- [ ] **Step 2 : écrire les 2 gabarits d'issue**

`bug_report.md` : repro/attendu/observé/environnement (OS, navigateur si
pertinent, `docker compose up` ou setup manuel) — reprend exactement les
items déjà listés dans `CONTRIBUTING.md`. `feature_request.md` : problème à
résoudre + esquisse de solution + rappel de vérifier la feuille de route
d'abord (lien vers
`docs/vision/2026-07-04-feuille-de-route-geostudio.md`).

- [ ] **Step 3 : écrire `PULL_REQUEST_TEMPLATE.md`**

Checklist reprenant les 5 étapes du process PR de `CONTRIBUTING.md` (branche
depuis `dev`, commits conventional, suites de test vertes, description
quoi/pourquoi, lien vers spec/plan si applicable).

- [ ] **Step 4 : écrire `SECURITY.md`**

Périmètre (quelles versions/quel déploiement sont couverts), canal de
signalement honnête (spec §5 — pas de faux processus : si le seul canal
réel est une issue privée/un email de contact du mainteneur, l'écrire tel
quel plutôt que de promettre un programme de bug bounty ou un délai de
réponse contractuel qui n'existe pas). Ne pas activer de fonctionnalité
GitHub qui ne l'est pas déjà (`secret_scanning`/
`dependabot_security_updates` restent désactivés, cf. `CLAUDE.md` — ne pas
prétendre le contraire dans le texte).

- [ ] **Step 5 : lien depuis `README.md`**

À côté de la ligne `CONTRIBUTING.md` existante (`README.md:178`, table des
pointeurs de documentation).

- [ ] **Step 6 : commit**

```bash
git add .github/ISSUE_TEMPLATE/ .github/PULL_REQUEST_TEMPLATE.md SECURITY.md README.md
git commit -m "$(cat <<'EOF'
docs: gabarits GitHub (issue/PR) + SECURITY.md

Ferme GAP-14 volet 5.5 — CONTRIBUTING.md et CODE_OF_CONDUCT.md
existaient déjà (SP-9, 2026-07-16) et couvraient déjà l'essentiel,
contrairement à ce que GAP-14 affirmait ("absent") : ce commit ajoute
la structure GitHub (gabarits) et la politique de sécurité qui
manquaient réellement.
EOF
)"
```

---

## Task 3 : routeur `/v1` imbriqué sur les 31 routeurs (GAP-14 5.3)

**Files:**
- Modify: `core/app/main.py`
- Test: `core/tests/test_main.py` ou équivalent (vérifier le nom exact du
  fichier qui teste déjà `create_app()`/le routage global avant d'en créer
  un nouveau — `find core/tests -iname "*main*"`)

**Interfaces:**
- Produces : toutes les routes des 31 routeurs (`configs`, `extensions`,
  `secrets`, `roles`, `mapicons`, `instance`, `items`, `auth`, `sharing`,
  `public`, `schemas`, `collections`, `catalog`, `features`, `tiles`,
  `attachments`, `ingestion`, `stac`, `dcat`, `harvest`, `alerts`,
  `reports`, `notifications`, `usage`, `quotas`, `compliance`, `pipelines`,
  `export`, `appexport`, `tileset3d`, `terrain3d`, `copilot`,
  `admin_tools`) répondent désormais sous `/v1/...`. `/health` et `/mcp`
  inchangés.

- [ ] **Step 1 : écrire le test avant le code**

Un test qui appelle `create_app()` (client de test FastAPI existant, même
patron que les tests de routes déjà présents) et vérifie :
`GET /v1/items` répond (200 ou 401 selon l'auth du test, mais pas 404) ;
`GET /items` (sans préfixe) répond **404** (preuve qu'il n'y a pas de double
montage rétrocompatible, cf. spec §2.6) ; `GET /health` répond toujours sans
préfixe ; une requête vers le montage MCP (`/mcp`, méthode appropriée)
n'est pas affectée par le changement.

```bash
cd core && uv run pytest tests/test_main.py -k "v1 or health or mcp" -v
# attendu : ÉCHEC (le routeur v1 n'existe pas encore)
```

- [ ] **Step 2 : implémenter**

```python
v1_router = APIRouter(prefix="/v1")
for r in (configs_routes.router, extensions_routes.router, ...):  # les 31
    v1_router.include_router(r)
app.include_router(v1_router)
```

Remplacer les 31 appels `app.include_router(x.router)` existants par
l'ajout à `v1_router` (garder l'ordre existant — certains routeurs peuvent
avoir un ordre significatif pour la résolution de route, à vérifier si un
conflit de chemin apparaît). Ne PAS toucher `app.get("/health")` ni
`app.mount("/", mcp_server.streamable_http_app())`.

```bash
cd core && uv run pytest tests/test_main.py -v
```

- [ ] **Step 3 : suite complète du cœur (attendu : nombreux échecs à ce
  stade — normal, corrigés par les Tasks 4-5)**

```bash
cd core && uv run pytest 2>&1 | tail -50
```

Ne pas s'inquiéter d'échecs massifs ici : tout test qui appelle une route
sans le préfixe `/v1` échoue désormais, **c'est le travail des tâches
suivantes de les corriger** — mais il faut lire la liste pour confirmer que
les échecs sont bien de cette nature (404 sur ancien chemin), pas d'une
autre cause. Si la suite de tests du cœur construit ses URLs via un helper
partagé (`conftest.py`, un client de test avec une base URL), vérifier s'il
suffit de corriger CE point unique plutôt que chaque test individuellement
— chercher avant d'éditer fichier par fichier.

```bash
grep -rn "client.get(\"/\|client.post(\"/\|TestClient(" core/tests/conftest.py 2>/dev/null | head -20
```

- [ ] **Step 4 : corriger les tests du cœur (au point unique si possible,
  sinon fichier par fichier)**

```bash
cd core && uv run pytest
```

Suite verte avant de continuer.

- [ ] **Step 5 : régénérer OpenAPI/types TS**

```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Diff **non vide attendu** — chaque chemin de route change (`/items` →
`/v1/items`, etc.). Vérifier que `openapi.json` ne référence PAS `/v1/health`
ni `/v1/mcp` (confirmation que les deux exclusions ont tenu).

- [ ] **Step 6 : commit**

```bash
git add core/app/main.py core/tests/ core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): verse les 31 routeurs de l'API sous /v1 (GAP-14, contrat 1/5)

/health et le montage /mcp restent hors versionnement (contrats
externes à protocole fixe : healthcheck Docker, découverte OAuth
MCP). Pas de compatibilité ascendante — décision assumée (spec SP-57b
§2.6), aucun consommateur externe réel n'existe encore.
EOF
)"
```

---

## Task 4 : chemins bruts hors routage + audit `CORE_BASE_URL` (GAP-14 5.3)

**Files:**
- Modify: `core/app/main.py` (les 4 regex/comparaisons littérales),
  `core/app/ratelimit/limiter.py` (les 6 regex de `route_group()`)
- Modify (au cas par cas, après audit) : tout ou partie de
  `core/app/admin_tools/routes.py`, `core/app/analytics/duckdb_conn.py`,
  `core/app/appexport/jobs.py`, `core/app/collections/routes.py`,
  `core/app/features/routes.py`, `core/app/ingestion/importer.py`,
  `core/app/items/routes.py`, `core/app/pipelines/connector_runtime.py`,
  `core/app/dcat/routes.py`, `core/app/public/routes.py`,
  `core/app/jobs/__init__.py`
- Ne PAS modifier (vérifié spec §1.4) : `core/app/copilot/mcp_loopback.py`,
  `core/app/mcp/server.py`
- Test: `core/tests/test_ratelimit.py` (ou équivalent — vérifier le nom
  exact), `core/tests/test_main.py`, tests dédiés par fichier audité

**Interfaces:**
- Consumes: la liste exacte des 6 regex de `route_group()` et des 4
  éléments de `main.py` (spec §1.4, reproduite ci-dessous).

- [ ] **Step 1 : écrire les tests de régression AVANT de toucher les regex**

Pour chaque mécanisme, un test qui prouve qu'il fonctionne encore une fois
les routes sous `/v1` :

- **Rate-limit** : POST répété sur `/v1/collections/empty` déclenche bien
  un 429 après le seuil (test caractéristique existant probablement déjà
  présent pour `/collections/empty` non préfixé — l'adapter, pas en écrire
  un deuxième).
- **CORS appexport** : une requête OPTIONS sur `/v1/collections/{id}`
  reçoit toujours `Access-Control-Allow-Origin: *` (si `CORE_APPEXPORT_ENABLED`
  actif dans l'environnement de test).
- **Garde lecture-seule** : en mode démo (`is_read_only_mode()` vrai), un
  POST sur `/v1/collections/{id}/items` est bien bloqué (403) mais un appel
  à `/mcp` ou `/v1/analytics/sql` reste exempté (comportement inchangé,
  chemin `/mcp` non préfixé, `/analytics/sql` désormais `/v1/analytics/sql`
  dans l'exemption elle-même — Step 3 doit corriger CETTE ligne aussi).

```bash
cd core && uv run pytest tests/test_ratelimit.py tests/test_main.py -k "v1 or empty or readonly" -v
# attendu : ÉCHEC sur au moins le cas rate-limit/collections-empty
# (la regex ne matche pas encore /v1/collections/empty)
```

- [ ] **Step 2 : mettre à jour les 4 éléments de `main.py`**

`_AGGREGATE_PATH_RE`, `_EXPORT_PATH_RE`, `_APPEXPORT_CORS_PATH_RE`,
`_APPEXPORT_CORS_RULES` : préfixer chaque alternative de `/v1`.
`read_only_guard` : `!= "/analytics/sql"` devient `!= "/v1/analytics/sql"` ;
`!= "/mcp"` **ne change pas**.

- [ ] **Step 3 : mettre à jour les 6 regex de `limiter.py::route_group()`**

`_SQL_RE`, `_HARVEST_RE`, `_COLLECTIONS_EMPTY_RE`, `_ARCGIS_LIVE_QUERY_RE`,
`_WEBHOOK_TRIGGER_RE` : préfixer de `/v1`. `_LLM_RE` :
`r"^/mcp$|^/copilot/turn$"` devient `r"^/mcp$|^/v1/copilot/turn$"` — **seule
la seconde alternative change**, vérifier avec un test dédié que les deux
comportements (LLM sur `/mcp` non préfixé, LLM sur `/v1/copilot/turn`
préfixé) sont bien reconnus.

```bash
cd core && uv run pytest tests/test_ratelimit.py tests/test_main.py -v
```

- [ ] **Step 4 : falsifier un des correctifs**

Retirer temporairement le `/v1` de `_COLLECTIONS_EMPTY_RE`, confirmer que le
test rate-limit de la Step 1 échoue (le 429 n'arrive plus), remettre.

- [ ] **Step 5 : auditer les 13 fichiers `CORE_BASE_URL`/`base_url`, un par
  un**

```bash
for f in core/app/admin_tools/routes.py core/app/analytics/duckdb_conn.py \
  core/app/appexport/jobs.py core/app/collections/routes.py \
  core/app/features/routes.py core/app/ingestion/importer.py \
  core/app/items/routes.py core/app/pipelines/connector_runtime.py \
  core/app/dcat/routes.py core/app/public/routes.py core/app/jobs/__init__.py; do
  echo "=== $f ==="; grep -n "CORE_BASE_URL\|base_url" "$f"
done
```

Pour chaque occurrence trouvée : lire le contexte (à quelle route l'URL
construite pointe-t-elle ?) et décider — si la route pointée est désormais
sous `/v1` (cas le plus fréquent attendu : vignettes d'item, liens STAC/DCAT
self, proxy de pièce jointe, liens de notification, export appexport),
ajouter `/v1` au segment construit ; si elle pointe vers `/mcp` (aucun cas
attendu dans cette liste — `mcp_loopback.py`/`mcp/server.py` sont déjà
exclus de cette liste) ou vers une URL non-API, ne pas y toucher — le
documenter en commentaire si le choix n'est pas évident à la relecture.

- [ ] **Step 6 : test de chacun des fichiers modifiés**

```bash
cd core && uv run pytest -k "thumbnail or stac or dcat or attachment or notification or appexport" -v
```

- [ ] **Step 7 : suite complète du cœur + régénération OpenAPI/types TS si
  un schéma de réponse a changé de valeur (pas de forme)**

```bash
cd core && uv run pytest
```

- [ ] **Step 8 : commit**

```bash
git add core/app/main.py core/app/ratelimit/limiter.py core/app/*/routes.py \
  core/app/*/jobs.py core/app/ingestion/importer.py core/app/pipelines/connector_runtime.py \
  core/app/analytics/duckdb_conn.py core/app/jobs/__init__.py core/tests/
git commit -m "$(cat <<'EOF'
fix(core): met à jour les chemins bruts hors routage FastAPI après /v1

Rate-limit (route_group), CORS appexport, garde lecture-seule
(main.py) et les URLs absolues construites via CORE_BASE_URL/
CORE_INTERNAL_BASE_URL dans 13 modules — aucun de ces mécanismes ne
participe au routage FastAPI, donc la Tâche précédente (routeur /v1
imbriqué) ne les mettait pas à jour automatiquement. /mcp reste
inchangé partout (mcp_loopback.py, mcp/server.py, _LLM_RE, garde
lecture-seule).
EOF
)"
```

---

## Task 5 : infra Traefik (GAP-14 5.3)

**Files:**
- Modify: `docker-compose.yml` (3 labels)

- [ ] **Step 1 : mettre à jour les 3 labels identifiés**

```
traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/v1/admin-tools/verify
traefik.http.middlewares.seo-static-rewrite.replacepathregex.replacement=/v1/public/$$1
traefik.http.middlewares.seo-bots-rewrite.replacepathregex.replacement=/v1/public/sites/$$1/social-preview
```

- [ ] **Step 2 : vérifier par valeur (piège CLAUDE.md n°2)**

```bash
docker compose config | grep -A2 "admin-auth.forwardauth\|seo-static-rewrite.replacepathregex\|seo-bots-rewrite.replacepathregex"
```

- [ ] **Step 3 : vérification manuelle contre une stack réelle**

```bash
docker compose up -d --build core traefik shell martin titiler
curl -s http://localhost/sitemap.xml | head -5
curl -s -A "facebookexternalhit/1.1" http://localhost/sites/<slug-existant>
# Passerelle admin (SP-32) : un lancement de jeton HMAC réel suivi d'un
# accès à /admin/martin doit toujours aboutir (forwardAuth pointe
# maintenant vers /v1/admin-tools/verify) — vérifier le flux complet, pas
# seulement que core répond sur ce chemin isolément.
```

Documenter le résultat réel dans le ledger de session (ne jamais clore sur
la seule lecture de `docker compose config`, cf. précédent SP-55).

- [ ] **Step 4 : commit**

```bash
git add docker-compose.yml
git commit -m "$(cat <<'EOF'
fix(infra): met à jour les 3 labels Traefik qui ciblent le cœur après /v1

admin-auth (passerelle admin SP-32), seo-static-rewrite et
seo-bots-rewrite (sitemap/robots/aperçu social SP-55) pointaient vers
des chemins core désormais sous /v1 — vérifié contre une stack réelle,
pas seulement docker compose config.
EOF
)"
```

---

## Task 6 : shell — redéfinition unique de `coreUrl` (GAP-14 5.3)

**Files:**
- Modify: `shell/src/api/base.ts::createBase()`
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Produces: `ItemClientBase.coreUrl` porte désormais `${opts.coreUrl}/v1`.

- [ ] **Step 1 : écrire le test caractéristique (avant le code)**

Dans `itemClient.test.ts` : `createItemClient({ coreUrl: "https://core.test",
... })` puis un appel qui déclenche `request()` (ex. `listItems()`) —
vérifier que `fetch` est appelé avec `https://core.test/v1/items` (pas
`https://core.test/items`). Un test pour `getCoreUrl()` : doit renvoyer
`"https://core.test/v1"` (le test existant
`itemClient.test.ts:3790` — « getCoreUrl exposes the client's configured
core API origin » — attend aujourd'hui `"https://core.test"` : **ce test
doit être mis à jour intentionnellement**, ce n'est pas une régression mais
le nouveau contrat).

```bash
cd shell && npm run test -- itemClient -t "v1|getCoreUrl"
# attendu : ÉCHEC (coreUrl pas encore versionné)
```

- [ ] **Step 2 : implémenter**

```ts
export function createBase(opts: { coreUrl: string; getToken: () => string | undefined }): ItemClientBase {
  const coreUrl = `${opts.coreUrl}/v1`;
  // request()/requestBlob() utilisent coreUrl (fermeture), inchangés sinon
  ...
  return { coreUrl, request, requestBlob, ... };
}
```

- [ ] **Step 3 : vérifier `isHostedCoreUrl` (MapView) reste cohérent**

`MapView.test.tsx` construit déjà des cas avec `getCoreUrl={() =>
"https://hote.test/api"}` (ligne 1195, cas qui a motivé le correctif SP-24
C1) — ajouter un cas `getCoreUrl={() => "https://hote.test/api/v1"}` (le
nouveau contrat réel une fois le shell branché sur un `coreUrl` déjà
versionné) et vérifier que la détection d'URL hébergée fonctionne toujours
(le token d'auth est bien attaché à une URL de tuile qui commence par
`https://hote.test/api/v1/collections/...`).

```bash
cd shell && npm run test -- MapView -t "hosted|v1"
```

- [ ] **Step 4 : suite complète du client (les 4 autres fichiers de domaine
  qui construisaient leur propre `fetch` — layers.ts, exportsIngestion.ts,
  extensionsAdminTools.ts, items.ts, features.ts — n'ont besoin d'AUCUNE
  édition, c'est le point du design : vérifier que c'est bien le cas)**

```bash
cd shell && npm run test
```

Si un de ces 5 fichiers échoue, c'est le signe qu'il construit son URL
autrement qu'en lisant `coreUrl` depuis l'objet `base` — investiguer avant
de corriger à la main dans ce fichier (ça voudrait dire que le design §2.4
de la spec a une exception non prévue).

- [ ] **Step 5 : falsifier**

Revenir temporairement à `const coreUrl = opts.coreUrl;` (sans `/v1`),
confirmer que le test de la Step 1 échoue, remettre.

- [ ] **Step 6 : commit**

```bash
git add shell/src/api/base.ts shell/src/api/itemClient.test.ts shell/src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): coreUrl porte désormais le préfixe /v1 (point unique)

Un seul point de redéfinition (createBase()) couvre tous les
consommateurs (request()/requestBlob() ET les 5 fichiers de domaine
qui construisent leur propre fetch avec coreUrl) sans les éditer
individuellement — même discipline que ce que isHostedCoreUrl
(MapView, SP-24 C1) impose déjà : build et vérification d'une URL
hébergée doivent lire le même champ pour ne jamais diverger.
EOF
)"
```

---

## Task 7 : migration des mocks de test (GAP-14 5.3)

**Files:**
- Modify: 28 fichiers `shell/e2e/*.spec.ts` (80 occurrences de
  `page.route("https://core.test/...")`), jusqu'à 39 fichiers
  `shell/src/**/*.test.ts(x)` référençant `core.test`

**Interfaces:**
- Consumes: aucune (migration de test pure).

- [ ] **Step 1 : lister précisément les occurrences à traiter**

```bash
grep -rn 'page.route("https://core.test' shell/e2e/*.spec.ts > /tmp/e2e-mocks.txt
wc -l /tmp/e2e-mocks.txt
grep -rln "core.test" shell/src --include=*.test.ts --include=*.test.tsx > /tmp/vitest-core-test.txt
wc -l /tmp/vitest-core-test.txt
```

- [ ] **Step 2 : exclure les faux positifs avant toute substitution**

Certains mocks ciblent une URL **non-API** (upload S3 présigné,
`shell/e2e/attachments.spec.ts:45: page.route("http://localhost/upload", ...)`)
— ne pas les toucher. Filtrer `/tmp/e2e-mocks.txt` pour ne garder que les
chemins qui correspondent à une route réelle du cœur (`/items`,
`/collections`, `/instance`, `/extensions`, `/harvest`, `/usage`,
`/pipelines`, `/configs`, `/groups`, etc. — pas `localhost/upload` ni tout
autre domaine qui n'est pas `core.test`).

- [ ] **Step 3 : substitution mécanique dans `shell/e2e/*.spec.ts`**

```bash
for f in $(cut -d: -f1 /tmp/e2e-mocks.txt | sort -u); do
  sed -i 's#page\.route("https://core\.test/#page.route("https://core.test/v1/#g' "$f"
done
```

Puis relire chaque fichier modifié pour repérer une éventuelle substitution
malvenue (ex. un commentaire qui contenait la même chaîne, un mock qui
visait délibérément un chemin non préfixé pour tester le 404 de la Task 3
Step 1 — improbable côté E2E mais à vérifier).

- [ ] **Step 4 : audit des 39 fichiers Vitest**

Contrairement aux specs E2E (mocks `page.route` à chemin exact), les tests
Vitest mockent `fetch` de façons variées (`vi.fn()`, assertions sur l'URL
appelée via `expect(fetchMock).toHaveBeenCalledWith(...)`, parfois une
correspondance partielle). Traiter au cas par cas — un `grep -n "core.test"`
par fichier pour voir s'il s'agit d'une URL exacte à corriger ou d'une
correspondance partielle déjà tolérante au changement.

```bash
for f in $(cat /tmp/vitest-core-test.txt); do echo "=== $f ==="; grep -n "core.test" "$f"; done | less
```

- [ ] **Step 5 : suite complète**

```bash
cd shell && npm run test
cd shell && npm run e2e
```

- [ ] **Step 6 : grep final de vérification — aucune occurrence orpheline**

```bash
grep -rn 'core\.test/[a-zA-Z]' shell/e2e/*.spec.ts shell/src/**/*.test.ts shell/src/**/*.test.tsx 2>/dev/null \
  | grep -v '/v1/' | grep -v "localhost/upload"
# attendu : vide (ou seulement des faux positifs déjà identifiés Step 2)
```

- [ ] **Step 7 : commit**

```bash
git add shell/e2e/ shell/src/
git commit -m "$(cat <<'EOF'
test(shell): migre les mocks de test vers /v1 (GAP-14, contrat 5/5)

80 occurrences sur 28 specs E2E (page.route absolu sur core.test) +
audit des 39 fichiers Vitest référençant core.test — les mocks E2E en
glob (**/chemin*) n'avaient pas besoin de modification, seuls les
mocks à URL absolue devaient changer.
EOF
)"
```

---

## Clôture de plan

- [ ] **Suite complète finale** :

```bash
cd core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports \
  && uv run pytest \
  && uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold \
  && npm run e2e
uvx pre-commit run --all-files
```

- [ ] **Vérification manuelle finale contre une stack réelle** (piège
  CLAUDE.md n°4, ne pas se contenter des tests unitaires) :

```bash
docker compose up -d --build
curl -s http://localhost:8200/health          # doit répondre, non préfixé
curl -s http://localhost:8200/v1/items -H "Authorization: Bearer <jeton test>"  # doit répondre
curl -s http://localhost:8200/items           # doit répondre 404
```

- [ ] **Documenter dans le suivi de clôture** le résultat réel de la
  vérification Traefik (Task 5, Step 3) et de la vérification stack
  ci-dessus.
- [ ] **Mettre à jour `CLAUDE.md`** (`### Livré`) avec une ligne SP-57b :
  API du cœur versionnée sous `/v1/` (31 routeurs, `/health`/`/mcp` hors
  versionnement), `docs/adr/` créé (11 ADR rétroactifs), gabarits GitHub +
  `SECURITY.md` (le guide de contribution lui-même, `CONTRIBUTING.md`,
  existait déjà depuis SP-9 — GAP-14 se trompait sur ce point, à noter
  explicitement).

# SP-9 — Sécurité minimale : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un ingress Traefik réellement fonctionnel (`Host(DOMAIN)`, en-têtes de
sécurité, rate limiting, dashboard non exposé) ; la couverture authz existante
auditée avec tout trou réel comblé par un test qui le prouve d'abord rouge ;
les dépendances cœur et shell auditées à chaque CI, bloquantes sur
High/Critical.

**Architecture:** Labels Traefik ajoutés directement sur les services `core`
et `shell` de `docker-compose.yml` (pas de fichier de config dynamique
séparé) — deux routers distingués par `Host`+`PathPrefix`, deux middlewares
partagés (`security-headers`, `rate-limit`) déclarés une fois sur `core` et
référencés `@docker` par les deux routers, un middleware `strip-api` propre à
`core`. Revue authz : audit méthodique des endpoints REST + outils MCP contre
les fichiers de test existants, tout trou comblé par un test rouge→vert dans
le fichier de test le plus proche (jamais un nouveau fichier fourre-tout).
Audit dépendances : deux jobs CI indépendants (`core-deps-audit` via
`pip-audit`, `shell-deps-audit` via `npm audit` derrière un petit script de
filtrage accepted-risk, nécessaire pour une vulnérabilité réelle déjà
présente et sans correctif, découverte en écrivant ce plan).

**Tech Stack:** Traefik v3.0 (déjà l'image du compose), pytest/FastAPI
TestClient (cœur), `pip-audit`, `npm audit`, Node.js (script de filtrage).

## Global Constraints

- `DOMAIN` et `ACME_EMAIL` existent déjà dans `.env.example` — aucune
  nouvelle variable d'environnement à documenter (spec §2).
- **`VITE_CORE_URL` reste baké au build par défaut sur `localhost`** — limitation
  déjà actée et explicitement hors périmètre dans
  `2026-07-15-sp9-ci-publique-release-design.md` §2 (configuration runtime du
  shell publié = un vrai chantier séparé). Cette sous-partie **ne modifie pas**
  les `args:` de build du service `shell` dans `docker-compose.yml` : le
  câblage Traefik est fonctionnel pour router `Host(DOMAIN)` vers `shell`/
  `core`, mais un déploiement public réel qui veut que le shell appelle le
  cœur via `https://${DOMAIN}/api` doit reconstruire l'image `shell` avec
  `--build-arg VITE_CORE_URL=https://${DOMAIN}/api` séparément — à documenter
  dans une future itération runtime-config, pas ici.
- `--api.dashboard=true` et `--api.insecure=true` sont retirés entièrement du
  `command:` de `traefik`, et le port `8090:8080` est retiré des `ports:` —
  aucun dashboard authentifié ne les remplace en v1 (hors périmètre, spec §2) ;
  diagnostic via `docker compose logs traefik` uniquement.
- Pas de CSP stricte, pas de WAF/fail2ban, pas de SAST/DAST en CI, pas de
  chiffrement au repos applicatif — tous explicitement hors périmètre v1
  (spec §2, à ne pas implémenter dans ce plan).
- **Revue authz : le périmètre réel dépasse les 8 fichiers cités par la spec**
  (qui étaient illustratifs, pas exhaustifs — vérifié en listant
  `core/tests/` en écrivant ce plan : ~25 fichiers de test couvrent tout ou
  partie des 44 endpoints REST + 11 outils MCP). Task 2 ci-dessous donne la
  liste réelle et complète des deux (endpoints et fichiers de test associés).
  Tout trou réel comblé dans le fichier de test existant le plus proche du
  module concerné — jamais un nouveau `test_security_audit.py`.
- **`pip-audit` n'a pas de filtre de sévérité natif** (vérifié en écrivant ce
  plan : la sortie `--format json` ne porte aucun champ de sévérité agrégée
  fiable au-delà du texte de l'avis OSV/PyPI) — `core-deps-audit` bloque donc
  sur **toute** vulnérabilité connue trouvée, pas seulement High/Critical.
  Déviation assumée et documentée (la spec §3.3 laissait ce point ouvert,
  « à affiner en tâche ») ; zéro vulnérabilité connue dans les dépendances de
  `core/` au moment de l'écriture de ce plan (2026-07-16, `uv run pip-audit`
  exécuté réellement).
- **`npm audit --audit-level=high` échoue aujourd'hui réellement** (vérifié en
  écrivant ce plan) sur une vulnérabilité High préexistante et sans correctif :
  `lodash-es` (GHSA-r5fr-rjxr-66jc + 2 avis modérés liés) via
  `cel-js@0.8.2` → `chevrotain@11.0.3`, dépendance de production actée en
  SP-5a (moteur d'expressions CEL). `chevrotain` 11.0.3 est la dernière
  version publiée et n'a pas de correctif disponible pour cette chaîne.
  `shell-deps-audit` passe donc par un petit script
  (`shell/scripts/check-npm-audit.mjs`) qui lit la sortie JSON de `npm audit`
  et ignore uniquement les vulnérabilités listées dans une allowlist
  documentée en dur dans le script (aujourd'hui : `lodash-es` seul) — toute
  autre vulnérabilité High/Critical reste bloquante. Déviation assumée du
  snippet littéral de la spec (`npm audit --audit-level=high` nu), justifiée
  par ce blocage réel et vérifié, pas supposé.
- Baseline de non-régression actuelle (cf. `CLAUDE.md`, plus récente que les
  chiffres §6 de la spec qui datent d'avant les autres sous-parties SP-9
  déjà livrées) : **387 tests cœur passed/64 skipped, 466 tests shell, 36/36
  specs E2E**. Ces chiffres augmentent seulement du nombre de tests réels
  ajoutés en Task 2 (pas de chiffre fixé à l'avance).
- Docs et rapports en français, code/identifiants en anglais (`CLAUDE.md`).
- Prouver qu'un job CI bloque réellement (Tasks 3/4, spec §5) suppose de
  pousser une dépendance jetable connue-vulnérable sur une branche
  disposable et d'observer un run CI réel échouer, puis de la retirer — une
  action visible sur le dépôt distant : **à confirmer explicitement avec
  l'utilisateur avant de pousser**, jamais lancée de façon autonome (même
  règle que `2026-07-16-sp9-ci-publique-release.md`).

---

## File Structure

- Modify `docker-compose.yml` — labels Traefik sur `core`/`shell`, retrait
  dashboard/insecure sur `traefik`.
- Modify un sous-ensemble (déterminé par l'audit) de `core/tests/*.py` —
  tests rouge→vert pour tout trou authz réel trouvé.
- Create `docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md`
  — rapport de revue authz (matrice de couverture + trous trouvés/corrigés).
- Modify `core/pyproject.toml` (+ `core/uv.lock`) — ajoute `pip-audit` en
  dev-dependency.
- Modify `.github/workflows/ci.yml` — ajoute les jobs `core-deps-audit` et
  `shell-deps-audit`.
- Create `shell/scripts/check-npm-audit.mjs` — filtre accepted-risk pour
  `npm audit --json`.

---

### Task 1: Câblage Traefik minimal (labels, en-têtes, rate limiting, retrait dashboard)

**Files:**
- Modify: `docker-compose.yml` (services `core`, `shell`, `traefik`)

**Interfaces:**
- Consumes: `${DOMAIN}`/`${ACME_EMAIL}` (déjà dans `.env.example`, inchangés).
- Produces: rien consommé par une tâche suivante (les tâches 2-4 sont
  indépendantes de celle-ci).

- [ ] **Step 1: Lire le fichier actuel pour confirmer les blocs exacts à modifier**

```bash
cat docker-compose.yml
```

Confirmer l'absence actuelle de tout label `traefik.*` sur `core`/`shell`, et
la présence de `--api.dashboard=true` / `--api.insecure=true` / `"8090:8080"`
sur le service `traefik` (état vérifié en écrivant ce plan — si un autre
commit a changé ce fichier entretemps, adapter les blocs ci-dessous à l'état
réel plutôt qu'à ces numéros de ligne).

- [ ] **Step 2: Ajouter les labels Traefik au service `core`**

Remplacer, dans le service `core` :

```yaml
    depends_on: [pgbouncer, minio]
    restart: unless-stopped

  # Worker d'ingestion (SP-6a) — même image que le cœur, process séparé
```

par :

```yaml
    depends_on: [pgbouncer, minio]
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.core.rule=Host(`${DOMAIN}`) && PathPrefix(`/api`)
      - traefik.http.routers.core.entrypoints=websecure
      - traefik.http.routers.core.tls.certresolver=letsencrypt
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

  # Worker d'ingestion (SP-6a) — même image que le cœur, process séparé
```

Notes :
- `priority=10` : force `core` à gagner face à `shell` sur une même URL
  (`Host(DOMAIN)` seul matcherait aussi `/api/...` sans cette priorité
  explicite — Traefik calcule une priorité automatique basée sur la longueur
  de la règle, mais un ordre explicite est plus sûr et déjà recommandé par la
  documentation Traefik officielle).
- `strip-api` : le cœur route lui-même ses endpoints à la racine (`/me`,
  `/items`, `/collections`, …) — `/api` n'existe que côté Traefik/client
  public, retiré avant que la requête n'atteigne le conteneur `core`.
- `security-headers`/`rate-limit` sont **définis** ici (sur `core`) et
  **référencés** par les deux routers via le suffixe `@docker` — pattern
  Traefik standard pour un middleware partagé entre plusieurs conteneurs du
  même provider Docker.

- [ ] **Step 3: Ajouter les labels Traefik au service `shell`**

Remplacer :

```yaml
  shell:
    build: ./shell
    ports:
      - "8300:8300"
    networks: [gis-net]
    restart: unless-stopped
```

par :

```yaml
  shell:
    build: ./shell
    ports:
      - "8300:8300"
    networks: [gis-net]
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.shell.rule=Host(`${DOMAIN}`)
      - traefik.http.routers.shell.entrypoints=websecure
      - traefik.http.routers.shell.tls.certresolver=letsencrypt
      - traefik.http.routers.shell.priority=1
      - traefik.http.routers.shell.middlewares=security-headers@docker,rate-limit@docker
      - traefik.http.services.shell.loadbalancer.server.port=8300
```

- [ ] **Step 4: Retirer le dashboard non authentifié du service `traefik`**

Remplacer :

```yaml
    command:
      - --api.dashboard=true
      - --api.insecure=true
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
```

par :

```yaml
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
```

Et remplacer :

```yaml
    ports:
      - "80:80"
      - "443:443"
      - "8090:8080"
```

par :

```yaml
    ports:
      - "80:80"
      - "443:443"
```

- [ ] **Step 5: Valider la syntaxe du compose**

```bash
./scripts/bootstrap-env.sh   # no-op si .env existe déjà
docker compose config >/dev/null && echo "compose config OK"
```

Expected: `compose config OK`. Vérifier aussi dans la sortie complète
(`docker compose config`) que `traefik.http.routers.core.rule` s'est bien
résolu en `Host(\`<valeur réelle de DOMAIN>\`) && PathPrefix(\`/api\`)` — la
substitution `${DOMAIN}` doit avoir eu lieu avant que Traefik ne voie le
label.

- [ ] **Step 6: Vérification manuelle en conditions réelles (en-têtes + rate limit + routage)**

Sans domaine public ni certificat Let's Encrypt réel disponible en local, on
utilise `curl --resolve` pour forcer un `Host` de test vers `127.0.0.1` et
`-k` pour ignorer le certificat auto-signé de repli de Traefik (ACME échouera
silencieusement en local faute de DNS réel — attendu, sans impact sur les
en-têtes/le rate limiting, qui sont indépendants du certificat).

```bash
DOMAIN=gis.test.local docker compose up -d traefik core shell
docker compose ps traefik core shell   # attendre "Up"/"healthy" sur les dépendances de core
```

En-têtes de sécurité (shell) :

```bash
curl -k -s -D - -o /dev/null --resolve gis.test.local:443:127.0.0.1 https://gis.test.local/ \
  | grep -iE 'strict-transport-security|x-content-type-options|x-frame-options'
```

Expected : les trois en-têtes présents (`Strict-Transport-Security: max-age=31536000`,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`).

Routage + priorité + strip-prefix (core, anonyme) :

```bash
curl -k -s -o /dev/null -w '%{http_code}\n' --resolve gis.test.local:443:127.0.0.1 https://gis.test.local/api/me
```

Expected : `401` (pas `404`) — preuve que `PathPrefix(/api)` a bien gagné sur
`Host` seul (priorité) et que `strip-api` a bien retiré le préfixe avant que
`core` ne route `/me`.

Rate limiting (rafale parallèle — un `curl` séquentiel est trop lent pour
dépasser `average=100`/`burst=200` en pratique) :

```bash
seq 1 500 | xargs -P 50 -I{} curl -k -s -o /dev/null -w '%{http_code}\n' \
  --resolve gis.test.local:443:127.0.0.1 https://gis.test.local/ | sort | uniq -c
```

Expected : au moins un `429` dans la sortie (le ratio exact 200/429 dépend du
timing d'exécution — le critère de réussite est la présence d'au moins un
`429`, pas un ratio précis, conforme au critère d'acceptation §6 de la spec).

Dashboard non exposé :

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8090 2>&1 || echo "connexion refusée (attendu)"
```

Expected : échec de connexion (port retiré du compose), pas une réponse HTTP.

Nettoyage :

```bash
docker compose down
```

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: câblage Traefik minimal (en-têtes de sécurité, rate limiting, retrait du dashboard)"
```

---

### Task 2: Revue authz — audit complet + comblement des trous réels

**Files:**
- Modify: sous-ensemble de `core/tests/*.py` déterminé par l'audit (voir
  liste de fichiers candidats ci-dessous — aucun nouveau fichier créé)
- Create: `docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md`

**Interfaces:**
- Consumes: rien des tâches précédentes.
- Produces: rien consommé par une tâche suivante.

**Contexte vérifié en écrivant ce plan (pas une supposition) :** la spec cite
8 fichiers de test comme couverture existante à auditer
(`test_auth.py`, `test_sharing_authorization.py`, `test_sharing_acceptance.py`,
`test_sharing_routes.py`, `test_collections_authorization.py`,
`test_collections_sharing_routes.py`, `test_mcp_auth.py`,
`test_mcp_tools_sharing.py`) — c'est une liste illustrative, pas exhaustive.
`core/tests/` contient en réalité ~70 fichiers de test ; la liste complète
pertinente pour cet audit (endpoints REST + outils MCP, avec leur(s)
fichier(s) de test associé(s) le(s) plus proche(s)) est celle-ci :

| Module (`core/app/…`) | Endpoints | Fichier(s) de test à auditer |
|---|---|---|
| `configs/routes.py` | `POST /configs`, `GET /configs/{id}`, `PUT /configs/{id}`, `GET /configs/{id}/revisions`, `POST /configs/{id}/rollback`, `DELETE /configs/{id}`, `GET /configs/by-item/{item_id}`, `PUT /configs/by-item/{item_id}`, `DELETE /configs/by-item/{item_id}`, `DELETE /items/{item_id}` | `test_routes.py`, `test_configs_extension_permissions.py` |
| `collections/routes.py` | `POST /collections`, `GET /collections`, `GET /collections/candidates`, `GET /collections/{id}`, `GET /collections/{id}/schema`, `PATCH /collections/{id}`, `DELETE /collections/{id}`, `GET /collections/{id}/sharing`, `PUT /collections/{id}/sharing` | `test_collections_routes.py`, `test_collections_authorization.py`, `test_collections_sharing_routes.py`, `test_collections_candidates_integration.py` |
| `auth/routes.py` | `GET /me`, `GET /users`, `PATCH /users/{id}` | `test_me.py`, `test_users.py`, `test_users_admin_routes.py`, `test_admin_bootstrap.py` |
| `items/routes.py` | `GET /items`, `GET /items/{id}`, `PATCH /items/{id}`, `POST /items/{id}/thumbnail`, `GET /items/{id}/thumbnail`, `GET /items/{id}/sharing`, `PUT /items/{id}/sharing` | `test_items_routes.py` |
| `features/routes.py` (OGC API Features) | `GET /`, `GET /conformance`, `GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`, `POST /collections/{id}/items`, `PUT /collections/{id}/items/{fid}`, `DELETE /collections/{id}/items/{fid}` | `test_features_routes_read.py`, `test_features_routes_write.py`, `test_features_rls.py`, `test_features_integration.py`, `test_ogc_discovery.py` |
| `ingestion/routes.py` | `POST /uploads/presign`, `POST /uploads/inspect`, `POST /uploads`, `GET /uploads/{job_id}` | `test_ingestion_routes.py` |
| `sharing/routes.py` | `GET /groups`, `POST /groups`, `POST /groups/{id}/members` | `test_sharing_routes.py`, `test_sharing_authorization.py`, `test_sharing_acceptance.py` |
| `public/routes.py` (accès anonyme) | `GET /items/{id}`, `GET /configs/by-item/{id}` | `test_public_routes.py` |
| `extensions/routes.py` | `POST /extensions`, `PATCH /extensions/{id}`, `GET /extensions` | `test_extensions_routes.py`, `test_configs_extension_permissions.py`, `test_mcp_tools_extension_permissions.py` |
| Outils MCP (`app/mcp/tools.py`) | `whoami`, `list_items`, `search_catalog`, `query_features`, `get_item`, `get_app_config`, `save_app_config`, `create_item`, `create_form_app`, `get_sharing`, `set_sharing` | `test_mcp_auth.py`, `test_mcp_routes.py`, `test_mcp_schema.py`, `test_mcp_tools_items.py`, `test_mcp_tools_configs.py`, `test_mcp_tools_create.py`, `test_mcp_tools_create_form_app.py`, `test_mcp_tools_sharing.py`, `test_mcp_tools_search.py`, `test_mcp_tools_query_features.py`, `test_mcp_tools_extension_permissions.py`, `test_mcp_form_app.py` |
| Recherche sémantique (SP-7, transverse) | scoring dans `list_items`/`search_catalog` | `test_search_ranking.py`, `test_search_providers.py` |

Vérifier cette liste au moment de l'exécution (les routes ont pu changer) :

```bash
grep -rn "@router\.\(get\|post\|put\|patch\|delete\)" app --include="routes.py"
```

Si la sortie diffère de la liste ci-dessus, c'est elle qui fait foi — mettre
à jour la matrice en conséquence.

- [ ] **Step 1: Créer le rapport et y consigner la matrice de couverture**

Créer `docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md`
avec cette structure (une ligne par endpoint/outil, remplie au fur et à
mesure de l'audit — ne pas pré-remplir de valeurs, les déterminer réellement
en lisant chaque fichier de test) :

```markdown
# SP-9 — Sécurité minimale : revue authz

Méthode : pour chaque endpoint/outil ci-dessous, vérifié dans son/ses
fichier(s) de test associé(s) l'existence d'un test couvrant : accès
autorisé (owner/partage), accès refusé (non-owner sans partage → 403/404
selon la convention déjà en place), accès anonyme si la route/l'outil le
permet, et — pour les modules ajoutés depuis SP-7/SP-8b/SP-8c (extensions,
recherche sémantique) — l'isolation cross-tenant.

| Endpoint / outil | Autorisé testé ? | Refusé (403/404) testé ? | Anonyme testé (si applicable) ? | Cross-tenant testé (si applicable) ? | Trou ? |
|---|---|---|---|---|---|
| ... une ligne par endpoint/outil du tableau ci-dessus ... | | | | | |

## Trous trouvés et corrigés

(une sous-section par trou réel, avec repro : commande pytest qui échouait
avant correctif, fichier/ligne du test ajouté, fichier/ligne du correctif
côté route/`can()` si un correctif de code a été nécessaire — sinon préciser
qu'il s'agissait uniquement d'un défaut de couverture sur un comportement
déjà correct)

## Conclusion

(nombre total de trous réels trouvés — 0 si aucun — et confirmation que les
tests ajoutés passent tous, cf. Step 4 ci-dessous)
```

- [ ] **Step 2: Auditer chaque module et remplir la matrice**

Pour chaque ligne du tableau de contexte ci-dessus, ouvrir le(s) fichier(s)
de test associé(s) et vérifier la présence de tests pour chacun des 4
critères de la colonne. Deux patrons de test existent déjà dans ce dépôt,
à identifier lequel s'applique à chaque module :

Patron route-level (`TestClient`, ex. `test_collections_sharing_routes.py`) :

```python
def test_sharing_requires_owner_or_admin(env):
    app, client, _, admin, regular, group_id = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    _as(app, regular)  # lisible (publique) mais pas partageable
    r = client.put("/collections/incidents/sharing", json={"public": True, "groups": []})
    assert r.status_code == 403
```

Patron unitaire sur `can()` (ex. `test_collections_authorization.py`) :

```python
def test_stranger_reads_public_collection_only(env):
    session, tenant, owner, other = env
    assert can(session, user_id=other.id, action="read",
               item=_facts(tenant, owner, public=True), kind="collection") is True
    assert can(session, user_id=other.id, action="read",
               item=_facts(tenant, owner), kind="collection") is False
```

Pour chaque endpoint/outil, noter dans la matrice ce qui est réellement
trouvé (pas supposé) — lire le fichier de test en entier, pas seulement les
noms des fonctions de test.

- [ ] **Step 3: Pour chaque trou trouvé, écrire un test rouge, l'exécuter, puis corriger**

Pour un trou de **couverture** sur un comportement déjà correct : écrire le
test manquant dans le fichier existant le plus proche, en suivant exactement
le patron déjà utilisé dans ce fichier (fixtures `env`/`client` identiques,
convention `_as(app, user)` pour changer d'utilisateur courant si le fichier
l'utilise déjà). L'exécuter :

```bash
uv run pytest tests/<fichier>.py::<nom_du_test> -v
```

Si le comportement est déjà correct, ce test devrait déjà passer une fois
écrit (il documente un comportement existant, pas un correctif) — dans ce
cas, le noter comme « couverture ajoutée, pas de trou de sécurité réel »
dans le rapport.

Pour un trou de **comportement** (le test révèle un vrai `200`/`204` là où un
`403`/`404` est attendu) : confirmer d'abord que le test échoue bien (RED) :

```bash
uv run pytest tests/<fichier>.py::<nom_du_test> -v
```

Expected: `FAILED` avec l'assertion de statut qui échoue. Puis corriger le
site concerné — soit le contrôle dans `<module>/routes.py` (garde
manquante, ex. absence de vérification `can()` avant une action), soit
`app/sharing/authorization.py` (`can()` lui-même, si la règle de permission
est incorrecte) — puis ré-exécuter :

```bash
uv run pytest tests/<fichier>.py::<nom_du_test> -v
```

Expected: `PASSED`.

- [ ] **Step 4: Suite complète — vérifier l'absence de régression**

```bash
uv run pytest
```

Expected: tous les tests passent, total = 387 + (nombre de tests ajoutés en
Step 3) passed, 64 skipped (sans `CORE_TEST_DATABASE_URL` — les tests
`postgis` restent skippés en environnement sans Postgres réel, comme pour
toutes les sous-parties SP-9 précédentes).

```bash
uv run lint-imports
```

Expected: pas d'erreur (aucune modification de ce plan ne touche les
frontières de modules).

- [ ] **Step 5: Finaliser le rapport et commit**

Compléter la section « Conclusion » du rapport (nombre de trous trouvés/
corrigés, ou confirmation explicite qu'aucun trou réel n'a été trouvé si
c'est le cas).

```bash
git add docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md tests/
git commit -m "test(core): revue authz — comble les trous réels trouvés dans la couverture existante"
```

(Si aucun trou n'a été trouvé et aucun test ajouté, commit uniquement le
rapport : `git add docs/superpowers/specs/2026-07-15-sp9-securite-minimale-revue-authz.md`.)

---

### Task 3: CI — `core-deps-audit` (pip-audit)

**Files:**
- Modify: `core/pyproject.toml`, `core/uv.lock`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: rien des tâches précédentes.
- Produces: rien consommé par une tâche suivante.

- [ ] **Step 1: Ajouter `pip-audit` en dev-dependency**

```bash
cd core
uv add --group dev "pip-audit>=2.7"
```

Vérifier le diff :

```bash
git diff pyproject.toml
```

Expected : une ligne ajoutée dans `[dependency-groups] dev`, `uv.lock`
régénéré automatiquement par la commande (pas d'édition manuelle).

- [ ] **Step 2: Vérifier que l'audit passe aujourd'hui**

```bash
uv run pip-audit --strict
```

Expected : `No known vulnerabilities found` (état vérifié en écrivant ce
plan, 2026-07-16 — si une vulnérabilité réelle apparaît d'ici l'exécution de
cette tâche, traiter au cas par cas : bump de version si un correctif existe ;
sinon appliquer le même patron accepted-risk documenté que Task 4 pour le
shell, en ajoutant une exception explicite et justifiée plutôt qu'en
désactivant le job).

- [ ] **Step 3: Ajouter le job `core-deps-audit` à `ci.yml`**

Lire le fichier actuel pour confirmer la structure (jobs `migrations`,
`core`, `api-types-drift`, `shell`) :

```bash
cat .github/workflows/ci.yml
```

Ajouter le job suivant, à la suite du job `core` (avant `api-types-drift`) :

```yaml
  core-deps-audit:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: core
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run pip-audit --strict
```

(`--strict` : échoue si la résolution des dépendances échoue sur l'une
d'elles — pas un filtre de sévérité, cf. Global Constraints. `pip-audit`
n'ayant pas de notion de sévérité fiable, ce job bloque sur toute
vulnérabilité connue trouvée, pas seulement High/Critical.)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
cd ..
git add .github/workflows/ci.yml
git commit -m "ci: audit des dépendances Python (pip-audit, bloquant)"
```

- [ ] **Step 5: Prouver que le job bloque réellement (spec §5) — confirmation utilisateur requise avant de pousser**

Demander confirmation explicite avant cette étape (pousse sur une branche
distante et déclenche un run CI réel). Une fois confirmé :

```bash
git checkout -b sp9-securite-ci-dry-run
cd core
uv add "pyjwt==2.4.0"   # version ancienne, jetable, jamais commitée seule sur dev
cd ..
git add core/pyproject.toml core/uv.lock
git commit -m "test: dépendance jetable à vulnérabilité connue (dry-run core-deps-audit)"
git push -u origin sp9-securite-ci-dry-run
```

(Vérifié en écrivant ce plan : `uv run --with pip-audit --with "pyjwt==2.4.0"
pip-audit --strict` remonte réellement plusieurs advisories PYSEC non
corrigées avant 2.12.0/2.13.0 pour cette version — pas besoin de cibler un
CVE précis, `pyjwt==2.4.0` déclenche le job de façon fiable.)

Observer le run CI réel (`gh run watch` ou l'onglet Actions) : le job
`core-deps-audit` doit échouer sur les vulnérabilités connues de
`pyjwt==2.4.0`. Puis retirer la dépendance jetable et republier :

```bash
git reset --hard HEAD~1
git push --force origin sp9-securite-ci-dry-run
git checkout dev
git branch -D sp9-securite-ci-dry-run
git push origin --delete sp9-securite-ci-dry-run
```

(Branche et commit strictement jetables — jamais fusionnés dans `dev`.)

---

### Task 4: CI — `shell-deps-audit` (npm audit + allowlist accepted-risk)

**Files:**
- Create: `shell/scripts/check-npm-audit.mjs`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: rien des tâches précédentes.
- Produces: rien consommé par une tâche suivante.

**Contexte vérifié en écrivant ce plan (pas une supposition) :**
`npm audit --audit-level=high` échoue aujourd'hui (exit code `1`) sur
`lodash-es <=4.17.23` (High, `GHSA-r5fr-rjxr-66jc` + 2 avis modérés liés),
tiré transitivement par `cel-js@0.8.2` (dépendance de production, moteur
d'expressions CEL, arbitrage SP-5a) → `chevrotain@11.0.3` → `lodash-es`.
`npm audit` rapporte explicitement « No fix available » pour cette chaîne —
`chevrotain` 11.0.3 est la dernière version publiée. La sortie
`npm audit --json` expose un objet top-level `vulnerabilities`, une entrée
par paquet avec un champ `severity` (`"high"`/`"critical"`/…) — c'est sur ce
champ que le script filtre, pas sur les identifiants d'avis individuels
(plus simple, un paquet alloué reste alloué tant qu'il n'a pas de correctif,
quel que soit le nombre d'avis CVE qui le concernent).

- [ ] **Step 1: Écrire le script de filtrage**

Créer `shell/scripts/check-npm-audit.mjs` :

```javascript
#!/usr/bin/env node
// Filtre `npm audit --json` : bloque sur toute vulnérabilité High/Critical
// non listée dans ALLOWLIST. Un paquet alloué reste bloquant sur tout NOUVEAU
// paquet vulnérable — seule l'entrée exacte du nom de paquet est ignorée.
import { readFileSync } from "node:fs";

const ALLOWLIST = {
  "lodash-es":
    "Transitif via cel-js@0.8.2 -> chevrotain@11.0.3 (GHSA-r5fr-rjxr-66jc " +
    "et avis liés). Aucun correctif upstream : chevrotain 11.0.3 est la " +
    "dernière version publiée. Risque jugé faible : lodash-es n'est utilisé " +
    "qu'en interne par le parseur CEL (tokenisation), jamais avec un template " +
    "contrôlé par un utilisateur non fiable. Revu 2026-07-16 — à retirer dès " +
    "qu'un correctif existe en amont.",
};

const path = process.argv[2];
if (!path) {
  console.error("usage: check-npm-audit.mjs <npm-audit.json>");
  process.exit(2);
}

const report = JSON.parse(readFileSync(path, "utf-8"));
const vulnerabilities = report.vulnerabilities ?? {};

const blocking = [];
for (const [pkg, info] of Object.entries(vulnerabilities)) {
  if (info.severity !== "high" && info.severity !== "critical") continue;
  if (ALLOWLIST[pkg]) {
    console.log(`ignoré (accepted-risk documenté) : ${pkg} (${info.severity})`);
    continue;
  }
  blocking.push(`${pkg} (${info.severity})`);
}

if (blocking.length > 0) {
  console.error("Vulnérabilités High/Critical non couvertes par l'allowlist :");
  for (const b of blocking) console.error(`  - ${b}`);
  process.exit(1);
}

console.log("Aucune vulnérabilité High/Critical bloquante (hors accepted-risk documenté).");
```

- [ ] **Step 2: Vérifier le script contre l'état réel actuel (doit passer)**

```bash
cd shell
npm audit --audit-level=high --json > /tmp/npm-audit-check.json || true
node scripts/check-npm-audit.mjs /tmp/npm-audit-check.json; echo "exit: $?"
```

Expected : `ignoré (accepted-risk documenté) : lodash-es (high)` puis
`Aucune vulnérabilité High/Critical bloquante (hors accepted-risk documenté).`,
`exit: 0`.

- [ ] **Step 3: Vérifier que le script bloque bien sur une vulnérabilité non allowlistée**

```bash
node -e "
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('/tmp/npm-audit-check.json'));
d.vulnerabilities['some-other-pkg'] = { severity: 'critical' };
fs.writeFileSync('/tmp/npm-audit-check-2.json', JSON.stringify(d));
"
node scripts/check-npm-audit.mjs /tmp/npm-audit-check-2.json; echo "exit: $?"
rm -f /tmp/npm-audit-check.json /tmp/npm-audit-check-2.json
```

Expected : `Vulnérabilités High/Critical non couvertes par l'allowlist :`
suivi de `  - some-other-pkg (critical)`, `exit: 1` — preuve que le script
bloque bien sur un paquet réellement non couvert, pas seulement qu'il ignore
tout.

- [ ] **Step 4: Ajouter le job `shell-deps-audit` à `ci.yml`**

Ajouter le job suivant, à la suite du job `shell` :

```yaml
  shell-deps-audit:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: shell
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm ci
      - run: npm audit --audit-level=high --json > npm-audit.json || true
      - run: node scripts/check-npm-audit.mjs npm-audit.json
```

- [ ] **Step 5: Commit**

```bash
git add shell/scripts/check-npm-audit.mjs .github/workflows/ci.yml
git commit -m "ci: audit des dépendances npm (bloquant High/Critical, allowlist accepted-risk documentée)"
```

- [ ] **Step 6: Prouver que le job bloque réellement (spec §5) — confirmation utilisateur requise avant de pousser**

Demander confirmation explicite avant cette étape (pousse sur une branche
distante et déclenche un run CI réel) — branche dédiée, indépendante de celle
de Task 3 Step 5 (déjà nettoyée à ce stade) :

```bash
git checkout -b sp9-securite-ci-dry-run-shell
cd shell
npm install --save-exact minimist@1.2.5   # version ancienne avec CVE connue, non allowlistée, jetable
cd ..
git add shell/package.json shell/package-lock.json
git commit -m "test: dépendance jetable à vulnérabilité connue (dry-run shell-deps-audit)"
git push -u origin sp9-securite-ci-dry-run-shell
```

Observer le run CI réel : le job `shell-deps-audit` doit échouer — `minimist`
n'étant pas dans `ALLOWLIST`, `check-npm-audit.mjs` doit sortir en erreur
(`exit 1`) avec `minimist` listé dans les vulnérabilités non couvertes. Puis
nettoyer :

```bash
git reset --hard HEAD~1
git push --force origin sp9-securite-ci-dry-run-shell
git checkout dev
git branch -D sp9-securite-ci-dry-run-shell
git push origin --delete sp9-securite-ci-dry-run-shell
```

(Branche et commit strictement jetables — jamais fusionnés dans `dev`.)

---

## Validation finale (après les 4 tâches)

- [ ] `cd core && uv run pytest && uv run lint-imports` — vert, total ≥ 387
  passed (+ tests ajoutés en Task 2).
- [ ] `cd shell && npm run test && npm run build` — vert, 466 tests.
- [ ] `cd shell && npx playwright install --with-deps chromium && npm run e2e`
  — 36/36 specs vertes (aucune modification de ce plan ne touche le shell
  applicatif ni l'E2E — régression improbable, à confirmer tout de même).
- [ ] Pousser sur une branche et observer un run CI réel : les 6 jobs
  (`migrations`, `core`, `core-deps-audit`, `api-types-drift`, `shell`,
  `shell-deps-audit`) verts.

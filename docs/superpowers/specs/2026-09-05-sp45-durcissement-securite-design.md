# SP-45 — Durcissement sécurité immédiat : design

## 0. Cadrage

Ce SP referme 7 des manques identifiés par la revue globale SP-42
(`docs/revue/2026-09-04-analyse-gaps.md`) : GAP-02, GAP-41, GAP-58, GAP-61,
GAP-77, GAP-78, GAP-79. Choisis pour leur **faible coût unitaire** (0.1 à
2-4 j-h chacun, 5-10 j-h au total) et leur **faible risque** (aucun ne
touche un mécanisme partagé par un autre chantier en cours), **pas** pour un
mécanisme commun — les 7 tâches du plan associé sont indépendantes entre
elles et peuvent s'exécuter dans n'importe quel ordre.

Chaque manque a été **revérifié dans le code réel** avant d'écrire ce
document (piège CLAUDE.md n°3 : « le texte littéral d'un plan ou d'un brief
est régulièrement faux »). Deux corrections au texte de
`2026-09-04-analyse-gaps.md` sont apportées ci-dessous (§4, §7) — le
document original reste la bonne porte d'entrée thématique, mais deux de ses
affirmations chiffrées sont légèrement fausses.

**Hors périmètre, explicitement** : GAP-73 (quotas par tenant — un vrai
mécanisme de quota de ressources, 5-8 j-h, referme une classe de problème
différente et plus large que le rate-limit par route traité ici en GAP-58) ;
GAP-72 (CSP en enforcing) — cf. §9 ci-dessous, recommandé comme suite
logique de ce SP, jamais entamé ici ; les 35 « confort » et le reste des
« sérieux »/« production » du backlog SP-42 non listés dans le périmètre
ci-dessus.

## 1. GAP-02 — Garde d'egress absente sur l'appel LLM sortant du copilote

### Constat vérifié

`core/app/copilot/llm_provider.py:88-93` (`OpenAICompatibleLLMProvider.chat`,
branche `self._client is None`) construit un `httpx.AsyncClient` nu et poste
directement sur `self._api_url` (= `CORE_LLM_API_URL`, un réglage opérateur)
sans aucune validation d'URL. C'est la 4e surface sortante du dépôt et la
seule sans garde : moissonnage (`core/app/harvest/egress.py`), connecteurs
pipeline (`core/app/pipelines/egress.py`), webhooks d'alerte
(`core/app/alerts/egress.py`) en ont chacun une — dupliquée trois fois
plutôt que partagée, par choix architectural délibéré (voir ci-dessous).

### Pourquoi une 4e duplication plutôt qu'un import

Le contrat de couches (`core/pyproject.toml [[tool.importlinter.contracts]]`,
liste `layers`) place `app.copilot` **au-dessus** de `app.harvest` — à la
différence d'`app.pipelines` et `app.alerts`, tous deux **en dessous**
d'`app.harvest` et donc structurellement incapables de l'importer (raison
documentée dans leurs docstrings respectifs). `app.copilot` pourrait
légalement importer `app.harvest.egress.assert_egress_allowed` (vérifié :
`uv run lint-imports` passe sur l'état actuel, aucune règle ne l'interdirait).

Rejeté malgré tout, pour une raison de **correction**, pas de convention :
`app.harvest.egress.assert_egress_allowed` lit son allowlist depuis
`CORE_HARVEST_EGRESS_ALLOWLIST`, câblée en pratique sur les sources de
moissonnage créées par n'importe quel utilisateur privilégié. Importer cette
fonction telle quelle coifferait silencieusement l'allowlist du copilote
(réglage opérateur, un seul héberger LLM) sur celle du moissonnage (surface
multi-utilisateurs) — un opérateur qui autoriserait un hôte de moissonnage
autoriserait de facto le LLM à y poster, et réciproquement. Le point de test
`core/tests/test_deployability.py` documente déjà cette classe de piège
(variable qui « donne une fausse impression » de portée). Un module dédié
avec sa propre variable d'environnement suit donc le patron déjà établi par
`app.alerts.egress`/`app.pipelines.egress` (chacun sa propre allowlist), pour
la même raison qu'eux.

Différence technique avec les 3 gardes existantes : les trois utilisent un
client **synchrone** (`httpx.Client`/`requests.Session`) — le provider LLM
utilise `httpx.AsyncClient` par contrat (`LLMProvider.chat` est async :
un appel bloquant gèlerait la boucle d'événements du process, qui tourne
sans `--workers`). La garde dupliquée doit donc envelopper un
`httpx.AsyncBaseTransport`, pas un `httpx.BaseTransport` — nouveau, aucun des
trois modules existants n'a de variante async à copier telle quelle. La
fonction de validation (`assert_egress_allowed`, résolution DNS incluse) reste
elle-même synchrone comme dans les trois autres : c'est un appel rapide
(un `socket.getaddrinfo`), le même compromis que les gardes existantes.

### Fix

Nouveau module `core/app/copilot/egress.py`, dupliquant
`EgressBlockedError`/`_is_internal`/`assert_egress_allowed`
(env `CORE_LLM_EGRESS_ALLOWLIST`, nommée d'après les 3 variables
`CORE_LLM_*` déjà existantes plutôt que `CORE_COPILOT_*`), plus
`_GuardedAsyncTransport(httpx.AsyncBaseTransport)` et
`build_guarded_async_client()`. `OpenAICompatibleLLMProvider.chat` utilise ce
client dans sa branche `self._client is None` (le seul chemin réellement
emprunté en production — `get_llm_provider()` ne passe jamais `http_client`,
réservé aux tests). `EgressBlockedError` est en plus attrapée dans
`_run_turn` (`core/app/copilot/routes.py`), aux côtés de `McpLoopbackError`,
et mappée en 502 plutôt que de remonter en 500 non géré.

### Risque résiduel assumé (même limite que les 3 gardes existantes)

TOCTOU DNS-rebinding (la garde valide l'IP résolue avant la requête, httpx
re-résout au connect) — documenté et accepté par `harvest/egress.py`, même
choix ici. `CORE_LLM_API_URL` est un réglage opérateur (pas une entrée
utilisateur), donc la surface d'attaque réelle est plus étroite que pour le
moissonnage — un attaquant devrait déjà contrôler la configuration de
l'instance pour en tirer parti.

## 2. GAP-41 — Secret Martin généré, jamais consommé

### Constat vérifié

`scripts/bootstrap-env.sh:17` génère `MARTIN_SECRET` (avec 3 autres
secrets forts) ; `docker-compose.yml:100-126` (service `martin`) ne le lit
jamais dans son `environment:` (seul `DATABASE_URL` y figure). L'accès à
Martin passe depuis SP-24/SP-32 exclusivement par
`admin-auth@docker` (forwardAuth Traefik vers `/admin-tools/verify`) — Martin
lui-même n'a jamais eu de mécanisme d'authentification par secret partagé
dans sa config (`martin-config.yaml` ne référence pas `MARTIN_SECRET`), et
la revue de historique (`docs/superpowers/specs/2026-07-15-sp9-install-secrets-design.md`,
`docs/superpowers/plans/2026-07-16-sp9-install-secrets.md`) confirme que
« rendre `MARTIN_SECRET` réellement consommé par `martin` » a été
explicitement écarté du périmètre à sa création (SP-9) et redécouvert sans
correction à 3 reprises depuis (SP-1d3, SP-9, SP-21 — cf.
`DOCUMENTED_BUT_UNWIRED_EXEMPTIONS` dans `core/tests/test_deployability.py:412-419`).
`docs/revue/2026-09-04-matrice-fonctionnalites.md:387` propose déjà les
deux options : câbler, ou retirer.

### Décision : retirer, pas câbler

L'accès à Martin est déjà protégé par un mécanisme réel et testé
(`test_admin_tool_router_is_gated_by_admin_auth`,
`core/tests/test_deployability.py:879`) — inventer une seconde couche de
protection par secret partagé pour un chemin déjà gardé ajouterait de la
surface (un secret de plus à générer, faire tourner, documenter) sans
combler un trou d'accès réel : le trou est que la variable **prétend**
protéger quelque chose qu'elle ne protège pas, pas qu'il manque une
protection. Le fix le plus sûr et le moins coûteux est de retirer la
variable plutôt que de câbler une protection redondante avec l'existant.

### Fix

- `scripts/bootstrap-env.sh` : retirer `MARTIN_SECRET` de la boucle `for var
  in PG_PASSWORD MINIO_PASSWORD KC_PASSWORD MARTIN_SECRET` (ne reste que 3
  noms).
- `.env.example` : retirer le bloc `MARTIN_SECRET` (lignes 15-22) en entier —
  plus une ligne active, plus un commentaire d'orpheline à maintenir.
- `core/tests/test_deployability.py` : retirer l'entrée `"MARTIN_SECRET"` de
  `DOCUMENTED_BUT_UNWIRED_EXEMPTIONS` (devient sans objet, la variable
  n'étant plus documentée du tout).

## 3. GAP-58 — `POST /collections/empty` sans rate-limit dédié

### Constat vérifié

`core/app/collections/routes.py:273-293` (route DDL — `create_empty_collection`
exécute un vrai `CREATE TABLE` PostGIS) est gardée par
`require_privilege(session, user, Privilege.DATA_MANAGE.value)` (autorisation
correcte, SP-42 correctif 1) mais par **aucun groupe** de
`core/app/ratelimit/limiter.py::route_group()` — ni `sql`, ni `llm`, ni
`jobs` (`_EXPORT_PATH_RE`), ni `harvest`. Un utilisateur authentifié muni du
privilège `data.manage` (Créateur, pas seulement Administrateur) peut donc
appeler cette route en boucle serrée sans aucune limite de débit — un DoS par
`CREATE TABLE` répété, indépendant du gap plus large et hors périmètre
GAP-73 (quotas de ressources par tenant, qui limiterait le nombre total de
collections, pas le débit d'appel).

### Fix

Nouveau groupe `collections_empty` dans `_BUDGETS` (budget serré : 5/60s,
plus bas que `harvest`/10 et `jobs`/15 — un DDL est plus coûteux qu'un appel
réseau ou une lecture), nouvelle regex `_COLLECTIONS_EMPTY_RE = re.compile(
r"^/collections/empty$")`, branchée dans `route_group()` sur méthode `POST`
uniquement (cohérent avec le principe déjà appliqué à `harvest` : ne limiter
que l'écriture).

## 4. GAP-61 — Rate limiter incomplet (3 sous-manques)

**Correction au texte de `analyse-gaps.md` (piège CLAUDE.md n°3)** : le
document affirme que « les 4 routes ArcGIS live-query échappent entièrement
au rate limiter ». Vérifié faux : `_EXPORT_PATH_RE`
(`core/app/main.py:65-67`, motif
`^/(collections/[^/]+|datasets/[^/]+/arcgis)/export(/items)?$|...`) couvre
déjà **2 des 4** routes (`POST /datasets/{id}/arcgis/export` et
`GET /datasets/{id}/arcgis/export/items`, groupe `jobs`). Seules
**2 routes échappent réellement** : `GET /datasets/{id}/arcgis/items` et
`POST /datasets/{id}/arcgis/aggregate` (`core/app/harvest/routes.py:284,331`)
— ni `_SQL_RE`, ni `_LLM_RE`, ni `_EXPORT_PATH_RE`, ni `_HARVEST_RE` (qui ne
couvre que les chemins `/harvest/*`, pas `/datasets/*`) ne les capturent.

### 4.a — Budget anonyme partagé (clé vide)

`core/app/main.py` (`rate_limit_guard`) dérive `caller_key = request.headers.
get("authorization", "")` — pour **tout** appelant anonyme (aucun en-tête
`Authorization`), la clé est la chaîne vide, identique pour tous. Un seul
appelant anonyme abusif épuise le budget d'un groupe rate-limité pour
**tous** les autres appelants anonymes simultanés de l'instance (pertinent :
plusieurs endpoints d'export sont anonymes-capables par design, cf.
commentaire CORS de `core/app/main.py` autour d'`_APPEXPORT_CORS_RULES`).

Fix : extraire `caller_key(auth_header, client_host)` en fonction pure dans
`app/ratelimit/limiter.py` — retombe sur `f"anon:{client_host}"` en l'absence
d'en-tête `Authorization`. Pour que `request.client.host` reflète l'IP
réelle du visiteur (et non celle du conteneur Traefik, seul point d'entrée
réseau vers `core` — vérifié : le service `core` de `docker-compose.yml`
n'expose aucun port hôte direct, seul `gis-net` interne le relie à Traefik),
`app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")`
(`uvicorn.middleware.proxy_headers`, vérifié présent et importable dans
l'environnement `uv` du dépôt, signature `(app, trusted_hosts: list[str] |
str = "127.0.0.1")`) est ajouté dans `create_app()`, **après** les
`@app.middleware("http")` déclarés (Starlette empile les middlewares dans
l'ordre inverse de déclaration : le dernier ajouté est le plus extérieur et
s'exécute en premier — vérifié empiriquement par un test isolé pendant
l'écriture de ce document, cf. piège CLAUDE.md n°3, jamais pris sur
mémoire). `trusted_hosts="*"` est acceptable ici précisément parce que
`gis-net` est un réseau Docker interne dont tous les membres sont des
conteneurs du même dépôt (aucun tiers non fiable ne peut y injecter
`X-Forwarded-For` directement) — risque résiduel documenté : un conteneur du
dépôt lui-même compromis pourrait usurper une clé de rate-limit, mais ne
contournerait aucune autorisation (le rate-limit n'est pas un mécanisme
d'auth).

### 4.b — Les 2 routes ArcGIS live-query non couvertes

Nouvelle regex `_ARCGIS_LIVE_QUERY_RE = re.compile(
r"^/datasets/[^/]+/arcgis/(items|aggregate)$")` dans `limiter.py`, vérifiée
dans `route_group()` avant `_HARVEST_RE` (peu importe la méthode HTTP,
contrairement à `_HARVEST_RE` : ces deux routes déclenchent toutes deux un
appel sortant vers un service ArcGIS tiers, y compris la lecture `GET
.../items` — à la différence de `GET /harvest/layers`, qui est une lecture
locale pure). Rattachées au groupe `harvest` existant (même classe de coût :
appel réseau vers un service tiers), pas un nouveau groupe.

### 4.c — Cache module-global de `live_query.py` jamais purgé

`core/app/harvest/live_query.py:22,128-141` (`_cache`, `fetch_query`) : une
entrée n'est retirée du dict que si sa clé est **relue** après expiration —
une clé jamais réinterrogée reste dans `_cache` indéfiniment. Fix : même
patron que `RateLimiter._sweep` (`core/app/ratelimit/limiter.py:83-91`) —
compteur d'appels module-global, balayage complet périodique
(`_SWEEP_INTERVAL = 50`, valeur identique par cohérence, pas de contrainte
technique à la faire diverger) qui retire toute entrée dont `expires_at` est
dépassé, indépendamment de la clé en cours.

## 5. GAP-77 — Clé privée `age` de test dans l'historique git public

### Constat vérifié

`git show 0b4733a1` contient littéralement (ligne ajoutée, pas seulement
mentionnée) `AGE-SECRET-KEY-1PC2664KFMK5QC4TV02067DFVJ2XKK6XT4HY2TTGZ2RQHMZ9MSWTQV2NSY5`.
Confirmé absente de `HEAD` (`git grep -n "AGE-SECRET-KEY" HEAD` : vide,
seules les mentions dans `docs/revue/2026-09-04-analyse-gaps.md` et
`docs/revue/2026-09-04-backlog.md` — du texte à propos de la clé, pas la clé
elle-même). `git log --all -p -S "AGE-SECRET-KEY"` montre la clé réelle
apparaître et disparaître plusieurs fois au fil de l'historique (redaction
progressive) — la commande de purge doit viser **tout** l'historique, pas ce
seul commit.

Le message du commit `0b4733a1` lui-même qualifie cette clé de « clé privée
de test... jetée en fin de session, ne protège rien de réel » — pas de
rotation nécessaire, seulement une purge (le coût GAP-77 le note déjà :
« 0.5-1 j-h, purge d'historique **+ rotation si la clé a un usage réel
quelque part** » — vérifié qu'elle n'en a pas).

### Fix (opération manuelle, pas de TDD applicable)

Cette opération réécrit l'historique public et casse tout clone existant —
**nécessite l'accord explicite de Tanguy avant exécution**, jamais prise sur
le seul jugement d'une session (règle générale de ce dépôt sur les
opérations destructives). Procédure :

1. Vérifier avant : `git log --all -p -S "AGE-SECRET-KEY" --oneline | grep
   -c "^commit"` (nombre de commits touchés par la chaîne).
2. `git filter-repo --replace-text <(echo "AGE-SECRET-KEY-1PC2664KFMK5QC4TV02067DFVJ2XKK6XT4HY2TTGZ2RQHMZ9MSWTQV2NSY5==>AGE-SECRET-KEY-REDACTED")`
   sur un clone miroir dédié (jamais sur le clone de travail principal).
3. Vérifier après, sur le mirror réécrit : `git log --all -p -S
   "AGE-SECRET-KEY-1PC2664KFMK5QC4TV02067DFVJ2XKK6XT4HY2TTGZ2RQHMZ9MSWTQV2NSY5"`
   retourne vide.
4. `git push --force` du mirror réécrit vers `origin` (nécessite d'avertir
   tout autre porteur de clone — sessions concurrentes possibles, cf.
   CLAUDE.md piège n°9 — de re-cloner plutôt que `pull`).
5. Suivre la procédure GitHub de purge du cache (contacter le support GitHub
   pour expirer les vues en cache d'un commit contenant un secret sur un
   dépôt public — les objets détachés restent accessibles par hash pendant
   un délai avant garbage-collection côté GitHub).

## 6. GAP-78 — Réglages de sécurité GitHub désactivés

### Constat vérifié (relu en session, `gh api repos/tlenenao/geostudio`)

```json
{
  "secret_scanning": {"status": "disabled"},
  "secret_scanning_push_protection": {"status": "disabled"},
  "dependabot_security_updates": {"status": "disabled"},
  "secret_scanning_non_provider_patterns": {"status": "disabled"},
  "secret_scanning_validity_checks": {"status": "disabled"}
}
```

GAP-78 ne nomme que les 3 premiers ; les 2 derniers (patterns non-fournisseur,
vérification de validité) sont liés mais hors périmètre explicite du gap —
laissés tels quels, gratuits à activer plus tard sans dépendance à ce SP.

### Fix (opération manuelle `gh api`, pas de code)

```bash
gh api --method PATCH repos/tlenenao/geostudio --input - <<'EOF'
{
  "security_and_analysis": {
    "secret_scanning": {"status": "enabled"},
    "secret_scanning_push_protection": {"status": "enabled"},
    "dependabot_security_updates": {"status": "enabled"}
  }
}
EOF
```

Vérification après : rejouer le `gh api repos/tlenenao/geostudio` en lecture
seule, confirmer les 3 champs à `"enabled"`. Gratuit sur un dépôt public
(pas de coût de licence GitHub Advanced Security sur les dépôts publics).

## 7. GAP-79 — `traefik` sans politique `restart:`

### Constat vérifié

**Correction au texte de `analyse-gaps.md`** : le gap dit « contrairement
aux 9 autres services de l'overlay prod qui reçoivent tous `restart:
unless-stopped` ». Vérifié : ce sont précisément 9 services qui déclarent
`restart: unless-stopped` **dans le fichier `docker-compose.prod.yml`
lui-même** (`postgis`, `pgbouncer`, `minio`, `martin`, `titiler`, `keycloak`,
`otel-lgtm`, `tunnel`, `backup`) — le compte est juste, mais 6 services
supplémentaires (`core`, `worker`, `cdc-worker`, `export-worker`,
`qgis-worker`, `shell`) ont déjà `restart: unless-stopped` hérité du
`docker-compose.yml` de base (pas besoin de le répéter dans l'overlay).
`traefik` est donc bien le seul service durablement actif (à l'exclusion
d'`appexport-runtime-builder`, un conteneur one-shot de build, pour lequel
`restart:` n'a pas de sens) sans politique de redémarrage, ni dans le
fichier de base ni dans l'overlay — confirmé sur les deux fichiers, ligne
`traefik:` jusqu'à la fin de chaque bloc.

### Fix

Une ligne `restart: unless-stopped` ajoutée au service `traefik` de
`docker-compose.yml` (base), après `networks: [gis-net]` — l'overlay
`docker-compose.prod.yml` en hérite automatiquement (fusion Compose : une
clé non réécrite par l'overlay survit du fichier de base), aucune édition de
`docker-compose.prod.yml` nécessaire.

## 8. Critères d'acceptation

- Les 7 manques ont chacun un test qui échoue avant le fix et passe après
  (GAP-02, GAP-41, GAP-58, GAP-61 : pytest ; GAP-77, GAP-78 : vérification
  `git`/`gh api` avant/après documentée dans le ledger d'exécution ; GAP-79 :
  test `test_deployability.py`).
- `cd core && uv run pytest` reste vert (aucune régression).
- `cd core && uv run ruff check . && uv run ruff format --check . && uv run
  mypy --strict app/auth app/secrets app/analytics app/copilot
  app/admin_tools app/roles && uv run lint-imports` restent verts.
- Diff OpenAPI/types TS **vide attendu** : aucune des 7 tâches ne change de
  route, de modèle de requête/réponse, ni de champ visible côté shell — à
  vérifier explicitement (piège CLAUDE.md n°1), pas supposé.
- GAP-77/GAP-78 : opérations manuelles hors code, réalisées avec l'accord
  explicite de Tanguy et documentées (avant/après) dans le ledger de
  session, jamais automatisées dans ce plan.

## 9. Suite logique recommandée, non entamée ici

**SP-48 — bascule de la CSP de `Report-Only` en enforcing** (GAP-72) est la
suite naturelle de ce SP une fois les 7 manques ci-dessus refermés : les 4
blocages concrets qui l'ont empêchée jusqu'ici (tuiles WMS/WMTS moissonnées +
terrain externe, tuilesets 3D externes, widgets d'extension tiers, incohérence
`connect-src` shell/nginx vs overlay prod) restent documentés en commentaire
dans `docker-compose.prod.yml:167-184` et n'ont pas été ré-audités pour ce
document — travail de conception à part entière, pas un correctif bon
marché comme les 7 ci-dessus.

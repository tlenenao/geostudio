# Revue de projet GeoStudio & plan d'action — 2026-08-20

**Commit audité** : `a7817e5` (branche `dev`, 1423 commits)
**Hypothèse de travail** : SP-20 est considéré **livré**. Côté cœur, les tâches 1→7
du plan `2026-08-16-sp20-copilote-embarque.md` sont committées (`app/copilot/`
complet : `llm_provider`, `mcp_loopback`, `tools_allowlist`, `routes`) ; côté
shell, les tâches 8→13 sont en cours. Les constats copilote ci-dessous portent
donc sur du **code réellement committé**, pas sur une intention.
**Entrées externes** : trois analyses fournies (Kimi, Grok, ChatGPT), toutes
datées du 2026-08-08 sur le commit `943a1ce` — soit **avant** SP-17b, SP-18,
SP-19, SP-20 et avant la 3D. Chacune est triagée en §2.

---

## 1. Verdict

Sur les axes que les trois analyses ont mesurés — densité de tests, frontières de
modules, documentation de vision, primitives de sécurité applicative — le dépôt
est en **très bon état**, meilleur que ce que les trois rapports laissent
entendre. Plusieurs de leurs « critiques » sont soit déjà livrées, soit fausses,
soit en contradiction directe avec un arbitrage figé (§2).

Le risque réel est ailleurs, et **aucune des trois analyses ne l'a vu** :

> **L'écart entre ce qui est livré et ce qui est déployable.**
> Cinq SP terminés (SP-15d, SP-17a, SP-17b, SP-18a, SP-18b) n'ont **aucun chemin
> de déploiement en production**. Le copilote SP-20 est cassé **par
> construction** dans l'overlay prod. La sauvegarde ne couvre que 3 des 7
> buckets S3, et les 2 non couverts qui comptent contiennent des données
> utilisateur irremplaçables.

C'est la même classe de défaut que CLAUDE.md documente déjà trois fois (SP-17a,
SP-17b, tileset3d : « variable absente de l'environnement du service `core` »).
La 4ᵉ et la 5ᵉ occurrence sont dans le dépôt aujourd'hui. Ce n'est plus une
série de bugs, c'est un **trou de processus** : il n'existe **aucune** vérification,
en CI ou en checklist, qu'une capacité nouvellement livrée soit déployable
ailleurs que sur le poste de développement.

Deuxième constat structurant, sous-estimé par les trois analyses : il n'y a
**aucun linter, aucun type-checker Python, aucun formateur, aucune mesure de
couverture** sur ~60 000 lignes écrites intégralement par des sessions LLM
successives. Le filet est porté à 100 % par les tests (235 fichiers pytest,
148 fichiers Vitest, 53 specs Playwright) et par la discipline de revue de
branche. Ça marche — les revues finales trouvent réellement des défauts — mais
c'est le levier le moins cher du dépôt, et il n'est pas tiré.

Enfin, un angle mort produit : **l'interface est intégralement en français
codé en dur** (~784 littéraux dans les seuls `.tsx`, `<html lang="fr">`), sans
aucune infrastructure i18n. Pour un projet Apache-2.0 qui vise l'adoption
publique au jalon M6, c'est une barrière à l'entrée plus forte que n'importe
lequel des points de sécurité listés par les trois analyses. Et l'absence
d'audit d'accessibilité automatisé est, pour un produit destiné à des
collectivités françaises, une question de **conformité RGAA**, pas de confort.

Troisième angle mort, et le plus large : **la surface fonctionnelle a pris du
retard sur la surface technique**. Le §7 analyse douze domaines produit et le
motif se répète : la brique difficile est construite, la dernière marche
manque. La carte n'a aucun popup et son clic ne fonctionne pas sur les couches
tuilées, donc pas sur un jeu de données réel. La symbologie existe mais dans le
widget carte, pas dans l'éditeur de cartes. Les configs sont versionnées avec
rollback **depuis SP-0** et aucune page ne les appelle. Le catalogue ne filtre
que 3 des 12 types d'objets livrés. L'export DCAT-AP émet une licence codée en
dur, ce qui le rend inexploitable pour l'open data. `audit_log` est alimenté par
toute écriture et aucune UI ne le lit. Aucun de ces points n'est un bug : ce
sont des dernières marches, souvent à faible coût, sur des fondations déjà
payées.

---

## 2. Triage des trois analyses fournies

Vérifié ligne par ligne contre le code. `FAUX` signifie que l'affirmation ne
tient pas au commit audité ; `LIVRÉ` que le manque signalé a été comblé depuis
le 2026-08-08 ; `PARTIEL` que le constat est juste mais la cause ou la gravité
sont mal posées.

| Réf | Affirmation | Verdict | Réalité vérifiée |
|---|---|---|---|
| Kimi REL-01 | « 106 TODO/FIXME/HACK/XXX, dette technique réelle » | **FAUX** | Exactement **2** occurrences dans `core/app` + `shell/src`, toutes deux des renvois documentés entre `ExportPanel.tsx` et `export/repository.py`. Grok avait raison (0 dette marqueur). |
| Kimi OPS-01/02/03, ChatGPT 9.3/9.4 | « Aucun SLO, aucune alerte configurée, dashboards à exposer » | **FAUX** | `deploy/observability/grafana/provisioning/alerting/rules.yaml` contient **5 règles** (latence P95 API Features, latence tuiles Martin, backlog de jobs, taux 5xx, + une règle de preuve du pipeline) et 4 dashboards provisionnés. Le seul vrai manque : **aucun contact point / policy de notification** → les alertes s'allument dans l'UI et ne notifient personne (cf. I9). |
| Kimi FEAT-05 | « Feature flags : système à créer » | **FAUX** | 7 capacités instance-wide existent déjà (`CORE_ETL_ENABLED`, `CORE_EXPORT_ENABLED`, `CORE_APPEXPORT_ENABLED`, `CORE_TILESET3D_ENABLED`, `CORE_TERRAIN3D_ENABLED`, `CORE_READ_ONLY_MODE`, + copilote via `CORE_LLM_PROVIDER`). Le problème n'est pas leur absence mais leur **gouvernance** (cf. C4, I14). |
| Kimi FEAT-04 | « Cache Redis/Memcached pour tuiles et API » | **À REJETER** | Contredit un arbitrage figé : Redis a été **sorti du projet au jalon M1** (CLAUDE.md, « GeoNode/Superset/Redis : sortis »). Réintroduire un broker/cache mémoire est une décision produit, pas une amélioration technique. |
| Kimi FEAT-06/07, DATA-02/03, INT-02 | Export PDF/PNG, 3D Tiles + terrain, analytique embarquée, fédération de catalogues, connecteur ETL | **LIVRÉ** | Respectivement SP-17a, 3D (rendu + hébergement), SP-14, SP-12 (5 connecteurs), SP-15. Kimi place ces items en « M10 / Q3 2027 » alors qu'ils sont derrière nous. |
| Kimi, tableau de roadmap M1→M10 | « M2 en cours, M6 Q1 2027, M10 Q3 2027 » | **FAUX / À JETER** | Le jalon **M15 est atteint**. Ce tableau a ~14 mois de retard ; tout séquencement qui en dérive est sans valeur. |
| Kimi SEC-01, Grok S1, ChatGPT 6.5 | « SQL injection : f-strings, criticité P0 » | **PARTIEL, gravité surévaluée** | Les 10 primitives de quoting sont **individuellement correctes** (doublement de `"` pour les identifiants, de `'` pour les littéraux — la bonne règle pour PG et DuckDB) ; `collections/ddl.py` et `publication.py` délèguent même au `identifier_preparer` de SQLAlchemy. Le vrai problème n'est pas l'injection, c'est que la primitive est **dupliquée 6 fois** sans implémentation partagée ni suite de tests d'injection dédiée (cf. M1). Pas P0. |
| Grok, ChatGPT | « SSRF : risque structurel majeur / 🔴 CRITIQUE » | **PARTIEL, gravité surévaluée** | 3 gardes existent (`harvest/`, `pipelines/`, `alerts/egress.py`), bloquant loopback / privé / link-local / réservé / multicast / unspecified, avec allowlist optionnelle, session `requests` gardée pour dlt, redirections couvertes (fix SP-16b). Le résiduel — DNS-rebinding TOCTOU — est **déjà documenté** comme suivi assumé. Le vrai manque est ailleurs : une **4ᵉ surface d'egress non gardée** est apparue avec SP-20 (l'appel LLM), et un opérateur doit configurer **3 variables d'allowlist distinctes** pour une seule propriété de sécurité. |
| ChatGPT 9.5 | « Backup : 🔴 CRITIQUE, insuffisant » | **PARTIEL, bonne conclusion mauvaise raison** | Le mécanisme existe et est sérieux : `pg_dump`, export du realm Keycloak, miroir de buckets, chiffrement `age`, rétention testée (`test_retention.py`), copie offsite optionnelle, runbook de restauration daté. Le défaut réel est la **couverture** (3 buckets sur 7) et le fait que la restauration n'ait jamais été rejouée (cf. C5). |
| ChatGPT I7 | « Ajouter import-linter » | **LIVRÉ (mais troué)** | Présent depuis SP-1a, 26 couches. Les trois analyses le citent comme une force *sans le vérifier* : **4 modules sont hors contrat**, dont `app.analytics`, le module le plus sensible du dépôt (cf. I1). |
| Grok 3.2 | « PEP8 implicite via uv » | **FAUX** | `uv` n'est pas un linter. Il n'y a **ni ruff, ni mypy, ni black, ni bandit, ni pytest-cov** dans `core/pyproject.toml`. |
| ChatGPT 7.2 | « Maintenir tsc/eslint/vitest comme contrôles obligatoires » | **FAUX (prémisse)** | Il n'y a **ni ESLint ni Prettier** dans le shell — aucun fichier de configuration, aucune dépendance. Le seul contrôle statique est `tsc --noEmit`. |
| Kimi TST-04 | « E2E sur OIDC réel manquants » | **VRAI** | `playwright.config.ts` force `VITE_AUTH_MODE: "mock"`. Les 53 specs n'exercent jamais la redirection Keycloak, PKCE, le refresh, l'expiration ni le logout. |
| Kimi SEC-02 | « Image core en root » | **VRAI** | 8 Dockerfiles, **0 directive `USER`**. `core/Dockerfile` documente le choix (répertoire d'extensions DuckDB partagé build/runtime) — c'est une raison, pas une impossibilité. |
| Kimi SEC-03 | « Pas de CSP » | **VRAI** | Le middleware Traefik `security-headers` pose STS, nosniff, frameDeny, referrerPolicy — **pas de `Content-Security-Policy`, pas de `Permissions-Policy`**. `shell/nginx.conf` est un `try_files` nu : aucun en-tête, aucune compression. |
| Kimi SEC-04 | « Rate limiting applicatif absent » | **VRAI** | Un seul `ratelimit` Traefik (average 100 / burst 200) **uniforme** : `/analytics/sql`, `/mcp`, `/copilot/turn` et un `GET /health` partagent le même budget. Aucun rate limiting côté FastAPI, donc **rien** dans un déploiement non fronté par Traefik. |
| Kimi SEC-05, Grok S2, ChatGPT C1 | « Verrouiller le mode mock en production » | **VRAI, et pire que décrit** | `_mock_mode()` lit `CORE_AUTH_MODE` sans aucun garde d'environnement, et retourne un utilisateur `bootstrap_admin=True, bootstrap_analyst=True` pour **n'importe quel** `Bearer <n'importe quoi>`. Une fuite de cette variable en prod = compromission administrative totale, sans credential. |
| Kimi REL-02 | « Pas de healthcheck sur core » | **VRAI** | 3 healthchecks au total (postgis, minio, keycloak). Ni `core`, ni `worker`, ni `cdc-worker`, ni `shell`, ni `martin`/`titiler`/`pgbouncer`. |
| Kimi REL-03 | « Graceful shutdown du CDC worker » | **VRAI** | `core/app/cdc/main.py` : aucun handler `signal`, aucun `SIGTERM`. |
| Kimi ARC-03 | « `app.db` : 10 imports ignorés masquant une violation » | **VRAI (18, pas 10)** | 18 `ignore_imports` `app.db -> app.*.models`. La cause est légitime (enregistrement du metadata SQLAlchemy) mais la liste grandit d'une ligne à chaque SP. |
| Kimi ARC-04, ChatGPT | « Format d'erreur uniforme (RFC 7807) » | **VRAI** | Aucun `exception_handler` global dans `main.py`. |
| Kimi FEAT-01 | « Versionner l'API (`/v1/`) » | **VRAI** | Aucun préfixe de version, aucune politique de dépréciation. Pertinent avant M6 puisque l'OpenAPI est déjà consommé par un client généré. |
| Kimi PERF-01 | « Pagination cursor-based » | **VRAI mais à déprioriser** | `select_features` est en `LIMIT/OFFSET`. C'est aussi ce que **spécifie OGC API Features** (`offset`), les collections sont RLS-scopées, et aucune mesure ne montre que c'est un problème. À traiter sur preuve, pas par principe. |
| Kimi PERF-02 | « Compression gzip/brotli » | **VRAI** | Aucune compression : ni middleware Traefik `compress`, ni `gzip on` dans `shell/nginx.conf`, ni `GZipMiddleware` FastAPI. |
| Kimi A11Y-03/04 | « WCAG 2.1 AA, i18n » | **VRAI, et plus important que classé** | Aucune infrastructure i18n, `<html lang="fr">`, ~784 littéraux français dans les `.tsx`. 388 attributs `aria-`/`role=` sur 115 composants (donc une intention a11y réelle), mais **aucun audit automatisé** (pas d'`axe`, pas de test clavier). |
| Grok/ChatGPT/Kimi (SAST) | Semgrep/CodeQL, secret scanning, Trivy, SBOM, Dependabot, pre-commit | **VRAI** | CI = 6 jobs (migrations up/down, pytest + lint-imports, `pip-audit --strict`, dérive des types OpenAPI, vitest + Playwright + build, `npm audit`). Solide sur les dépendances, **rien** en SAST, secrets, image, SBOM, et aucun hook pre-commit. |
| ChatGPT §4 | « Refonte `domain/application/infrastructure` » | **À REJETER** | Une réécriture de 19k lignes de cœur pour remplacer un contrat de couches qui fonctionne. Le vrai problème du contrat est qu'il est **incomplet** (I1), et ça se corrige en 4 lignes. |
| ChatGPT §1 | « Le risque principal est la complexité opérationnelle du monolithe » | **NON ÉTAYÉ** | Aucun fichier du cœur ne dépasse 802 lignes ; médiane très basse ; 19k lignes pour 26 modules. Il n'y a pas de god file. La complexité *opérationnelle* est réelle mais elle est dans le **déploiement** (C4), pas dans le code. |

---

## 3. Constats vérifiés — par gravité

### Critique

**C1 — `/copilot/turn` : le principal authentifié n'est pas celui qui agit (confused deputy).**
`core/app/copilot/routes.py:112-127`. La route authentifie l'appelant via
`Depends(get_current_user)`, puis ouvre la session MCP avec `body.mcpToken`, un
**second jeton fourni par le client**, dont l'identité n'est jamais comparée à
celle de l'appelant. Le paramètre `user: User` est lié et **jamais utilisé** —
c'est le symptôme : la route vérifie une identité et exécute sous une autre.
Quiconque détient un jeton d'audience MCP appartenant à un autre utilisateur
(log, navigateur partagé, jeton obtenu légitimement pour un autre compte, autre
tenant) peut faire exécuter `create_item` / `create_form_app` /
`run_analytics_query` **sous cette identité** en présentant son propre
`Authorization`. Correctif : décoder le jeton MCP et exiger `sub ==
user.oidc_sub` + audience MCP, avant d'ouvrir la session.

**C2 — `/copilot/turn` bloque la boucle d'événements jusqu'à 3 minutes.**
`llm_provider.py:53` fait un `httpx.post(..., timeout=30.0)` **synchrone**,
appelé depuis `_run_turn`, qui est un `async def`. Le processus `uvicorn` de la
stack tourne **sans `--workers`** : un seul appel copilote gèle donc *toutes* les
requêtes (tuiles, features, `/health`) pendant la durée de l'aller-retour LLM.
Second effet, moins visible : `asyncio.wait_for(..., timeout=30.0)` en
`routes.py:120` **ne peut pas se déclencher** pendant un appel synchrone
bloquant — le garde 504 est inopérant précisément dans le cas qu'il couvre, et
le temps mural réel atteint `MAX_TOOL_ITERATIONS × 30 s = 180 s`, pas 30.
Correctif : `httpx.AsyncClient` + `await` (ou `run_in_threadpool`), et budget de
temps global explicite.

**C3 — Le copilote est cassé par construction dans l'overlay de production.**
`mcp_loopback.py:45` prend `os.environ["CORE_BASE_URL"]` comme cible du rappel
HTTP vers `/mcp`. Or `docker-compose.prod.yml:84` fixe
`CORE_BASE_URL: https://${GEOSTUDIO_PUBLIC_HOST}/api`. Le conteneur `core` doit
donc résoudre et joindre **son propre nom d'hôte public en TLS depuis
l'intérieur du réseau Docker** — le cas classique d'échec de hairpin NAT. En
dev, `http://localhost:8200` désigne l'application elle-même et ça marche *par
accident*. `CORE_BASE_URL` porte désormais deux rôles contradictoires :
identité publique (métadonnées OAuth MCP depuis SP-2a, fichier de connexion
SP-18b) **et** cible de rappel interne. Correctif : `CORE_INTERNAL_BASE_URL`
dédiée, défaut `http://localhost:8200`.

**C4 — Cinq SP livrés n'ont aucun chemin de déploiement en production.**
`docker-compose.prod.yml` est un overlay qui remplace `build:` par une image
GHCR pour **5 services seulement** : `postgis`, `core`, `worker`, `cdc-worker`,
`shell`. Tous les autres conservent leur `build:` du fichier de base :
`export-worker` (SP-17a, dont dépend SP-17b), `qgis-worker` (SP-15d),
`appexport-runtime-builder` (SP-18a/b), et `backup` (déclaré uniquement dans
l'overlay, avec `build: ./deploy/backup`). Et `release.yml` ne publie que
**4 images** (`geostudio-core`, `-shell`, `-postgis`,
`-appexport-standalone`) : il n'existe donc rien à tirer, même en le voulant.
Conséquence : déployer l'export PDF, les rapports planifiés, les algorithmes
QGIS ou l'export d'apps en production exige de **cloner les sources et
compiler Chromium/QGIS sur l'hôte de prod**, ce qui contredit l'en-tête du
fichier lui-même (« images depuis GHCR (au lieu de `build:`) »). Le mécanisme de
sauvegarde, seul rempart contre la perte de données, est dans le même cas.

**C5 — La sauvegarde ignore 4 des 7 buckets, dont deux contiennent des données
irremplaçables.** `deploy/backup/backup.sh:25-27` miroite exactement
`thumbnails`, `uploads`, `cdc`. Le cœur en utilise sept : s'ajoutent
`exports`, `appexports`, `tileset3d`, `terrain3d`. Les deux derniers sont le
problème : un tileset 3D uploadé est un objet S3 **jamais extrait, sans autre
copie**, et ses métadonnées vivent dans `BuilderConfig.tileset3d` — après une
restauration, l'item réapparaît intact en pointant sur une clé S3 disparue,
donc définitivement cassé, sans erreur au moment de la restauration.
`exports`/`appexports` sont des artefacts régénérables : les exclure est
légitime, mais ça doit être écrit. Accessoirement, `S3_EXPORTS_BUCKET`,
`S3_APPEXPORTS_BUCKET` et `S3_CDC_BUCKET` **ne figurent pas dans
`.env.example`** : un opérateur ne peut pas les découvrir.

**C6 — `CORE_AUTH_MODE=mock` accorde l'administration sans credential, sans
garde.** `auth/dependency.py:116-127` : en mode mock, tout `Bearer` non vide
retourne un utilisateur avec `bootstrap_admin=True` **et**
`bootstrap_analyst=True`. Aucune vérification d'environnement, aucun refus au
démarrage. Les trois analyses le signalent ; la conclusion est la bonne et le
correctif est de trois lignes (échec au boot si `mock` sans marqueur explicite
de développement).

### Important

**I1 — Quatre modules sont hors du contrat de couches, dont le plus sensible.**
Le contrat `[tool.importlinter]` liste 26 couches. Manquent : **`app.analytics`,
`app.cdc`, `app.search`, `app.instance`**. `app.analytics` n'est pas un détail :
il porte le sandbox SQL DuckDB et le moteur d'agrégation, et il est importé par
**11 modules** répartis sur toute la hauteur de la pile (`configs`, `features`,
`harvest`, `alerts`, `pipelines`, `mcp`, `appexport`). `lint-imports` passe au
vert sans rien dire de lui. Vérifié empiriquement : inséré au milieu de la
pile, le contrat **casse** (`app.configs` et `app.features` l'importent depuis
le dessous) ; placé au **bas** de la pile avec `app.search`, et `app.cdc` juste
au-dessus d'`app.ingestion`, le contrat **passe : 1 kept, 0 broken**. Le trou se
referme donc en 4 lignes de `pyproject.toml`, sans aucun refactor.

**I2 — Aucun contrôle statique sur ~60 000 lignes écrites par LLM.** Ni `ruff`,
ni `mypy`, ni `black`, ni `bandit` côté Python ; ni ESLint ni Prettier côté
shell ; aucune mesure de couverture des deux côtés ; aucun hook pre-commit.
Dans un dépôt où chaque ligne est produite par une session sans mémoire de la
précédente, un linter n'est pas de l'hygiène : c'est le seul mécanisme qui
applique une convention **sans qu'une session ait à s'en souvenir**.

**I3 — Ni CSP, ni Permissions-Policy, ni compression.** Cf. §2. Le shell servi
directement (port 8300 publié en dev) n'a **aucun** en-tête de sécurité,
`nginx.conf` étant un `try_files` nu.

**I4 — Rate limiting uniforme, et absent hors Traefik.** Un `POST
/analytics/sql`, un tour de copilote (jusqu'à 6 appels LLM) et un `GET /health`
consomment le même budget 100/200. Aucun garde côté application.

**I5 — Aucun healthcheck sur `core`, `worker`, `cdc-worker`, `shell`.** Rien
n'attend que les migrations Alembic soient passées avant que Traefik ne route
vers `core` ; rien ne détecte un worker vivant-mais-bloqué.

**I6 — `/copilot/turn` : aucun plafond de taille, et exempté du garde
lecture-seule.** `CopilotTurnRequest` n'a **aucune** contrainte : `history`,
`message`, `currentConfig` et `clientTools` sont entièrement pilotés par le
client et repartent intégralement à chaque itération LLM (jusqu'à 6). Combiné à
l'exemption explicite du garde démo (`main.py:122-131`) et à I4, l'instance de
démo publique prévue pour M6 laisse **un visiteur brûler le budget d'API LLM de
l'opérateur**. Les écritures, elles, sont bien bloquées (les outils MCP
vérifient `is_read_only_mode()` en 8 points).

**I7 — Surface d'injection de prompt via `currentConfig`.** `routes.py:48` :
`f"Configuration actuelle (JSON) : {current_config}"` — la config est
interpolée telle quelle dans le message système. Une `AppConfig` contient des
chaînes rédigées par des utilisateurs (titres de widgets, `richText`,
descriptions de datasets) et peut provenir d'un item **partagé par un tiers**.
Un titre malveillant devient une instruction, exécutée avec le jeton MCP réel
du lecteur. Accessoirement le `repr()` Python d'un dict n'est pas du JSON
(guillemets simples), donc l'étiquette « (JSON) » est fausse.

**I8 — Images non pinnées en production.** `minio/minio` est déclaré **sans
aucun tag** (donc `:latest`) pour le service de stockage objet, et
`tailscale/tailscale:latest` pour le tunnel de l'overlay prod. `pgbouncer`,
`martin`, `titiler` sont pinnés au patch ; `traefik:v3.0` et `keycloak:24.0`
flottent au mineur. Le suivi CLAUDE.md (« tags à repinner si dérive ») sous-estime
le cas : MinIO n'est pas « à repinner », il n'est pas pinné.

**I9 — Les 5 alertes SLO ne notifient personne.** `rules.yaml` ne contient ni
`contactPoints:` ni `policies:`.

**I10 — La clé maître des secrets échoue tard, et CLAUDE.md le décrit à
l'envers.** `load_master_key()` est appelée **paresseusement** depuis
`encrypt`/`decrypt`, jamais au démarrage. Une instance sans
`CORE_SECRETS_MASTER_KEY` démarre sans broncher et 500 (un `KeyError` nu) à la
première création de secret connecteur, potentiellement des mois plus tard.
CLAUDE.md affirme « clé maître requise au boot — échec rapide si absente » :
c'est l'intention du design SP-15e, pas le comportement du code.

**I11 — `cdc-worker` sans arrêt propre.** Aucun handler de signal dans
`cdc/main.py`, alors que ce worker tient un slot de réplication logique et un
feedback de LSN.

**I12 — Pas d'`ErrorBoundary` applicatif.** Il n'en existe qu'un, dans
`WidgetHost.tsx` (par widget). Toute exception de rendu hors widget produit un
écran blanc.

**I13 — L'authentification réelle n'est jamais testée de bout en bout.** 53
specs, toutes en `VITE_AUTH_MODE=mock`.

**I14 — Rien ne vérifie qu'une capacité est déployable. C'est la cause racine de
C3, C4 et des trois incidents déjà documentés.** Aucun job CI ne touche
`docker-compose*.yml` : ni `docker compose config`, ni comparaison de
l'ensemble des variables lues par `os.environ` avec celles fournies aux
services, ni vérification que chaque service `build:` du fichier de base a une
image publiée dans `release.yml`. La revue de tâche SP-18a a montré que la
vérification *manuelle* par valeur fonctionne — il faut la rendre automatique.

### À affiner

**M1 — Six copies de la primitive de quoting, avec une justification
auto-contredite.** `_qi` existe en 6 exemplaires (`analytics/aggregate`,
`pipelines/compiler`, `pipelines/runtime`, `pipelines/connector_runtime`,
`appexport/miniserver/items`), plus `quote_ident`/`_qi` en version SQLAlchemy
(`collections/ddl`, `collections/publication`) et 3 `_sql_lit`. Le commentaire
de `pipelines/runtime.py:71` justifie la duplication par le refus « d'un import
inter-module d'un nom privé `_`-préfixé » — alors que **la ligne 38 du même
fichier** fait exactement cela : `from app.analytics.aggregate import
_dedup_cte, _has_any_file`. La convention se contredit à 30 lignes d'écart.
Corollaire : aucune de ces copies n'a de test d'injection dédié.

**M2 — Aucune i18n.** ~784 littéraux français dans les `.tsx`, `<html lang="fr">`
en dur. C'est le principal frein à l'adoption externe du projet, plus que
n'importe quel point de sécurité de §2.

**M3 — Accessibilité non auditée.** 388 attributs `aria-`/`role=` sur 115
composants montrent une intention réelle, mais aucun audit automatisé (pas
d'`axe-core`), aucun test de navigation clavier, aucun contrôle de contraste.
Enjeu de conformité RGAA pour une cible « collectivités ».

**M4 — Contrat d'API non formalisé.** Pas de `/v1/`, pas de format d'erreur
uniforme, pas d'ADR (`docs/adr/` n'existe pas), un seul guide
(`docs/guides/`) et un seul runbook.

**M5 — `ItemClient` est devenu une interface-monde.** 1121 lignes, ~83 méthodes
non optionnelles, 2165 lignes de tests, et SP-18a a dû réécrire les 83
signatures à la main dans `StaticItemClient`. La règle d'architecture n°1 tient
toujours, mais son coût marginal augmente à chaque SP. À segmenter (catalogue /
données / analytique / administration) plutôt qu'à abandonner.

**M6 — CLAUDE.md dérive sur les faits mesurables.** La section « Commandes »
annonce « Vitest (61 fichiers, 398 tests) » et « Playwright (18 specs) » : la
réalité est **148 fichiers** de tests shell et **53 specs** E2E. Cf. aussi I10.
Ces chiffres sont lus par chaque session comme une vérité.

---

## 4. Plan d'action

Six vagues. L'ordre est celui du risque décroissant, pas celui de l'intérêt.
Chaque chantier indique sa **preuve de sortie** — la vérification qui prouve
qu'il est fait, dans l'esprit des revues de branche du dépôt.

### Vague 0 — Correctifs SP-20, avant merge (≈ 1 à 2 sessions)

Ces quatre points portent sur du code déjà committé sur `dev` et doivent partir
avec SP-20, pas après.

| # | Chantier | Contenu | Preuve de sortie |
|---|---|---|---|
| 0.1 | **Lier le jeton MCP à l'appelant** (C1) | Décoder `body.mcpToken`, exiger `sub == user.oidc_sub` et l'audience MCP avant d'ouvrir la session ; 401 sinon. Utiliser `user`, ou expliquer par écrit pourquoi il ne l'est pas. | Test : un jeton MCP d'un autre `sub` présenté avec un `Authorization` valide → 401, et aucun appel MCP émis. |
| 0.2 | **Désynchroniser l'appel LLM de la boucle d'événements** (C2) | `httpx.AsyncClient` + `await` dans `OpenAICompatibleLLMProvider`, ou `run_in_threadpool`. Budget de temps **global** au tour, pas par appel. | Test : pendant un tour copilote lent, `GET /health` répond < 1 s. Test : dépassement du budget → 504 effectif. |
| 0.3 | **`CORE_INTERNAL_BASE_URL`** (C3) | Nouvelle variable dédiée au rappel loopback, défaut `http://localhost:8200`, câblée dans les deux compose et `.env.example`. `CORE_BASE_URL` reste l'identité publique. | `docker compose -f docker-compose.yml -f docker-compose.prod.yml config` : la valeur passée à `core` est interne, jamais `https://${GEOSTUDIO_PUBLIC_HOST}`. |
| 0.4 | **Borner et neutraliser l'entrée du copilote** (I6, I7) | `max_length` Pydantic sur `message`/`history`/`currentConfig` sérialisé ; troncature explicite ; `json.dumps` au lieu du `repr()` ; délimiteur explicite autour de la config avec consigne système de ne jamais traiter son contenu comme une instruction ; retirer `/copilot/turn` de l'exemption du garde lecture-seule (ou plafonner par utilisateur en mode démo). | Test : `history` surdimensionné → 422. Test : un titre de widget contenant une instruction n'entraîne aucun appel d'outil. Test : en `CORE_READ_ONLY_MODE=true`, l'appel est refusé ou plafonné. |

### Vague 1 — Rendre déployable ce qui est déjà livré (≈ 3 à 4 sessions)

La vague à plus fort effet de levier : elle ne livre aucune fonctionnalité et
rend utilisables cinq SP déjà payés.

| # | Chantier | Contenu | Preuve de sortie |
|---|---|---|---|
| 1.1 | **Publier les images manquantes** (C4) | Ajouter `geostudio-export-worker`, `geostudio-qgis-worker`, `geostudio-appexport-runtime-builder`, `geostudio-backup` à la matrice de `release.yml`. | Un tag `v*` publie 8 images sur `ghcr.io`. |
| 1.2 | **Compléter l'overlay prod** (C4) | Substituer `build:` par l'image GHCR pour ces 4 services dans `docker-compose.prod.yml`, avec leurs profils. | `docker compose -f … -f … --profile export --profile etl --profile appexport config` ne contient **plus aucun** `build:`. |
| 1.3 | **Étendre la sauvegarde et documenter son périmètre** (C5) | Ajouter `tileset3d` et `terrain3d` à `backup.sh` ; écrire explicitement dans le runbook que `exports`/`appexports` sont exclus car régénérables ; ajouter les 3 variables de bucket manquantes à `.env.example`. | Un cycle sauvegarde → destruction → restauration sur une instance jetable : un item `tileset3d` reste **affichable** après restauration. |
| 1.4 | **Rejouer la restauration pour de vrai** (C5) | Exécuter le runbook `2026-07-24` de bout en bout, une fois, et le corriger là où il ment. | Le runbook porte une ligne « rejoué le \<date\>, écarts corrigés : … ». |
| 1.5 | **Garde CI de déployabilité** (I14 — le chantier structurant) | Nouveau job CI : (a) `docker compose config` sur base + overlay prod ; (b) tout service `build:` du fichier de base a une image dans `release.yml` ; (c) toute variable lue par `os.environ` dans `core/app/` figure dans l'environnement d'au moins un service **et** dans `.env.example`. | Le job échoue si l'on retire `CORE_TILESET3D_ENABLED` du service `core`, et si l'on ajoute un `os.environ["CORE_NOUVEAU"]` non câblé. |
| 1.6 | **Pinner et healthchecker** (I8, I5) | Tag explicite pour `minio/minio` et `tailscale/tailscale` ; healthcheck sur `core` (`GET /health`), `worker`, `cdc-worker`, `shell` ; `depends_on: condition: service_healthy` pour `core` là où c'est pertinent. | `docker compose config \| grep -c ":latest"` → 0. `docker compose ps` montre 4 services `healthy` de plus. |

### Vague 2 — Filet qualité statique (≈ 2 à 3 sessions)

Le levier le moins cher du dépôt, et celui qui bénéficie le plus au modèle de
développement (sessions LLM successives sans mémoire partagée).

| # | Chantier | Contenu | Preuve de sortie |
|---|---|---|---|
| 2.1 | **Ruff (lint + format) sur `core`** | Configuration dans `pyproject.toml`, passe de mise en conformité en un commit isolé, job CI. | `uv run ruff check` et `ruff format --check` verts en CI. |
| 2.2 | **ESLint + Prettier sur `shell`** | Config plate, règles ciblées (`react-hooks`, interdiction de `dangerouslySetInnerHTML` hors `sanitizeMarkdown.ts`, `no-floating-promises`), job CI. | La règle `dangerouslySetInnerHTML` échoue si on l'introduit hors de la couche de sanitation. |
| 2.3 | **Mypy sur `core`, périmètre progressif** | Strict sur `app/auth`, `app/secrets`, `app/analytics`, `app/copilot` d'abord ; le reste en non-bloquant. | Job CI vert sur le périmètre déclaré. |
| 2.4 | **Couverture mesurée, seuil non régressif** | `pytest --cov` + couverture Vitest, publication du chiffre, seuil « ne baisse pas » plutôt qu'un objectif arbitraire. | Le chiffre apparaît dans la CI ; une PR qui baisse la couverture échoue. |
| 2.5 | **Pre-commit** | ruff, eslint, prettier, `lint-imports`, vérification de message conventional. | `pre-commit run --all-files` vert. |
| 2.6 | **Boucher le contrat de couches** (I1) | Ajouter `app.cdc` (juste au-dessus d'`app.ingestion`), puis `app.analytics` et `app.search` au bas de la pile, et `app.instance`. **Correctif déjà validé empiriquement : le contrat passe.** | `uv run lint-imports` : 1 kept, 0 broken, avec 30 couches. |
| 2.7 | **Sécurité de chaîne d'outils** | Semgrep ou CodeQL, secret scanning (gitleaks), Trivy sur les images publiées, SBOM au release, Dependabot/Renovate. | 4 jobs CI supplémentaires, verts. |

### Vague 3 — Durcissement avant v0.1 publique (≈ 3 sessions)

| # | Chantier | Contenu | Preuve de sortie |
|---|---|---|---|
| 3.1 | **Interdire le mode mock hors développement** (C6) | Échec au démarrage si `CORE_AUTH_MODE=mock` sans marqueur explicite (`CORE_ENV=development`) ; `docker-compose.prod.yml` force `oidc`. | Test : `mock` sans marqueur → refus de démarrage. |
| 3.2 | **Clé maître au démarrage** (I10) | Appeler `load_master_key()` au boot quand la capacité secrets est utilisable ; corriger la phrase de CLAUDE.md. | Test : absence de clé → refus de démarrage, message actionnable. |
| 3.3 | **CSP, Permissions-Policy, compression** (I3) | En-têtes sur le middleware Traefik **et** dans `shell/nginx.conf` (les deux chemins existent) ; `gzip`/`compress`. CSP calibrée sur MapLibre, deck.gl, les extensions tierces et les tuiles. | Un widget tiers légitime charge encore ; `curl -H 'Accept-Encoding: gzip'` renvoie du contenu compressé. |
| 3.4 | **Rate limiting différencié** (I4) | Limites par utilisateur/tenant côté application sur `/analytics/sql`, `/mcp`, `/copilot/turn`, `/export`, `/app-exports`, `/harvest`. | Test : le 4ᵉ `POST /analytics/sql` en 10 s → 429, un `GET /health` concurrent passe. |
| 3.5 | **Format d'erreur unique + arrêt propre + garde de rendu** (ARC-04, I11, I12) | `exception_handler` global RFC 7807 ; handler `SIGTERM` sur `cdc-worker` ; `ErrorBoundary` au niveau de l'`App`. | Test : une exception non gérée renvoie un `application/problem+json`. Test : `SIGTERM` sur `cdc-worker` referme proprement. |
| 3.6 | **Conteneurs non-root** (SEC-02) | `USER` dans les 8 Dockerfiles ; pour `core`, déplacer explicitement le répertoire d'extensions DuckDB (`DUCKDB_HOME` ou `--home`) pour que la contrainte documentée tombe. | `docker run … id -u` ≠ 0 sur les 8 images, et un `POST .../aggregate` fonctionne toujours hors ligne. |
| 3.7 | **Notifier les alertes** (I9) | `contactPoints` + `policies` provisionnés, exemple webhook/email dans `.env.example`. | La règle « TEST — preuve que le pipeline d'alerting fonctionne » délivre réellement une notification. |
| 3.8 | **E2E sur OIDC réel** (I13) | Une spec unique contre le Keycloak du compose : login, refresh, expiration, logout. | La spec passe en CI avec un service Keycloak. |

### Vague 4 — Combler les manques fonctionnels (≈ 15 à 22 sessions)

Détail, preuves et arbitrages en **§7**. Contrairement aux vagues 0 à 3, chaque
ligne est un vrai périmètre produit, pas un correctif : cette vague se
sous-traite par lots, elle ne s'exécute pas d'un bloc. La colonne **E** donne
l'effort (S = sous la session, M = une à deux sessions, L = un SP à part
entière).

**Carte — le lot à faire d'abord**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.1 | L | **Popup d'attributs + clic sur les couches tuilées** (F1, F2) — popup configurable dans la visionneuse, le widget carte et `/sites/{slug}` ; handler `queryRenderedFeatures` sur `kind: "vector"`, pas seulement `kind: "feature"`. | Cliquer une entité d'une collection servie en tuiles MVT ouvre un popup renseigné, sur une carte publiée, sans widget d'app à côté. |
| 4.2 | M | **Symbologie dans l'éditeur de cartes** (S1) — porter `mapSymbology.ts` dans `LayersPanel` ; `MapLayer` gagne une symbologie déclarative compilée vers MapLibre à l'affichage, au lieu d'un `paint` brut. | Styliser une couche de l'éditeur de cartes sans écrire de JSON MapLibre ; l'export PNG/PDF (SP-17a) rend le même style. |
| 4.3 | M | **Classes et palettes** (S2, S3) — quantiles / intervalles égaux / seuils naturels, nombre de classes choisi, palettes sélectionnables branchées sur le `Theme` existant au lieu des constantes du module. | Une carte à 5 classes en quantiles, dans la palette du thème du site, round-trippée en config et rendue à l'identique. |
| 4.4 | M | **Étiquettes, contour, opacité, icônes** (S4, F5) — compléter la symbologie déclarative de 4.2. | Une couche de communes étiquetées par leur nom, identique à l'export. |
| 4.5 | M | **Mesure et croquis pour le lecteur** (F3) — distance, surface, annotation éphémère non persistée. | Mesurer une distance sur une carte publiée sans droit d'écriture. |

**Découverte et publication ouverte**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.6 | S | **Le catalogue voit les 12 types** (A1) — le filtre `Type` de `CatalogPage` propose app/dashboard/map seulement ; y ajouter dataset, pipeline, site, bookmark, alert, report, tileset3d, terrain3d, external. | Filtrer sur « Dataset » ramène les datasets ; aucun type de `ResourceType` n'est absent du sélecteur. |
| 4.7 | M | **Tri et facettes** (A2) — tri par date/titre/pertinence, facettes sur `keywords` (déjà stocké), filtre par propriétaire. | Trier le catalogue par date de modification et filtrer par mot-clé sans passer par la recherche plein texte. |
| 4.8 | M | **Recherche spatiale au catalogue** (A3) — emprise de recherche sur une carte, sur l'emprise déjà calculable des collections. | Dessiner un rectangle sur la Corrèze ne ramène que les jeux qui l'intersectent. |
| 4.9 | L | **Métadonnées éditables et licence par jeu** (B1, B2) — l'`Item` n'a que titre/résumé/mots-clés ; `dct:license` est **codé en dur** à `LICENSE_OTHER` dans `dcat/serializers.py`, `dct:language` à `"fr"`. Ajouter licence, producteur, fréquence de mise à jour, contact, généalogie, emprises spatiale et temporelle réelles, et les brancher sur DCAT **et** STAC. | Un jeu publié en Licence Ouverte 2.0 sort de l'export DCAT-AP avec la bonne URI de licence, moissonnable par data.gouv.fr. |
| 4.10 | M | **SEO des portails publics** (I1) — aucun `sitemap`, `robots.txt`, `og:`, `canonical` ni description par page dans tout le dépôt. | Une page `/sites/{slug}` produit un aperçu correct partagée dans un message, et apparaît dans un `sitemap.xml`. |

**Données et saisie**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.11 | M | **Vocabulaire contrôlé de bout en bout** (C1, G1) — aucun type `enum`/domaine dans les 7 `sqlType` de collection, et aucun champ `select` dans les 5 types du widget Formulaire. Ajouter le domaine côté collection et le rendu liste côté formulaire, d'un seul tenant. | Une collection déclare un domaine « état : projeté / en cours / livré » ; le formulaire l'affiche en liste et refuse toute autre valeur. |
| 4.12 | L | **Pièces jointes sur une entité** (C2) — upload S3 présigné (patron A6), table de liaison tenant-scopée, ajout et rendu depuis le widget Formulaire, respect de `can()` et de la RLS de collection. | Une photo attachée depuis le formulaire est visible d'un lecteur autorisé et invisible des autres. |
| 4.13 | M | **Géocodage** (D1) — fournisseur enfichable (patron `LLMProvider`/`EmbeddingProvider`), premier fournisseur BAN `api-adresse.data.gouv.fr`, exposé en contrôle de carte et en widget. | « 12 rue de la République, Tulle » recentre la carte ; le fournisseur est remplaçable par configuration. |
| 4.14 | M | **Formats d'import manquants** (C3) — 4 formats aujourd'hui (GeoJSON, CSV lat/lon, GPKG, Shapefile zippé). Ajouter au minimum XLSX (déjà exporté, jamais importé), KML/KMZ et GeoParquet (déjà produit par le CDC). | Importer le XLSX qu'on vient d'exporter fonctionne, sans conversion manuelle. |

**Analytique**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.15 | S | **Agrégats manquants** (H1) — 5 agrégats aujourd'hui (`count`, `sum`, `avg`, `min`, `max`). Ajouter `countDistinct`, `median`, `percentile`, `stddev`. | Un indicateur « nombre de communes distinctes » et un « revenu médian » se construisent sans SQL Lab. |
| 4.16 | S | **Grains temporels manquants** (H2) — `bucket` est `day`/`week`/`month`. Ajouter `hour`, `quarter`, `year`. | Une série annuelle se construit dans l'assistant, pas en SQL. |
| 4.17 | M | **Animation temporelle** (H3) — lecture play/pause/vitesse sur le contexte temps global A29 déjà livré, pas un nouveau système de filtrage. | Une carte et un graphique liés au même dataset s'animent ensemble. |

**Cycle de vie et retour à l'utilisateur**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.18 | S | **Rendre l'historique de versions atteignable** (K1) — `POST /configs/{id}/rollback` et les configs versionnées existent **depuis SP-0** et sont testés ; aucune page du shell ne les appelle. Un panneau « Historique » suffit. | Restaurer une version antérieure d'une app depuis le builder, sans appel d'API à la main. |
| 4.19 | M | **Notifications in-app** (K2) — zéro `toast`/`notification` dans le shell, pour cinq familles de jobs asynchrones (ingestion, pipelines, export, export d'app, rapports). | Un run de pipeline en échec est signalé même si l'utilisateur a quitté le panneau de suivi. |
| 4.20 | M | **Journal d'audit consultable** (K3) — `audit_log` est alimenté par toute écriture (règle non négociable) et **aucune UI ne le lit**. | Un admin voit qui a modifié un item, quand, et depuis quel chemin. |

**Gouvernance et exploitation**

| # | E | Chantier | Preuve de sortie |
|---|---|---|---|
| 4.21 | L | **Gestion des utilisateurs et des rôles** (L1) — `core/app/users/` n'a **pas de `routes.py`** ; les rôles ne viennent que de `CORE_ADMIN_SUBS`/`CORE_ANALYST_SUBS`, **lus à la création de l'utilisateur seulement**. Promouvoir quelqu'un exige aujourd'hui d'éditer l'environnement et de recréer la ligne. | Un admin promeut un analyste depuis l'UI ; l'action est auditée ; aucune variable d'environnement n'est touchée. |
| 4.22 | M | **Quotas et usage** (L2) — aucun quota, aucune statistique d'usage, pour une plateforme qui accepte des uploads de tilesets 3D de plusieurs Go. | Un tenant qui dépasse son quota de stockage voit son upload refusé avec un message clair. |
| 4.23 | M | **Liens de partage à échéance** (J1) — partage `viewer`/`editor` par item/collection via groupes plats, sans lien à jeton ni expiration. Réutiliser le patron du jeton d'export éphémère SP-17a. | Un lien partagé donne accès en lecture puis cesse de fonctionner à l'échéance, et l'accès est audité. |
| 4.24 | S | **Widget de saisie lié à une variable** (F2 §7-W) — les variables typées SP-5 ne se règlent que par une action composée (`AppRenderer.tsx:51-58`). | Saisir un seuil dans un champ recalcule un indicateur lié par binding CEL. |

### Vague 5 — Ouverture du produit (≈ 4 à 6 sessions)

C'est ici que se joue l'adoption, pas dans les vagues précédentes.

| # | Chantier | Contenu | Preuve de sortie |
|---|---|---|---|
| 5.1 | **i18n** (M2) | Extraction des ~784 littéraux vers un catalogue, `fr` comme locale de référence, `en` comme seconde locale, `lang` dérivé de la locale. À faire **en un chantier dédié** : réparti sur plusieurs SP il ne se terminera jamais. | Bascule `fr`↔`en` complète sur les parcours catalogue, builder, runtime ; aucun littéral résiduel détecté par une règle de lint. |
| 5.2 | **Audit d'accessibilité** (M3) | `axe-core` dans Vitest/Playwright sur les 6 écrans principaux, corrections de contraste et de focus, parcours clavier du builder. | 0 violation `serious`/`critical` sur les 6 écrans, en CI. |
| 5.3 | **Contrat d'API** (M4) | Préfixe `/v1/`, politique de dépréciation écrite, documentation interactive (Redoc/Scalar) publiée depuis l'`openapi.json` déjà exporté. | Les anciens chemins répondent encore ; le client TS généré cible `/v1/`. |
| 5.4 | **ADR** (M4) | `docs/adr/` avec au minimum : monolithe modulaire + import-linter, multi-tenant + RLS, procrastinate sans broker, `ItemClient` comme sas, sidecar QGIS et licence GPL, CDC vers GeoParquet, MCP dans le cœur, copilote et frontière de confiance. | 8 ADR, référencés depuis CLAUDE.md. |
| 5.5 | **Contribution externe** | Guide « premier ticket », labels `good first issue`, modèle de PR, guide auteur du SDK Web Components complété. | Un contributeur externe peut livrer un widget sans poser de question. |

### Vague 6 — Dette d'architecture (opportuniste, jamais bloquant)

| # | Chantier | Contenu |
|---|---|---|
| 6.1 | **Une seule primitive de quoting** (M1) | Un module bas dans la pile (sous `app.analytics`, désormais dans le contrat) exposant `quote_ident`/`sql_literal` **publics** et testés contre une batterie d'injection ; supprimer les 6 copies ; retirer le commentaire auto-contredit. |
| 6.2 | **Une seule garde d'egress** | Fusionner les 3 gardes en un module bas de pile avec une allowlist unique + surcharges par consommateur ; y faire passer l'appel LLM du copilote (4ᵉ surface, aujourd'hui non gardée). |
| 6.3 | **Segmenter `ItemClient`** (M5) | Découper en interfaces par domaine composées en un `ItemClient` agrégé, pour que `StaticItemClient` n'ait plus à réécrire 83 signatures. |
| 6.4 | **`app.db` sans les 18 dérogations** (ARC-03) | Un module d'enregistrement de metadata au bas de la pile, importé par `app.db`, pour vider `ignore_imports`. |
| 6.5 | **Journal CDC borné** | Suivi déjà ouvert : `replace` planifié fait croître le journal CDC d'environ 2× par run. À traiter quand l'usage réel le justifie. |
| 6.6 | **Reprendre les jobs orphelins** | `appexport.repository.reclaim_stuck_jobs` est du code mort : aucune tâche périodique ne l'appelle, contrairement à `app.export`/`app.reports`. |
| 6.7 | **Tests QGIS réels** | Les 5 tests `@pytest.mark.qgis` de SP-15d n'ont jamais tourné. Dernier point bloquant du jalon M14. |
| 6.8 | **Rafraîchir CLAUDE.md** (M6) | Corriger les compteurs de tests, la phrase sur la clé maître, et ajouter une règle : tout ajout de variable d'environnement passe par la garde CI 1.5. |

---

## 5. À ne pas faire

Explicitement écarté, pour que ces propositions ne reviennent pas à chaque
analyse externe :

- **Cache Redis / Memcached** (Kimi FEAT-04) — contredit la sortie de Redis
  actée au jalon M1. Si un cache devient nécessaire, ce sera une décision
  produit argumentée, pas une optimisation.
- **Refonte `domain/application/infrastructure`** (ChatGPT §4) — réécrire 19k
  lignes pour remplacer un contrat de couches qui fonctionne. Le vrai défaut du
  contrat est son incomplétude (chantier 2.6, 4 lignes).
- **Extraction des workers en microservices** (Grok A3) — aucune mesure de
  charge ne l'appuie ; les files procrastinate donnent déjà l'isolation utile.
- **Pagination cursor-based** (Kimi PERF-01) — `offset` est ce que spécifie OGC
  API Features. À traiter sur preuve de lenteur mesurée.
- **Reconstruire SLO / dashboards / alerting** — déjà livré par SP-10b. Seul le
  contact point manque (3.7).
- **Réécrire les gardes SSRF** — correctes ; il faut les *unifier* (5.2), pas
  les refaire.
- **3D, impression, analytique embarquée, fédération de catalogues, ETL** — tous
  livrés. Toute analyse qui les propose comme du travail à venir se trompe de
  date. Les vrais manques fonctionnels sont ailleurs, et sont en **§7** : ce
  sont eux qui remplacent les propositions produit des trois analyses, pas
  l'inverse.
- **La roadmap M1→M10 de Kimi** — obsolète de ~14 mois. `M15` est atteint.

---

## 6. Séquencement recommandé

1. **Vague 0** avec SP-20 — ne pas merger le copilote avec C1/C2/C3 ouverts.
2. **Vague 1** immédiatement après, en un SP dédié (« déployabilité »). C'est le
   meilleur retour technique du plan : elle ne livre rien de neuf et rend cinq
   SP utilisables.
3. **Vague 2** ensuite, ou en parallèle : elle réduit le coût de toutes les
   vagues suivantes, et particulièrement le coût des sessions LLM.
4. **Les quatre bouchons à coût faible, dès que la vague 1 est close** — 4.18
   (panneau d'historique/rollback), 4.6 (le catalogue voit les 12 types), 4.15
   (`countDistinct`, médiane) et 4.16 (grains `year`/`quarter`/`hour`). Quatre
   chantiers marqués **S**, tous sur des fondations déjà livrées et testées.
   C'est le meilleur rapport valeur/effort du document, toutes vagues
   confondues.
5. **Vague 4, lot Carte** (4.1 → 4.3) ensuite, et sans attendre la vague 3 :
   popup, clic sur tuiles vectorielles et symbologie réelle conditionnent la
   crédibilité de SP-13 comme celle du critère de sortie M4. Une carte qu'on ne
   peut ni interroger ni styliser reste un fond d'écran, quel que soit l'état de
   la CI.
6. **Vague 3** avant toute exposition publique (M6, instance de démo) — en y
   ajoutant 4.9 (licence et métadonnées) et 4.10 (SEO) si le portail public fait
   partie de la démonstration, sans quoi elle démontrera une capacité
   d'ouverture que le produit n'a pas.
7. **Reste de la vague 4** par arbitrage produit, cas d'usage par cas d'usage.
   Trois questions tranchent la moitié du lot : le terrain est-il un usage visé
   (→ 4.11, 4.12, G2 hors-ligne) ? l'instance sera-t-elle multi-tenant réelle
   (→ 4.21, 4.22) ? l'open data est-il un objectif affiché (→ 4.9, 4.10) ?
8. **Vague 5** est la vraie condition d'adoption externe *contributive*. À
   planifier comme un SP à part entière, pas comme un lot d'améliorations.
9. **Vague 6** au fil de l'eau, quand un SP touche déjà le code concerné.

Le jalon M16 (copilote) est atteignable dès la vague 0 terminée. En revanche
**M14 reste bloqué** par un seul point : les 5 tests QGIS de SP-15d n'ont jamais
été exécutés (chantier 6.7).

---

## 7. Analyse fonctionnelle

Pendant produit du §3. Elle sort d'une lecture du shell et des schémas du cœur,
que les trois analyses n'ont pas faite : leurs propositions fonctionnelles
portaient sur des capacités déjà livrées (3D, impression, analytique,
fédération, ETL), écartées en §5. Ce qui suit les remplace.

Chaque domaine dit d'abord **ce qui existe** — pour que le manque soit lisible à
sa juste échelle — puis ce qui manque, vérifié. Aucun de ces constats n'est un
bug : ce sont des périmètres jamais construits, donc des arbitrages.

### A — Catalogue et découverte

**Existe** : recherche sémantique hybride (pgvector + trigram, RRF, SP-7) — de
la recherche de bien meilleure qualité que celle de la plupart des catalogues
géo ; portées « mes éléments / partagés / publics » ; vignettes ; pagination ;
mots-clés stockés sur l'item.

**A1 — Le sélecteur de type du catalogue est resté à SP-0.** `ResourceType`
compte **12 valeurs** (`app`, `dashboard`, `map`, `site`, `dataset`, `external`,
`bookmark`, `pipeline`, `alert`, `report`, `tileset3d`, `terrain3d`). Le filtre
`Type` de `CatalogPage.tsx` en propose **trois** : App, Dashboard, Map. Les
datasets, pipelines, sites, signets, alertes, rapports et tilesets 3D sont donc
**non filtrables**, et pour la plupart non parcourables : on ne les trouve qu'en
sachant déjà leur nom, via la recherche plein texte. Neuf des dix kinds de
document déclaratif livrés depuis SP-14 sont invisibles au parcours.

**A2 — Aucun tri, aucune facette.** Pas de tri par date de modification, par
titre ni par pertinence. Les `keywords` sont stockés sur l'`Item` et ne sont
jamais exposés en facette. Le paradoxe : la recherche est excellente, le
parcours est primitif — or un catalogue public sert surtout à parcourir.

**A3 — Aucune recherche spatiale.** Pour un catalogue géospatial, on ne peut pas
chercher « ce qui couvre mon territoire ». Aucune emprise n'est stockée sur
l'item (cf. B1), donc rien ne pourrait le servir aujourd'hui.

### B — Métadonnées et publication ouverte

**Existe** : API STAC native en lecture, export DCAT-AP en JSON-LD, moissonnage
par cinq connecteurs (SP-12). L'infrastructure de fédération est là.

**B1 — Le modèle `Item` n'a presque aucune métadonnée.** Ses champs utiles sont
`title`, `abstract`, `keywords`, `thumbnail_key`, `is_published`, `is_public`.
Manquent : licence, producteur, contact, fréquence de mise à jour, généalogie,
**emprise spatiale**, **emprise temporelle**, version, langue. Ce sont
exactement les champs qu'un catalogue existe pour porter.

**B2 — Conséquence directe : l'export DCAT-AP est inexploitable pour
l'open data.** `dcat/serializers.py:61` émet `"dct:license": {"@id":
LICENSE_OTHER}` — **la même licence codée en dur pour tous les jeux** —,
`dct:language` figé à `"fr"`, et `dct:publisher` réduit au nom du tenant. Un
auteur ne peut déclarer aucune licence. L'export est structurellement valide et
fonctionnellement vide : la licence est le champ décisif d'un moissonnage
data.gouv.fr ou European Data Portal. C'est le seul endroit du dépôt où une
capacité livrée ne peut pas remplir sa fonction, indépendamment de tout bug.

### C — Ingestion et modèle de données

**Existe** : 4 formats (GeoJSON, CSV lat/lon avec détection automatique des
colonnes, GeoPackage multi-couches, Shapefile zippé), reprojection vers WGS84
par pyproj avec échec propre sur CRS inconnu, ingestion asynchrone
procrastinate, `feature_count`, jusqu'à 50 000 entités validées (jalon M4).
7 types de colonne : `text`, `integer`, `bigint`, `double precision`, `boolean`,
`date`, `timestamptz` — le nécessaire numérique est là.

**C1 — Aucun vocabulaire contrôlé.** Pas de type `enum`/domaine, donc aucune
liste de valeurs autorisées au niveau de la donnée. C'est la contrainte la plus
demandée en collecte terrain et en qualité de données, et elle se combine avec
G1 pour rendre toute saisie contrôlée impossible.

**C2 — Aucune pièce jointe sur une entité.** Les seules occurrences
d'`attachment` sont des en-têtes `Content-Disposition` d'export. Le widget
Formulaire et le `canWrite` par utilisateur (SP-4) visent la collecte ; sans
photo ni document, le cas d'usage terrain ne tient pas.

**C3 — Formats d'import en retard sur les formats d'export.** La plateforme
**exporte** CSV, XLSX, GeoJSON et GPKG (SP-16a) et **produit** du GeoParquet
(CDC, SP-11a) ; elle n'importe ni XLSX ni GeoParquet. Manquent aussi KML/KMZ,
GML, FlatGeobuf, GPX. Un aller-retour export → correction dans un tableur →
réimport, le geste le plus banal d'un agent, est impossible.

**C4 — Aucune règle de qualité** au-delà de la validation de schéma : pas de
contrainte métier, pas d'unicité fonctionnelle, pas d'alerte d'anomalie à
l'ingestion.

### D — Cartographie : interaction

**Existe** : MapLibre + deck.gl sous un seul overlay, 5 kinds de couche
(`vector` tuilé, `raster`, `feature` GeoJSON, `deck` heatmap/hexbin/column,
`tiles3d`), terrain raster-dem, caméra pitch/bearing persistée, sélecteur de
fond de carte, panneau de couches, légende dans la visionneuse, export PNG/PDF
mis en page.

**D1 — Aucun popup, nulle part.** Zéro occurrence de `popup` dans
`shell/src/map` et `shell/src/builder/widgets`. Un lecteur d'une carte publiée,
d'une fiche dataset ou d'une page `/sites/{slug}` **ne peut pas cliquer une
entité pour voir ses attributs**. Le clic existe
(`MapView.tsx:106-111`, `onFeatureClick`) mais il alimente la sélection —
édition SP-4, cross-filter SP-14n — jamais un affichage. Sans qu'un auteur ait
explicitement posé un widget Table à côté de la carte, la donnée est muette.

**D2 — Interactivité et passage à l'échelle sont mutuellement exclusifs.** Le
handler de clic n'est posé que sur les couches `kind: "feature"` (GeoJSON par
URL). Les couches `kind: "vector"` — les tuiles MVT servies par Martin,
c'est-à-dire le chemin performant pour tout jeu de données réel — n'ont **aucun**
handler. Dès qu'un jeu est assez gros pour être tuilé, il devient inerte. C'est
le constat le plus structurant du §7 : corriger D1 seul ne servirait qu'aux
petits jeux.

**D3 — Aucun géocodage, aucune recherche d'adresse** dans tout le dépôt. Pour un
portail public français, la BAN est un standard de fait ; c'est aussi ce qui
manque au geste le plus banal d'un visiteur, « zoomer sur ma commune ».

**D4 — Aucun outil de mesure ni de dessin** pour le lecteur. Les seules
occurrences de `draw` sont `drawer` (le widget tiroir) et un commentaire sur
l'ordre de rendu du terrain.

### E — Cartographie : symbologie

**Existe** : `mapSymbology.ts` — couleur par champ catégorielle ou numérique,
taille par champ sur les points, détection automatique du type de géométrie,
légende générée, rendu `fill`/`circle`/`line`. Propre, testé, et suffisant pour
une première carte.

**E1 — La symbologie n'existe que dans le widget carte des apps, pas dans
l'éditeur de cartes.** `shell/src/map/LayersPanel.tsx` ne contient **aucun** code
de style, et `MapLayer.paint` reste un `Record<string, unknown>` brut
(`types.ts:65-69`). L'éditeur de cartes — l'objet phare du produit depuis SP-0,
celui qu'un utilisateur ouvre en premier — est le seul endroit où styliser exige
d'écrire du JSON MapLibre à la main. Le module existe et fonctionne : il est au
mauvais endroit.

**E2 — Pas de classes.** La couleur numérique est une rampe à **deux arrêts**
(`NUMERIC_COLOR_LOW` → `NUMERIC_COLOR_HIGH`). Ni quantiles, ni intervalles
égaux, ni seuils naturels, ni nombre de classes choisi. C'est l'opération
thématique la plus courante de la cartographie.

**E3 — Palettes codées en dur.** `CATEGORICAL_PALETTE` et les deux bornes
numériques sont des constantes du module : **un auteur ne peut pas changer une
couleur**. Le produit a par ailleurs un vrai système de thème
(`ThemePanel.tsx`, `AppConfig.theme`) — la carte est précisément la seule chose
que le thème n'atteint pas. C'est bloquant pour SP-13, dont la promesse est un
portail public aux couleurs d'une institution.

**E4 — Ni opacité, ni contour, ni épaisseur, ni pointillés, ni symboles
ponctuels, ni clustering, ni étiquettes** (aucun `text-field` généré : une couche
de communes ne peut pas afficher les noms).

**Conséquence de E1→E4** : le critère de sortie M4 — « upload GPKG → carte
stylée partageable en minutes » — n'est vrai que pour un style par défaut.

### F — Builder d'apps et de dashboards

**Existe**, et c'est la partie la plus mûre du produit : 22 widgets, grille
responsive à points de rupture, thème éditable, pages avec navigation onglets ou
narration (`story`), variables typées, bindings CEL, actions composées avec
condition, filtres croisés, mise en page d'impression, undo/redo (SP-19), export
en trois modes, modèles de départ (`templates.ts`), SDK Web Components pour les
widgets tiers, 12 types de graphique ECharts, table avec tri et pagination.

**F1 — Quatre briques attendues manquent au catalogue de widgets** :
liste de couches activable par le lecteur dans une app (la visionneuse a son
`LayersPanel`, le widget carte n'a que sa mini-légende) ; comparateur
avant/après (swipe), classique dès qu'il y a de l'imagerie — et TiTiler est déjà
dans la stack ; champ de saisie lié à une variable ; recherche/géocodeur.

**F2 — Les variables typées ne se règlent que par une action composée.** Elles
*sont* bien réglables (`AppRenderer.tsx:51-58`, action `var:{id}` / `set`) —
mon inventaire initial se trompait sur ce point — mais il n'existe aucun widget
de saisie simple. Un auteur qui veut un champ « seuil » doit passer par une
action.

**F3 — La table n'est pas éditable en place** et n'a ni formatage de colonne, ni
largeur, ni regroupement, ni mise en forme conditionnelle. Acceptable en v0, à
noter comme la limite du widget le plus utilisé après la carte.

### G — Formulaires et collecte

**Existe** : widget Formulaire généré depuis le schéma de collection, édition
depuis la sélection carte ou table, `canWrite` par utilisateur, validation
`required` / `maxLength` / `min` / `max` / `pattern`, visibilité
conditionnelle CEL (`visibleWhen`), écriture par OGC API Features Part 4 avec
RLS.

**G1 — Cinq types de champ, et pas de liste.** `text`, `number`, `integer`,
`date`, `checkbox`. Manquent **`select`/liste déroulante** — le besoin numéro un
d'une saisie contrôlée —, boutons radio, zone de texte multiligne, fichier/photo,
et les types typés `email`/`url`/`tel`. Combiné à C1 (aucun domaine côté
collection), cela signifie qu'**il n'existe aucun vocabulaire contrôlé dans tout
le produit**, ni à la donnée, ni à la saisie.

**G2 — Aucun mode hors-ligne** (question produit Q11, ouverte depuis le début).
Décisif si le terrain est un usage visé ; à trancher explicitement plutôt qu'à
laisser ouvert indéfiniment.

**G3 — Aucun workflow de validation** : pas de brouillon/soumission/approbation,
pas d'état de relecture. Une écriture est immédiate et définitive.

### H — Analytique

**Existe** : datasets comme objets de plateforme, pipeline déclaratif, métriques
CEL, requête visuelle no-code Filtrer→Joindre→Résumer, contexte global
temps × emprise, filtres croisés inter-datasets, SQL Lab bordé pour analystes,
DuckDB sur GeoParquet, alertes de seuil, rapports planifiés, exports secs.
C'est une pile analytique sérieuse.

**H1 — Cinq agrégats seulement** : `count`, `sum`, `avg`, `min`, `max`. Manquent
`countDistinct` — sans doute la métrique la plus utilisée après `count` : « combien
de communes distinctes », « combien d'usagers uniques » —, `median`,
`percentile`, `stddev`, `variance`. En statistique publique, la médiane n'est pas
un raffinement, c'est l'indicateur de référence (revenu médian, âge médian).

**H2 — Trois grains temporels** : `bucket` est `day`/`week`/`month`. Manquent
`hour`, `quarter` et **`year`**. Une série annuelle — la vue la plus courante en
statistique publique — n'est pas construisible sans passer au SQL Lab.

**H3 — Aucune animation temporelle.** `dateRangeFilter` filtre ; rien ne joue une
série. C'est l'extension la plus directe d'un socle déjà livré : le contexte
temps global A29 fournit exactement ce qu'il faut.

**H4 — `bucket` exige un `groupBy` à un seul champ** (`aggregate.py:93-94`) :
pas de série temporelle ventilée par catégorie, le graphique multi-séries le
plus courant.

### I — Portails publics (SP-13)

**Existe** : modèle site/slug, route publique `/sites/{slug}`, widgets de
contenu Hero/RichSection/Gallery, fiche dataset avec téléchargement, modèle de
galerie, thème.

**I1 — Aucun SEO.** Zéro `sitemap`, `robots.txt`, balise `og:`, `canonical` ou
description par page dans tout le dépôt. Un portail public dont la raison d'être
est d'être trouvé est invisible des moteurs, et un lien partagé dans un message
ou une lettre d'information ne produit aucun aperçu. Pour SP-13, c'est le manque
le plus contradictoire avec l'intention.

**I2 — Aucun domaine personnalisé** : un portail vit sous
`/sites/{slug}` du domaine de l'instance. Une collectivité ne peut pas servir le
sien.

**I3 — Aucune internationalisation** (cf. M2 en §3) : le portail est en
français, en dur.

### J — Partage, droits, gouvernance

**Existe** : groupes gérés par le cœur, `item_shares` et `collection_shares`,
porte `can()` unique, RLS PostGIS par collection, publication publique,
rôles admin/analyste, `audit_log` sur toute écriture.

**J1 — Le partage est le sous-système le moins riche du produit.** `role` vaut
`"viewer" | "editor"`, via des groupes plats. Manquent : lien de partage à jeton
et à échéance, rôle « commentateur », transfert de propriété, groupes imbriqués,
publication expirante. Face au reste — RLS par collection, `can()`, 10 kinds de
document — c'est un décalage net de maturité.

**J2 — Aucun commentaire ni annotation** sur un item : aucune boucle de
collaboration entre l'auteur et le lecteur.

### K — Cycle de vie et retour à l'utilisateur

**K1 — L'historique de versions existe côté serveur et n'est atteignable par
personne.** Les configs sont versionnées et `POST /configs/{id}/rollback` est
implémenté, audité et testé — **depuis SP-0**. Aucune page du shell ne l'appelle.
Donc : SP-19 a livré un undo/redo éphémère et en session, tandis qu'un
utilisateur qui enregistre une mauvaise modification puis recharge la page a
définitivement perdu son travail — alors que le serveur en détient chaque
version. C'est le meilleur rapport valeur/effort de tout le §7 : l'API est là,
il manque un panneau.

**K2 — Aucune notification in-app.** Zéro `toast`/`notification` dans le shell,
pour **cinq familles de travaux asynchrones** (ingestion, pipelines, export,
export d'app, rapports). Les alertes notifient par webhook et courriel (SP-16b),
les rapports par courriel (SP-17b) : l'application elle-même ne dit jamais rien.
Un run échoué n'est visible que si l'on regarde le bon panneau au bon moment.

**K3 — Le journal d'audit n'est lisible par personne.** `audit_log` est alimenté
par toute écriture — règle d'architecture non négociable — et il n'existe **aucune
UI** pour le consulter (zéro occurrence d'`audit` dans `shell/src`). L'exigence
de traçabilité est remplie côté écriture et vide côté usage : personne ne peut
répondre à « qui a modifié ça ».

### L — Administration et exploitation

**Existe** : pages d'administration pour les collections, les extensions de
widgets et les sources de moissonnage ; bootstrap des rôles par variables
d'environnement ; mode démo lecture seule ; coffre de secrets.

**L1 — Il n'y a aucune gestion des utilisateurs.** `core/app/users/` contient
`models.py` et `repository.py` — **pas de `routes.py`**. Les utilisateurs sont
créés à la volée à la première connexion OIDC, et les rôles ne viennent que de
`CORE_ADMIN_SUBS` / `CORE_ANALYST_SUBS`, **lus uniquement au moment de la
création** de la ligne. Conséquences concrètes : on ne peut pas lister les
utilisateurs, ni promouvoir ou rétrograder quelqu'un sans éditer l'environnement
puis supprimer sa ligne pour qu'elle soit recréée, ni désactiver un compte, ni
voir qui a accès à quoi. Pour une plateforme multi-tenant, c'est le manque
d'exploitation le plus lourd du §7.

**L2 — Aucun quota, aucune statistique d'usage** : ni stockage, ni nombre
d'entités, ni appels, ni budget LLM — pour une plateforme qui accepte des
uploads de tilesets 3D de plusieurs gigaoctets et qui appelle une API LLM
facturée à l'usage (cf. I6 en §3).

### Les dix constats qui pèsent le plus

Classement par valeur produit, indépendamment de l'effort. Les cinq premiers me
paraissent difficilement contournables avant de montrer le produit à un
utilisateur réel.

| Rang | Constat | Pourquoi il pèse |
|---|---|---|
| 1 | **D1 + D2** — pas de popup, et le clic ne marche pas sur les couches tuilées | Une carte publiée qu'on ne peut pas interroger est un fond d'écran. Et c'est le cas général, pas un cas limite : le chemin tuilé est celui de tout jeu réel. |
| 2 | **E1 + E2 + E3** — symbologie absente de l'éditeur de cartes, sans classes, palettes figées | Nie le critère de sortie M4 et la promesse white-label de SP-13. |
| 3 | **K1** — l'historique de versions n'est atteignable par personne | Une perte de travail définitive, alors que le serveur détient tout. Coût : un panneau. |
| 4 | **A1** — le catalogue ne connaît que 3 des 12 types | Neuf types de documents livrés sont invisibles au parcours. Coût : un sélecteur. |
| 5 | **B2** — la licence DCAT-AP est codée en dur | La capacité de publication open data ne peut pas remplir sa fonction. |
| 6 | **C1 + G1** — aucun vocabulaire contrôlé, ni à la donnée ni à la saisie | Bloque la collecte sérieuse et la qualité de données. |
| 7 | **L1** — aucune gestion des utilisateurs et des rôles | Rend l'exploitation multi-tenant impraticable au-delà de quelques comptes. |
| 8 | **H1 + H2** — pas de `countDistinct`, pas de médiane, pas de grain annuel | Trois manques élémentaires pour un produit qui se positionne en analytique. |
| 9 | **I1** — aucun SEO sur les portails publics | Contredit directement la raison d'être de SP-13. |
| 10 | **K2 + K3** — aucune notification, journal d'audit illisible | Cinq familles de jobs asynchrones sans retour, et une traçabilité sans lecteur. |

### Ce que ce §7 ne propose pas

Ni collaboration temps réel (Q10), ni marketplace de widgets, ni application
mobile native, ni certification OGC, ni versionnement de la donnée elle-même
(le CDC le rendrait possible). Ce sont des directions défendables, mais aucune
ne relève d'un manque constaté dans le code : elles demandent un brainstorm
produit, pas une revue.
